"""
Wallet proxy router: /wallet/* endpoints.

These endpoints proxy requests to the TSS coordinator (port 8000)
so the frontend only needs a single API origin (port 8006).
"""

import os
import httpx
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from routers.auth import get_current_user
from models.user import User

router = APIRouter(prefix="/wallet", tags=["Wallet"])

COORDINATOR_URL = os.getenv("COORDINATOR_URL", "http://localhost:8000")


# ── helpers ──────────────────────────────────────────────────

async def _get_coordinator_token() -> str:
    """Login to coordinator as internal service and return a JWT."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Register admin (safe to call repeatedly; 409 = already exists)
        await client.post(
            f"{COORDINATOR_URL}/auth/register",
            json={"username": "admin", "password": "admin"},
        )
        resp = await client.post(
            f"{COORDINATOR_URL}/auth/login",
            json={"username": "admin", "password": "admin"},
        )
        if resp.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"Could not authenticate with coordinator: {resp.text}",
            )
        return resp.json()["access_token"]


# ── /wallet/status ────────────────────────────────────────────

@router.get("/status")
async def wallet_status(current_user: User = Depends(get_current_user)):
    """
    Proxy to coordinator /wallet/status.
    Requires authentication to get the current user's company_id.
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{COORDINATOR_URL}/wallet/status",
                params={"company_id": str(current_user.company_id)}
            )
            return JSONResponse(status_code=resp.status_code, content=resp.json())
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="Coordinator is offline. Start nodes with: python scripts/start_nodes.py",
        )


# ── /wallet/address ───────────────────────────────────────────

@router.get("/address")
async def wallet_address(current_user: User = Depends(get_current_user)):
    """Proxy to coordinator /wallet/address (authenticated)."""
    try:
        token = await _get_coordinator_token()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{COORDINATOR_URL}/wallet/address",
                headers={"Authorization": f"Bearer {token}"},
                params={"company_id": str(current_user.company_id)},
            )
            return JSONResponse(status_code=resp.status_code, content=resp.json())
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Coordinator offline")


# ── /wallet/balance ───────────────────────────────────────────

@router.get("/balance")
async def wallet_balance(current_user: User = Depends(get_current_user)):
    """Proxy to coordinator /wallet/balance (authenticated)."""
    try:
        token = await _get_coordinator_token()
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{COORDINATOR_URL}/wallet/balance",
                headers={"Authorization": f"Bearer {token}"},
                params={"company_id": str(current_user.company_id)},
            )
            return JSONResponse(status_code=resp.status_code, content=resp.json())
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Coordinator offline")


# ── /wallet/sign ──────────────────────────────────────────────

class SignRequest(BaseModel):
    to_address: str
    value_wei: int
    nonce: int = -1
    gas_price_wei: int = 20_000_000_000
    gas_limit: int = 21000
    chain_id: int = 11155111
    data: str = ""
    participating_nodes: list[int] = [1, 2, 3]
    broadcast: bool = True


@router.post("/sign")
async def wallet_sign(
    req: SignRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Proxy to coordinator /wallet/sign (MPC signing + Sepolia broadcast).
    Requires JWT authentication on this side.
    """
    payload = req.model_dump()
    payload["company_id"] = str(current_user.company_id)

    try:
        token = await _get_coordinator_token()
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{COORDINATOR_URL}/wallet/sign",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
            return JSONResponse(status_code=resp.status_code, content=resp.json())
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="Coordinator is offline. Start nodes with: python scripts/start_nodes.py",
        )


# ── /wallet/history ───────────────────────────────────────────

@router.get("/history")
async def wallet_history(current_user: User = Depends(get_current_user)):
    """Proxy to coordinator /wallet/history."""
    try:
        token = await _get_coordinator_token()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{COORDINATOR_URL}/wallet/history",
                headers={"Authorization": f"Bearer {token}"},
                params={"company_id": str(current_user.company_id)},
            )
            return JSONResponse(status_code=resp.status_code, content=resp.json())
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Coordinator offline")
