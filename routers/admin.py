"""
Admin router: /admin/* endpoints.

Platform-wide administration endpoints requiring admin JWT + secret header.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Header

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/companies")
async def list_companies(admin_secret: str = Header(..., alias="X-Admin-Secret")):
    """Get all companies on the platform."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="List companies endpoint - implement in Phase 4"
    )


@router.get("/relayer")
async def get_relayer_status(admin_secret: str = Header(..., alias="X-Admin-Secret")):
    """Get relayer wallet balance, total txs relayed, estimated ETH remaining."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Relayer status endpoint - implement in Phase 4"
    )


@router.get("/audit")
async def get_platform_audit(admin_secret: str = Header(..., alias="X-Admin-Secret")):
    """Get platform-wide audit log."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Platform audit endpoint - implement in Phase 4"
    )
