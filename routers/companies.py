"""
Company management router: /companies/* endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from models import get_db
from models.company import Company
from models.user import User
from routers.auth import get_current_user
from services.relayer import Relayer

router = APIRouter(prefix="/companies", tags=["Companies"])


@router.get("/me")
async def get_company(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get full company details including vault address, balance, threshold, executives list."""
    # Get company
    result = await db.execute(select(Company).where(Company.id == current_user.company_id))
    company = result.scalar_one_or_none()
    
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Get live balance from chain
    relayer = Relayer()
    try:
        balance_wei = await relayer.get_vault_balance(company.contract_address)
        balance_eth = balance_wei / 1e18
    except Exception:
        balance_wei = 0
        balance_eth = 0.0
    
    return {
        "id": str(company.id),
        "name": company.name,
        "email": company.email,
        "threshold": company.threshold,
        "total_signers": company.total_signers,
        "contract_address": company.contract_address,
        "eth_address": company.eth_address,
        "balance_wei": balance_wei,
        "balance_eth": round(balance_eth, 6),
        "is_active": company.is_active,
        "created_at": company.created_at.isoformat() if company.created_at else None
    }


@router.get("/me/executives")
async def get_executives(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all executives with roles and node assignments."""
    result = await db.execute(
        select(User).where(User.company_id == current_user.company_id)
    )
    users = result.scalars().all()
    
    return {
        "executives": [
            {
                "id": str(user.id),
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
                "node_id": user.node_id,
                "is_active": user.is_active,
                "last_login": user.last_login.isoformat() if user.last_login else None
            }
            for user in users
        ],
        "count": len(users)
    }


@router.put("/me/threshold")
async def update_threshold(
    new_threshold: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update threshold in DB + call contract updateThreshold()."""
    # Only OWNER can update threshold
    if current_user.role != "OWNER":
        raise HTTPException(status_code=403, detail="Only owners can update threshold")
    
    # Get company
    result = await db.execute(select(Company).where(Company.id == current_user.company_id))
    company = result.scalar_one_or_none()
    
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Validate threshold
    if new_threshold < 1 or new_threshold > company.total_signers:
        raise HTTPException(
            status_code=400,
            detail=f"Threshold must be between 1 and {company.total_signers}"
        )
    
    # TODO: Call contract updateThreshold() via relayer (Phase 4)
    # For now, just update DB
    company.threshold = new_threshold
    await db.commit()
    
    return {
        "message": "Threshold updated successfully",
        "new_threshold": new_threshold
    }
