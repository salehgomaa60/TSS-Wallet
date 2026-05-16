"""
Node health router: /nodes/* endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, status

router = APIRouter(prefix="/nodes", tags=["Nodes"])


@router.get("/health")
async def get_node_health():
    """
    Get status of all 5 TSS nodes.
    
    Returns:
        nodes: list of {id, status, port, has_shares}
        dkg_active: bool
        threshold: int
        total: int
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Node health endpoint - implement in Phase 4"
    )
