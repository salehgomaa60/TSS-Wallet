"""
Transaction lifecycle router: /transactions/* endpoints.
"""

import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from web3 import Web3

from models import get_db
from models.company import Company
from models.user import User
from models.transaction import Transaction
from models.approval import Approval
from models.audit_log import AuditLog
from routers.auth import get_current_user, write_audit_log
from services.relayer import Relayer

router = APIRouter(prefix="/transactions", tags=["Transactions"])


class ProposeRequest(BaseModel):
    to_address: str
    value_eth: float
    description: str


class RejectRequest(BaseModel):
    reason: Optional[str] = None


async def get_company_for_user(current_user: User, db: AsyncSession) -> Company:
    """Helper to get company for current user."""
    result = await db.execute(select(Company).where(Company.id == current_user.company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


async def check_vault_balance(company: Company, required_wei: int) -> bool:
    """Check if vault has sufficient balance."""
    relayer = Relayer()
    try:
        balance_wei = await relayer.get_vault_balance(company.contract_address)
        return balance_wei >= required_wei
    except Exception:
        return False


@router.post("/propose")
async def propose_transaction(
    req: ProposeRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Propose a new treasury transaction.
    
    1. Validate executive is active
    2. Convert value_eth to value_wei
    3. Check vault has sufficient balance
    4. Create transaction record (status: PENDING)
    5. Call proposeTransaction() on vault contract via relayer
    6. Send email notification to ALL other executives
    7. Write TX_PROPOSED to audit_log
    """
    # Validate user is active
    if not current_user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated")
    
    # Validate Ethereum address
    try:
        to_address = Web3.to_checksum_address(req.to_address)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid recipient address")
    
    # Convert ETH to wei
    value_wei = int(req.value_eth * 1e18)
    if value_wei <= 0:
        raise HTTPException(status_code=400, detail="Value must be greater than 0")
    
    # Get company
    company = await get_company_for_user(current_user, db)
    
    # Check vault has sufficient balance
    has_balance = await check_vault_balance(company, value_wei)
    if not has_balance:
        raise HTTPException(status_code=400, detail="Insufficient vault balance")
    
    try:
        # Create transaction record
        transaction = Transaction(
            company_id=company.id,
            proposed_by=current_user.id,
            to_address=to_address,
            value_wei=value_wei,
            value_eth=req.value_eth,
            description=req.description,
            status="PENDING",
            proposed_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=48)
        )
        db.add(transaction)
        await db.flush()
        
        # Call contract proposeTransaction (relayer pays gas)
        # Note: This is simplified - in production we'd need the relayer to actually call the contract
        # For now, we'll just record the proposal in our DB and the contract call would happen during approval
        
        # Write audit log
        await write_audit_log(
            db=db,
            action="TX_PROPOSED",
            company_id=company.id,
            user_id=current_user.id,
            details={
                "transaction_id": str(transaction.id),
                "to_address": to_address,
                "value_eth": req.value_eth,
                "description": req.description
            },
            ip_address=request.client.host if request.client else None
        )
        
        await db.commit()
        
        # TODO: Send email notification to other executives (Phase 4 with SendGrid)
        
        return {
            "transaction_id": str(transaction.id),
            "status": "PENDING",
            "to_address": to_address,
            "value_eth": req.value_eth,
            "expires_at": transaction.expires_at.isoformat(),
            "message": "Transaction proposed. Waiting for approvals."
        }
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to propose transaction: {str(e)}")


@router.post("/{tx_id}/approve")
async def approve_transaction(
    tx_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Approve a pending transaction.
    
    1. Validate executive has not already approved
    2. Get transaction from DB - check PENDING status
    3. Check transaction not expired (48 hour limit)
    4. Trigger MPC signing on this executive's TSS node
    5. Collect partial signature from node
    6. Save approval record with partial_signature
    7. Check: total approvals >= threshold?
       YES: aggregate signatures, broadcast, update status
       NO: update approval count, notify remaining executives
    """
    # Validate user is active
    if not current_user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated")
    
    # Get transaction
    try:
        tx_uuid = uuid.UUID(tx_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid transaction ID")
    
    result = await db.execute(
        select(Transaction).where(
            Transaction.id == tx_uuid,
            Transaction.company_id == current_user.company_id
        )
    )
    transaction = result.scalar_one_or_none()
    
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    if transaction.status != "PENDING":
        raise HTTPException(status_code=400, detail=f"Transaction is {transaction.status}")
    
    # Check not expired
    if transaction.expires_at and transaction.expires_at < datetime.now(timezone.utc):
        transaction.status = "EXPIRED"
        await db.commit()
        raise HTTPException(status_code=400, detail="Transaction has expired")
    
    # Check if user already approved
    result = await db.execute(
        select(Approval).where(
            Approval.transaction_id == transaction.id,
            Approval.user_id == current_user.id
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="You have already approved this transaction")
    
    # Get company for threshold
    company = await get_company_for_user(current_user, db)
    
    try:
        # Trigger MPC signing via coordinator
        # This is simplified - in production we'd collect partial signatures from nodes
        # For now, we simulate the signing process
        
        # Get current approvals count
        result = await db.execute(
            select(Approval).where(Approval.transaction_id == transaction.id)
        )
        current_approvals = len(result.scalars().all())
        
        # Record approval
        # Note: In production, this would include the actual partial signature from the TSS node
        approval = Approval(
            transaction_id=transaction.id,
            user_id=current_user.id,
            node_id=current_user.node_id,
            partial_signature={"r": "0x...", "s": "0x..."},  # Placeholder
            ip_address=request.client.host if request.client else None
        )
        db.add(approval)
        await db.flush()
        
        new_approval_count = current_approvals + 1
        threshold_reached = new_approval_count >= company.threshold
        
        if threshold_reached:
            # Update transaction status
            transaction.status = "EXECUTING"
            await db.flush()
            
            # In production: Aggregate signatures and call contract approveTransaction
            # For now, simulate execution
            transaction.status = "EXECUTED"
            transaction.executed_at = datetime.now(timezone.utc)
            transaction.tx_hash = "0x" + "0" * 64  # Placeholder
            
            # Write audit log for execution
            await write_audit_log(
                db=db,
                action="TX_EXECUTED",
                company_id=company.id,
                user_id=current_user.id,
                details={
                    "transaction_id": str(transaction.id),
                    "approvals_count": new_approval_count,
                    "threshold": company.threshold
                },
                ip_address=request.client.host if request.client else None
            )
            
            # TODO: Send execution notification to all executives (Phase 4 with SendGrid)
        else:
            # Write audit log for approval
            await write_audit_log(
                db=db,
                action="TX_APPROVED",
                company_id=company.id,
                user_id=current_user.id,
                details={
                    "transaction_id": str(transaction.id),
                    "approvals_count": new_approval_count,
                    "threshold": company.threshold
                },
                ip_address=request.client.host if request.client else None
            )
            
            # TODO: Send notification to remaining executives (Phase 4 with SendGrid)
        
        await db.commit()
        
        return {
            "transaction_id": tx_id,
            "status": transaction.status,
            "approvals_count": new_approval_count,
            "threshold": company.threshold,
            "executed": threshold_reached,
            "tx_hash": transaction.tx_hash if threshold_reached else None
        }
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Approval failed: {str(e)}")


@router.post("/{tx_id}/reject")
async def reject_transaction(
    tx_id: str,
    req: RejectRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Record rejection without cancelling transaction."""
    # Validate user is active
    if not current_user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated")
    
    # Get transaction
    try:
        tx_uuid = uuid.UUID(tx_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid transaction ID")
    
    result = await db.execute(
        select(Transaction).where(
            Transaction.id == tx_uuid,
            Transaction.company_id == current_user.company_id
        )
    )
    transaction = result.scalar_one_or_none()
    
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    if transaction.status != "PENDING":
        raise HTTPException(status_code=400, detail=f"Transaction is {transaction.status}")
    
    # Write audit log for rejection
    await write_audit_log(
        db=db,
        action="TX_REJECTED",
        company_id=current_user.company_id,
        user_id=current_user.id,
        details={
            "transaction_id": str(transaction.id),
            "reason": req.reason
        },
        ip_address=request.client.host if request.client else None
    )
    
    await db.commit()
    
    # TODO: Send notification to proposer (Phase 4 with SendGrid)
    
    return {
        "transaction_id": tx_id,
        "status": "REJECTED",
        "rejected_by": str(current_user.id),
        "message": "Transaction rejected. Other executives can still approve."
    }


@router.get("/pending")
async def get_pending_transactions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all PENDING transactions for this company with approval status."""
    # Get all pending transactions for company
    result = await db.execute(
        select(Transaction).where(
            Transaction.company_id == current_user.company_id,
            Transaction.status == "PENDING"
        ).order_by(Transaction.proposed_at.desc())
    )
    transactions = result.scalars().all()
    
    # Enrich with approval info
    response = []
    for txn in transactions:
        # Get approvals
        result = await db.execute(
            select(Approval, User).join(User).where(Approval.transaction_id == txn.id)
        )
        approvals = result.all()
        
        # Check if current user has approved
        user_approved = any(a.Approval.user_id == current_user.id for a in approvals)
        
        # Get approver names
        approvers = [{"id": str(a.User.id), "name": a.User.full_name} for a in approvals]
        
        response.append({
            "id": str(txn.id),
            "to_address": txn.to_address,
            "value_eth": txn.value_eth,
            "description": txn.description,
            "status": txn.status,
            "proposed_at": txn.proposed_at.isoformat() if txn.proposed_at else None,
            "expires_at": txn.expires_at.isoformat() if txn.expires_at else None,
            "approvals_count": len(approvals),
            "user_has_approved": user_approved,
            "approvers": approvers
        })
    
    return {
        "transactions": response,
        "count": len(response)
    }


@router.get("/history")
async def get_transaction_history(
    page: int = 1,
    limit: int = 20,
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get paginated transaction history."""
    # Build query
    query = select(Transaction).where(
        Transaction.company_id == current_user.company_id
    )
    
    # Filter by status if provided
    if status:
        query = query.where(Transaction.status == status)
    
    # Order by proposed date
    query = query.order_by(Transaction.proposed_at.desc())
    
    # Execute with pagination
    result = await db.execute(query.offset((page - 1) * limit).limit(limit))
    transactions = result.scalars().all()
    
    # Get total count
    count_result = await db.execute(
        select(Transaction).where(Transaction.company_id == current_user.company_id)
    )
    total = len(count_result.scalars().all())
    
    # Enrich with approval info
    response = []
    for txn in transactions:
        # Get approvals
        result = await db.execute(
            select(Approval, User).join(User).where(Approval.transaction_id == txn.id)
        )
        approvals = result.all()
        
        response.append({
            "id": str(txn.id),
            "to_address": txn.to_address,
            "value_eth": txn.value_eth,
            "description": txn.description,
            "status": txn.status,
            "proposed_at": txn.proposed_at.isoformat() if txn.proposed_at else None,
            "executed_at": txn.executed_at.isoformat() if txn.executed_at else None,
            "tx_hash": txn.tx_hash,
            "approvals_count": len(approvals),
            "approvers": [{"id": str(a.User.id), "name": a.User.full_name} for a in approvals],
            "etherscan_url": f"https://sepolia.etherscan.io/tx/{txn.tx_hash}" if txn.tx_hash else None
        })
    
    return {
        "transactions": response,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "pages": (total + limit - 1) // limit
        }
    }


@router.get("/{tx_id}")
async def get_transaction(
    tx_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get full transaction detail including approvals and partial signatures."""
    # Get transaction
    try:
        tx_uuid = uuid.UUID(tx_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid transaction ID")
    
    result = await db.execute(
        select(Transaction).where(
            Transaction.id == tx_uuid,
            Transaction.company_id == current_user.company_id
        )
    )
    transaction = result.scalar_one_or_none()
    
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    # Get approvals with user details
    result = await db.execute(
        select(Approval, User).join(User).where(Approval.transaction_id == transaction.id)
    )
    approvals = result.all()
    
    # Get proposer info
    result = await db.execute(
        select(User).where(User.id == transaction.proposed_by)
    )
    proposer = result.scalar_one_or_none()
    
    return {
        "id": str(transaction.id),
        "to_address": transaction.to_address,
        "value_wei": transaction.value_wei,
        "value_eth": transaction.value_eth,
        "description": transaction.description,
        "status": transaction.status,
        "tx_hash": transaction.tx_hash,
        "raw_transaction": transaction.raw_transaction,
        "proposed_by": {
            "id": str(proposer.id) if proposer else None,
            "name": proposer.full_name if proposer else "Unknown"
        },
        "proposed_at": transaction.proposed_at.isoformat() if transaction.proposed_at else None,
        "expires_at": transaction.expires_at.isoformat() if transaction.expires_at else None,
        "executed_at": transaction.executed_at.isoformat() if transaction.executed_at else None,
        "approvals": [
            {
                "id": str(a.Approval.id),
                "user": {
                    "id": str(a.User.id),
                    "name": a.User.full_name,
                    "email": a.User.email
                },
                "node_id": a.Approval.node_id,
                "partial_signature": a.Approval.partial_signature,
                "signed_at": a.Approval.signed_at.isoformat() if a.Approval.signed_at else None
            }
            for a in approvals
        ],
        "etherscan_url": f"https://sepolia.etherscan.io/tx/{transaction.tx_hash}" if transaction.tx_hash else None
    }
