"""
Vault operations router: /vault/* endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from models import get_db
from models.company import Company
from models.user import User
from routers.auth import get_current_user
from services.relayer import Relayer

router = APIRouter(prefix="/vault", tags=["Vault"])


@router.get("/balance")
async def get_vault_balance(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get live vault balance from Sepolia via web3.py.
    
    Returns:
        balance_wei: Balance in wei
        balance_eth: Balance in ETH
        contract_address: Vault contract address
    """
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
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch balance from chain: {str(e)}"
        )
    
    return {
        "balance_wei": balance_wei,
        "balance_eth": round(balance_eth, 6),
        "contract_address": company.contract_address,
        "eth_address": company.eth_address,
        "network": "sepolia",
        "chain_id": 11155111
    }


@router.get("/status")
async def get_vault_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get full vault status including balance and contract info.
    """
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
        
        # Try to get additional contract info
        threshold = await relayer.call_contract_view(
            company.contract_address, 
            "threshold"
        )
        spending_limit = await relayer.call_contract_view(
            company.contract_address, 
            "spendingLimitWei"
        )
    except Exception as e:
        balance_wei = 0
        balance_eth = 0.0
        threshold = company.threshold
        spending_limit = 0
    
    return {
        "vault": {
            "balance_wei": balance_wei,
            "balance_eth": round(balance_eth, 6),
            "threshold": threshold if isinstance(threshold, int) else company.threshold,
            "spending_limit_wei": spending_limit if isinstance(spending_limit, int) else 0,
        },
        "contract": {
            "address": company.contract_address,
            "etherscan_url": f"https://sepolia.etherscan.io/address/{company.contract_address}",
        },
        "tss_wallet": {
            "address": company.eth_address,
            "group_public_key": company.group_public_key,
        },
        "network": "sepolia",
        "chain_id": 11155111
    }


@router.get("/transactions")
async def get_vault_transactions():
    """Read on-chain events from contract (TransactionProposed, TransactionExecuted)."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Vault transactions endpoint - implement in Phase 4"
    )
