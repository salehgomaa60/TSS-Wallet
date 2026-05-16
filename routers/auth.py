"""
Authentication router: /auth/* endpoints.

Handles user registration, login, invitations, and JWT management.
"""

import os
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from models import get_db
from models.company import Company
from models.user import User
from models.audit_log import AuditLog
from models.invitation import Invitation
from services.deployer import VaultDeployer
from services.relayer import Relayer

router = APIRouter(prefix="/auth", tags=["Authentication"])
security = HTTPBearer()

# Password hashing — using bcrypt directly (passlib breaks with bcrypt >= 4.x)
def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    try:
        return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())
    except Exception:
        return False

# JWT configuration
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))


# ── Pydantic Models ──────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    company_name: str
    threshold: int = 2
    total_signers: int = 3
    spending_limit_eth: float = 10.0


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class InviteRequest(BaseModel):
    email: EmailStr
    role: str  # OWNER, CEO, CFO, BOARD, EXECUTIVE
    node_id: int


class AcceptInviteRequest(BaseModel):
    token: str
    password: str
    full_name: str


# ── Helper Functions ─────────────────────────────────────────


def create_access_token(data: dict) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Get current user from JWT token."""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def run_dkg_for_company(company_id: str, threshold: int, total_nodes: int = 5) -> dict:
    """
    Retrieve (or restore) the shared TSS vault via the coordinator for this specific company.

    We call /wallet/setup without force_new so the coordinator reuses the persisted
    snapshot for this company_id if it exists, keeping the address stable.

    Returns dict with group_public_key, eth_address, and session_id.
    """
    import httpx

    coordinator_url = os.getenv("COORDINATOR_URL", "http://localhost:8000")

    async with httpx.AsyncClient(timeout=60.0) as client:
        # ── 1. Ensure "admin" user exists in the coordinator's in-memory store ──
        reg_resp = await client.post(
            f"{coordinator_url}/auth/register",
            json={"username": "admin", "password": "admin"}
        )
        # 409 means admin already exists — that's fine
        if reg_resp.status_code not in (200, 201, 409):
            raise RuntimeError(
                f"Could not register admin with coordinator: "
                f"{reg_resp.status_code} {reg_resp.text}"
            )

        # ── 2. Login to get a coordinator JWT ──
        login_resp = await client.post(
            f"{coordinator_url}/auth/login",
            json={"username": "admin", "password": "admin"}
        )
        if login_resp.status_code != 200:
            raise RuntimeError(
                f"Failed to authenticate with coordinator: "
                f"{login_resp.status_code} {login_resp.text}"
            )
        token = login_resp.json()["access_token"]

        # ── 3. Restore (or run) DKG — never force_new ──
        setup_resp = await client.post(
            f"{coordinator_url}/wallet/setup",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "company_id": company_id,
                "threshold": threshold,
                "total_nodes": total_nodes,
                "node_ids": list(range(1, total_nodes + 1)),
                "force_new": False,  # Reuse snapshot — keeps wallet address stable
            }
        )

        if setup_resp.status_code != 200:
            raise RuntimeError(
                f"DKG/wallet setup failed ({setup_resp.status_code}): {setup_resp.text}"
            )

        result = setup_resp.json()
        return {
            "eth_address": result["eth_address"],
            "group_public_key": result["group_public_key"],
            "session_id": result.get("session_id", "unknown")
        }


async def write_audit_log(
    db: AsyncSession,
    action: str,
    company_id: Optional[str] = None,
    user_id: Optional[str] = None,
    details: Optional[dict] = None,
    ip_address: Optional[str] = None
):
    """Write an entry to the audit log."""
    log = AuditLog(
        company_id=company_id,
        user_id=user_id,
        action=action,
        details=details or {},
        ip_address=ip_address
    )
    db.add(log)
    await db.commit()


# ── Endpoints ────────────────────────────────────────────────

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    req: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Register a new company with full vault setup.
    
    This endpoint:
    1. Creates company in DB
    2. Creates owner user in DB
    3. Runs DKG across TSS nodes for this company
    4. Deploys vault contract via deployer.py
    5. Saves contract_address and eth_address to company
    6. Writes COMPANY_CREATED to audit_log
    7. Returns JWT token + company details + vault address
    """
    # Check if email already exists
    result = await db.execute(select(User).where(User.email == req.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Check if company email already exists
    result = await db.execute(select(Company).where(Company.email == req.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Company with this email already exists")
    
    try:
        # Step 1: Create company in DB first (so we have its ID to pass to DKG)
        company = Company(
            name=req.company_name,
            email=req.email,
            password_hash="",  # Not used at company level
            threshold=req.threshold,
            total_signers=req.total_signers,
            contract_address="", # Will update
            eth_address="",      # Will update
            group_public_key={}, # Will update
            dkg_session_id="",   # Will update
            is_active=True
        )
        db.add(company)
        await db.flush()  # Generates company.id

        # Step 2: Run DKG to get TSS wallet address specific to this company
        dkg_result = await run_dkg_for_company(str(company.id), req.threshold, req.total_signers)
        eth_address = dkg_result["eth_address"]
        group_public_key = dkg_result["group_public_key"]
        dkg_session_id = dkg_result["session_id"]
        
        # Step 3: Deploy vault contract
        deployer = VaultDeployer()
        spending_limit_wei = int(req.spending_limit_eth * 1e18)

        # At registration time only the owner exists, so we pass the relayer
        # address as the sole initial executive.  The Solidity constructor
        # requires executives.length >= threshold, so we deploy with threshold=1
        # and call updateThreshold() later as more executives are invited.
        relayer_addr = os.getenv("RELAYER_ADDRESS", "")
        if not relayer_addr:
            raise HTTPException(
                status_code=500,
                detail="RELAYER_ADDRESS env var is not set. Cannot deploy vault."
            )

        contract_address = await deployer.deploy_vault(
            company_id=str(company.id),
            tss_wallet_address=eth_address,
            executive_addresses=[relayer_addr],   # Relayer is initial executive; owner added via invite
            executive_names=[req.full_name],
            threshold=1,          # Start at 1; raised to req.threshold once enough executives join
            spending_limit_wei=spending_limit_wei
        )
        
        # Update company with final addresses
        company.contract_address = contract_address
        company.eth_address = eth_address
        company.group_public_key = group_public_key
        company.dkg_session_id = dkg_session_id
        await db.flush()
        
        # Step 4: Create owner user
        user = User(
            company_id=company.id,
            email=req.email,
            password_hash=hash_password(req.password),
            full_name=req.full_name,
            role="OWNER",
            node_id=1,  # Owner gets node 1
            is_active=True
        )
        db.add(user)
        await db.flush()
        
        # Step 5: Write audit log
        await write_audit_log(
            db=db,
            action="COMPANY_CREATED",
            company_id=company.id,
            user_id=user.id,
            details={
                "company_name": req.company_name,
                "threshold": req.threshold,
                "total_signers": req.total_signers,
                "contract_address": contract_address,
                "eth_address": eth_address
            },
            ip_address=request.client.host if request.client else None
        )
        
        await db.commit()
        
        # Step 6: Create JWT token
        access_token = create_access_token({"sub": str(user.id)})
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "company": {
                "id": str(company.id),
                "name": company.name,
                "email": company.email,
                "threshold": company.threshold,
                "total_signers": company.total_signers,
                "contract_address": company.contract_address,
                "eth_address": company.eth_address,
            },
            "user": {
                "id": str(user.id),
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
                "node_id": user.node_id
            },
            "vault_address": contract_address,
            "tss_wallet_address": eth_address,
            "message": "Company registered successfully. Vault deployed to Sepolia."
        }
        
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        import traceback
        detail = f"Registration failed: {str(e)}\n{traceback.format_exc()}"
        print(f"[auth/register] ERROR: {detail}")
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")


@router.post("/login")
async def login(
    req: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Authenticate user and return JWT token.
    
    1. Find user by email
    2. Verify password hash
    3. Update last_login
    4. Write LOGIN to audit_log
    5. Return JWT
    """
    # Find user by email
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    if not user.is_active:
        raise HTTPException(status_code=401, detail="Account is deactivated")
    
    # Update last login
    user.last_login = datetime.now(timezone.utc)
    
    # Write audit log
    await write_audit_log(
        db=db,
        action="LOGIN",
        company_id=user.company_id,
        user_id=user.id,
        details={"email": req.email},
        ip_address=request.client.host if request.client else None
    )
    
    await db.commit()
    
    # Create JWT token
    access_token = create_access_token({"sub": str(user.id)})
    
    # Get company info
    result = await db.execute(select(Company).where(Company.id == user.company_id))
    company = result.scalar_one()
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "node_id": user.node_id,
            "company_id": str(user.company_id)
        },
        "company": {
            "id": str(company.id),
            "name": company.name,
            "contract_address": company.contract_address,
            "eth_address": company.eth_address,
        }
    }


@router.post("/invite")
async def invite_executive(
    req: InviteRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Invite a new executive to the company.
    
    Auth: JWT required, OWNER role only
    
    1. Generate secure random invitation token
    2. Save to invitations table with 7 day expiry
    3. Send invitation email via SendGrid
    4. Write USER_INVITED to audit_log
    """
    # Check if current user is OWNER
    if current_user.role != "OWNER":
        raise HTTPException(status_code=403, detail="Only owners can invite executives")
    
    # Check if email already exists
    result = await db.execute(select(User).where(User.email == req.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User with this email already exists")
    
    # Check if invitation already pending
    result = await db.execute(
        select(Invitation).where(
            Invitation.email == req.email,
            Invitation.company_id == current_user.company_id,
            Invitation.accepted_at.is_(None)
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Invitation already pending for this email")
    
    # Validate node_id
    if req.node_id < 1 or req.node_id > 5:
        raise HTTPException(status_code=400, detail="node_id must be between 1 and 5")
    
    # Check if node_id is already assigned in this company
    result = await db.execute(
        select(User).where(
            User.company_id == current_user.company_id,
            User.node_id == req.node_id
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Node {req.node_id} already assigned")
    
    # Generate invitation token
    token = secrets.token_urlsafe(32)
    
    # Create invitation
    invitation = Invitation(
        company_id=current_user.company_id,
        email=req.email,
        role=req.role,
        node_id=req.node_id,
        token=token,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        created_by=current_user.id
    )
    db.add(invitation)
    await db.flush()
    
    # Write audit log
    await write_audit_log(
        db=db,
        action="USER_INVITED",
        company_id=current_user.company_id,
        user_id=current_user.id,
        details={
            "invited_email": req.email,
            "role": req.role,
            "node_id": req.node_id,
            "invitation_id": str(invitation.id)
        },
        ip_address=request.client.host if request.client else None
    )
    
    await db.commit()
    
    # TODO: Send email notification (Phase 4 with SendGrid)
    
    return {
        "invitation_id": str(invitation.id),
        "token": token,
        "email": req.email,
        "role": req.role,
        "node_id": req.node_id,
        "expires_at": invitation.expires_at.isoformat(),
        "accept_url": f"/auth/accept-invite?token={token}"
    }


@router.post("/accept-invite")
async def accept_invite(
    req: AcceptInviteRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Accept an invitation and create user account.
    
    1. Validate invitation token (not expired, not used)
    2. Create user record with role and node_id from invitation
    3. Mark invitation as accepted
    4. Return JWT
    """
    # Find invitation
    result = await db.execute(
        select(Invitation).where(Invitation.token == req.token)
    )
    invitation = result.scalar_one_or_none()
    
    if not invitation:
        raise HTTPException(status_code=404, detail="Invalid invitation token")
    
    if invitation.accepted_at:
        raise HTTPException(status_code=400, detail="Invitation already used")
    
    if invitation.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invitation has expired")
    
    # Check if email already exists
    result = await db.execute(select(User).where(User.email == invitation.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User with this email already exists")
    
    # Create user
    user = User(
        company_id=invitation.company_id,
        email=invitation.email,
        password_hash=hash_password(req.password),
        full_name=req.full_name,
        role=invitation.role,
        node_id=invitation.node_id,
        is_active=True
    )
    db.add(user)
    await db.flush()
    
    # Mark invitation as accepted
    invitation.accepted_at = datetime.now(timezone.utc)
    
    # Write audit log
    await write_audit_log(
        db=db,
        action="USER_INVITED",  # Could be a separate action like USER_REGISTERED via invite
        company_id=invitation.company_id,
        user_id=user.id,
        details={
            "invitation_id": str(invitation.id),
            "role": invitation.role,
            "node_id": invitation.node_id
        },
        ip_address=request.client.host if request.client else None
    )
    
    await db.commit()
    
    # Create JWT token
    access_token = create_access_token({"sub": str(user.id)})
    
    # Get company info
    result = await db.execute(select(Company).where(Company.id == invitation.company_id))
    company = result.scalar_one()
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "node_id": user.node_id,
            "company_id": str(user.company_id)
        },
        "company": {
            "id": str(company.id),
            "name": company.name,
            "contract_address": company.contract_address,
            "eth_address": company.eth_address,
        },
        "message": "Invitation accepted. Welcome to TSS Vault!"
    }


# ── /auth/me ─────────────────────────────────────────────────────
@router.get("/me")
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns the authenticated user's profile AND their company's vault info.

    The frontend calls this on page load to refresh sessionStorage with the
    correct per-user vault address, making each browser tab completely
    independent (different tab = different token = different vault).
    """
    result = await db.execute(select(Company).where(Company.id == current_user.company_id))
    company = result.scalar_one_or_none()

    return {
        "user": {
            "id":         str(current_user.id),
            "email":      current_user.email,
            "full_name":  current_user.full_name,
            "role":       current_user.role,
            "node_id":    current_user.node_id,
            "company_id": str(current_user.company_id),
        },
        "company": {
            "id":               str(company.id)               if company else None,
            "name":             company.name                  if company else None,
            "eth_address":      company.eth_address           if company else None,
            "contract_address": company.contract_address      if company else None,
            "threshold":        company.threshold             if company else None,
            "total_signers":    company.total_signers         if company else None,
        },
    }
