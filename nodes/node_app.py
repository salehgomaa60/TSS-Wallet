# nodes/node_app.py  — Multi-vault TSS Signer Node
#
# Each company gets its own DKG vault (unique key material).
# Shares are stored per-vault:  .node_{id}_share_{vault_id}.json
# The vault_id is the DKG session_id produced during wallet/setup.

import os
import json
import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
from typing import Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException, Depends, Header, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from jose import JWTError, jwt

from crypto.ecc import (
    generate_nonce, compute_nonce_point, lagrange_coefficient, N, G
)
from crypto.shamir import PRIME, _evaluate_polynomial
from crypto.feldman_vss import generate_commitments, verify_share, get_public_key
from crypto.threshold_sign import keccak256, create_partial_signature, _split_scalar_one
from crypto.eth_tx import pubkey_to_eth_address
from py_ecc.secp256k1 import secp256k1
from Crypto.Hash import keccak as _keccak


# ─────────────────────────────────────────────
# App Configuration
# ─────────────────────────────────────────────
NODE_ID   = int(os.getenv("NODE_ID",   "1"))
NODE_PORT = int(os.getenv("NODE_PORT", str(8000 + NODE_ID)))
JWT_SECRET    = os.getenv("JWT_SECRET", f"node{NODE_ID}_secret_change_in_production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24

PROJECT_ROOT = Path(__file__).parent.parent


def _share_file(vault_id: str) -> Path:
    """Returns the per-vault share file path for this node."""
    return PROJECT_ROOT / f".node_{NODE_ID}_share_{vault_id}.json"


def _all_share_files() -> list[Path]:
    """Returns all share files for this node (one per vault)."""
    return list(PROJECT_ROOT.glob(f".node_{NODE_ID}_share_*.json"))


# ─────────────────────────────────────────────
# In-Memory Node State  (multi-vault)
# ─────────────────────────────────────────────
class NodeState:
    def __init__(self):
        self.node_id: int = NODE_ID
        # Multi-vault support — keyed by vault_id (= DKG session_id)
        self.shares: dict = {}              # vault_id -> (index, value)
        self.group_public_keys: dict = {}   # vault_id -> (gx, gy)
        # Signing nonces keyed by signing session_id
        self.signing_nonces: dict = {}      # sign_session_id -> nonce_dict
        # DKG ephemeral state (overwritten each DKG round)
        self.dkg_session: Optional[dict] = None
        self.commitments: Optional[list] = None
        self.received_dkg_shares: dict = {}
        self.received_commitments: dict = {}
        # Auth
        self.users: dict = {}
        self.user_node: dict = {}


state = NodeState()


# ─────────────────────────────────────────────
# Share Persistence
# ─────────────────────────────────────────────
def _save_share(share: tuple, group_public_key: tuple, eth_address: str, vault_id: str):
    """Persists a vault's Shamir share to .node_{id}_share_{vault_id}.json"""
    data = {
        "vault_id": vault_id,
        "node_id": NODE_ID,
        "share_index": share[0],
        "share_value": hex(share[1]),
        "group_public_key": {
            "x": hex(group_public_key[0]),
            "y": hex(group_public_key[1]),
        },
        "eth_address": eth_address,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    path = _share_file(vault_id)
    path.write_text(json.dumps(data, indent=2))
    print(f"[node-{NODE_ID}] Share persisted: {path}")


def _load_all_shares() -> int:
    """Loads ALL vault shares from disk on startup. Returns count loaded."""
    count = 0
    for path in _all_share_files():
        try:
            data = json.loads(path.read_text())
            required = {"share_index", "share_value", "group_public_key", "eth_address"}
            if not required.issubset(data.keys()):
                continue
            # Derive vault_id from filename or stored field
            vault_id = data.get("vault_id") or path.stem.split(f"_share_", 1)[-1]
            share_index = data["share_index"]
            share_value = int(data["share_value"], 16)
            state.shares[vault_id] = (share_index, share_value)
            gx = int(data["group_public_key"]["x"], 16)
            gy = int(data["group_public_key"]["y"], 16)
            state.group_public_keys[vault_id] = (gx, gy)
            count += 1
            print(f"[node-{NODE_ID}] ✅ Loaded vault {vault_id[:12]}... → {data['eth_address']}")
        except Exception as e:
            print(f"[node-{NODE_ID}] Warning: could not load {path.name} — {e}")
    return count


# ─────────────────────────────────────────────
# Lifespan
# ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    count = _load_all_shares()
    if count:
        print(f"[node-{NODE_ID}] Ready — {count} vault(s) loaded from disk.")
    else:
        print(f"[node-{NODE_ID}] No shares on disk. Run DKG via coordinator /wallet/setup")
    yield
    print(f"[node-{NODE_ID}] Shutting down.")


app = FastAPI(
    title=f"TSS Signer Node {NODE_ID}",
    description=(
        f"Threshold Signature Scheme — Signer Node {NODE_ID}. "
        "Multi-vault: holds one Shamir share per vault. Key NEVER reconstructed."
    ),
    version="3.0.0",
    lifespan=lifespan,
)

from fastapi.responses import JSONResponse
import traceback

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    print(f"[node-{NODE_ID}] ERROR: {exc}")
    traceback.print_exc()
    return JSONResponse(status_code=500, content={"detail": str(exc), "traceback": traceback.format_exc()})

security = HTTPBearer()


# ─────────────────────────────────────────────
# JWT Auth
# ─────────────────────────────────────────────
def create_jwt_token(username: str) -> str:
    expiry = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS)
    return jwt.encode(
        {"sub": username, "node_id": NODE_ID, "exp": expiry,
         "iat": datetime.now(timezone.utc)},
        JWT_SECRET, algorithm=JWT_ALGORITHM,
    )


def verify_jwt_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    try:
        return jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid or expired JWT: {e}")


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


# ─────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────
class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str

class DKGInitRequest(BaseModel):
    session_id: str
    threshold: int
    total_nodes: int
    node_ids: list[int]

class CommitmentPayload(BaseModel):
    session_id: str
    sender_node_id: int
    commitments: list[list[int]]
    jwt_token: str

class SharePayload(BaseModel):
    session_id: str
    sender_node_id: int
    encrypted_share_y: str
    nonce_mask: str
    jwt_token: str

class DKGFinalizeRequest(BaseModel):
    session_id: str

class NonceRequest(BaseModel):
    session_id: str       # signing session id (unique per sign attempt)
    vault_id: str         # which vault's share to use (= DKG session_id)
    message_hash_hex: str

class PartialSigRequest(BaseModel):
    session_id: str       # signing session id
    vault_id: str         # which vault's share to use
    message_hash_hex: str
    r: int
    k_inv: int
    all_signer_indices: list[int]
    mu_i: int


# ─────────────────────────────────────────────
# Auth Endpoints
# ─────────────────────────────────────────────
@app.post("/auth/register")
async def register(req: RegisterRequest):
    if req.username in state.users:
        raise HTTPException(status_code=409, detail="Username already registered")
    state.users[req.username] = _hash_password(req.password)
    state.user_node[req.username] = NODE_ID
    return {"status": "registered", "username": req.username, "node_id": NODE_ID}


@app.post("/auth/login")
async def login(req: LoginRequest):
    stored_hash = state.users.get(req.username)
    if stored_hash is None or stored_hash != _hash_password(req.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"access_token": create_jwt_token(req.username), "token_type": "bearer"}


# ─────────────────────────────────────────────
# DKG Endpoints
# ─────────────────────────────────────────────
@app.post("/dkg/init")
async def dkg_init(req: DKGInitRequest, auth: dict = Depends(verify_jwt_token)):
    import secrets as _secrets
    M = req.threshold
    coefficients = [_secrets.randbelow(N) for _ in range(M)]
    while coefficients[0] == 0:
        coefficients[0] = _secrets.randbelow(N)
    commitments = generate_commitments(coefficients)
    shares_for_nodes = {nid: _evaluate_polynomial(coefficients, nid) for nid in req.node_ids}

    state.dkg_session = {
        "session_id": req.session_id,
        "threshold": M,
        "total_nodes": req.total_nodes,
        "node_ids": req.node_ids,
        "coefficients": coefficients,
        "commitments": commitments,
        "shares_for_nodes": shares_for_nodes,
    }
    state.received_dkg_shares = {}
    state.received_commitments = {}
    state.received_commitments[NODE_ID] = commitments

    return {"status": "dkg_initialized", "session_id": req.session_id, "node_id": NODE_ID}


@app.get("/dkg/commitment/{session_id}")
async def get_dkg_commitment(session_id: str, auth: dict = Depends(verify_jwt_token)):
    if state.dkg_session is None or state.dkg_session["session_id"] != session_id:
        raise HTTPException(status_code=404, detail="No active DKG session")
    serialized = [[c[0], c[1]] for c in state.dkg_session["commitments"]]
    return {"session_id": session_id, "node_id": NODE_ID, "commitments": serialized}


@app.post("/dkg/receive_commitment")
async def receive_commitment(payload: CommitmentPayload, auth: dict = Depends(verify_jwt_token)):
    state.received_commitments[payload.sender_node_id] = [tuple(c) for c in payload.commitments]
    return {"status": "commitment_received", "from_node": payload.sender_node_id, "to_node": NODE_ID}


@app.post("/dkg/receive_share")
async def receive_share(payload: SharePayload, auth: dict = Depends(verify_jwt_token)):
    sender_commitments = state.received_commitments.get(payload.sender_node_id)
    if sender_commitments is None:
        raise HTTPException(
            status_code=422,
            detail=f"No commitments from node {payload.sender_node_id} — commitments must arrive first."
        )
    enc_bytes  = bytes.fromhex(payload.encrypted_share_y)
    mask_bytes = bytes.fromhex(payload.nonce_mask)
    share_y    = int.from_bytes(bytes(a ^ b for a, b in zip(enc_bytes, mask_bytes)), 'big')
    share = (NODE_ID, share_y)
    if not verify_share(share, sender_commitments):
        raise HTTPException(
            status_code=422,
            detail=f"Share from node {payload.sender_node_id} FAILED Feldman VSS! DKG aborted."
        )
    state.received_dkg_shares[payload.sender_node_id] = share_y
    return {"status": "share_verified", "from_node": payload.sender_node_id, "to_node": NODE_ID}


@app.post("/dkg/finalize")
async def dkg_finalize(req: DKGFinalizeRequest, auth: dict = Depends(verify_jwt_token)):
    if state.dkg_session is None:
        raise HTTPException(status_code=400, detail="No active DKG session")

    session  = state.dkg_session
    node_ids = session["node_ids"]

    own_share_y = session["shares_for_nodes"][NODE_ID]
    all_share_y = [own_share_y] + [
        state.received_dkg_shares[nid]
        for nid in node_ids
        if nid != NODE_ID and nid in state.received_dkg_shares
    ]

    if len(all_share_y) < session["total_nodes"]:
        missing = [nid for nid in node_ids if nid != NODE_ID and nid not in state.received_dkg_shares]
        raise HTTPException(status_code=400, detail=f"Missing shares from nodes: {missing}")

    combined_share_y = sum(all_share_y) % N
    vault_id = req.session_id   # DKG session_id IS the vault_id
    state.shares[vault_id] = (NODE_ID, combined_share_y)

    all_first_commitments = [
        state.received_commitments[nid][0]
        for nid in node_ids
        if nid in state.received_commitments
    ]
    group_pubkey = all_first_commitments[0]
    for c in all_first_commitments[1:]:
        group_pubkey = secp256k1.add(group_pubkey, c)

    state.group_public_keys[vault_id] = group_pubkey
    state.commitments = session["commitments"]

    eth_address = pubkey_to_eth_address(group_pubkey)
    _save_share(state.shares[vault_id], group_pubkey, eth_address, vault_id)

    return {
        "status": "dkg_complete",
        "node_id": NODE_ID,
        "vault_id": vault_id,
        "group_public_key": {"x": hex(group_pubkey[0]), "y": hex(group_pubkey[1])},
        "eth_address": eth_address,
        "share_persisted": True,
    }


# ─────────────────────────────────────────────
# MPC Signing Endpoints
# ─────────────────────────────────────────────
@app.post("/sign/nonce")
async def sign_nonce(req: NonceRequest, auth: dict = Depends(verify_jwt_token)):
    share = state.shares.get(req.vault_id)
    if share is None:
        raise HTTPException(
            status_code=400,
            detail=f"Node has no share for vault {req.vault_id}. Run DKG first."
        )

    ki = generate_nonce()
    Ri = compute_nonce_point(ki)

    state.signing_nonces[req.session_id] = {
        "vault_id": req.vault_id,
        "message_hash_hex": req.message_hash_hex,
        "private_nonce": ki,
        "public_nonce": Ri,
    }

    return {
        "session_id": req.session_id,
        "node_id": NODE_ID,
        "public_nonce": {"x": hex(Ri[0]), "y": hex(Ri[1])},
        "private_nonce_for_coordinator": ki,
    }


@app.post("/sign/partial")
async def sign_partial(req: PartialSigRequest, auth: dict = Depends(verify_jwt_token)):
    share = state.shares.get(req.vault_id)
    if share is None:
        raise HTTPException(status_code=400, detail=f"Node has no share for vault {req.vault_id}")

    nonce = state.signing_nonces.get(req.session_id)
    if nonce is None or nonce.get("vault_id") != req.vault_id:
        raise HTTPException(status_code=400, detail="No nonce for this signing session / vault mismatch")
    if nonce["message_hash_hex"] != req.message_hash_hex:
        raise HTTPException(status_code=400, detail="Message hash mismatch")

    message_hash = int(req.message_hash_hex, 16) % N
    partial = create_partial_signature(
        signer_index=NODE_ID,
        share=share,
        private_nonce=nonce["private_nonce"],
        k_inv=req.k_inv,
        r=req.r,
        message_hash=message_hash,
        all_signer_indices=req.all_signer_indices,
        mu_i=req.mu_i,
    )

    state.signing_nonces.pop(req.session_id, None)
    return {"session_id": req.session_id, "node_id": NODE_ID, "partial_sig": partial["partial_sig"]}


# ─────────────────────────────────────────────
# Utility Endpoints
# ─────────────────────────────────────────────
@app.get("/health")
async def health():
    return {
        "status": "online",
        "node_id": NODE_ID,
        "port": NODE_PORT,
        "vault_count": len(state.shares),
        "vault_ids": list(state.shares.keys()),
        "version": "3.0.0",
    }


@app.get("/share/status")
async def share_status(auth: dict = Depends(verify_jwt_token)):
    return {
        "node_id": NODE_ID,
        "vault_count": len(state.shares),
        "vaults": [
            {
                "vault_id": vid,
                "eth_address": pubkey_to_eth_address(state.group_public_keys[vid])
                    if vid in state.group_public_keys else None,
                "share_on_disk": _share_file(vid).exists(),
            }
            for vid in state.shares
        ],
    }


@app.get("/dkg/shares_for_distribution/{session_id}")
async def get_shares_for_distribution(session_id: str, auth: dict = Depends(verify_jwt_token)):
    if state.dkg_session is None or state.dkg_session["session_id"] != session_id:
        raise HTTPException(status_code=404, detail="No active DKG session")

    shares_data = {}
    for nid, share_y in state.dkg_session["shares_for_nodes"].items():
        if nid == NODE_ID:
            continue
        share_y_bytes = share_y.to_bytes(32, 'big')
        mask      = secrets.token_bytes(32)
        encrypted = bytes(a ^ b for a, b in zip(share_y_bytes, mask))
        shares_data[str(nid)] = {"encrypted": encrypted.hex(), "mask": mask.hex()}

    return {"session_id": session_id, "sender_node_id": NODE_ID, "shares": shares_data}


@app.get("/public_key")
async def get_group_public_key(
    vault_id: str = Query(..., description="The vault/DKG session ID"),
    auth: dict = Depends(verify_jwt_token),
):
    gpk = state.group_public_keys.get(vault_id)
    if gpk is None:
        raise HTTPException(status_code=404, detail=f"No group public key for vault {vault_id}. Run DKG first.")
    return {
        "node_id": NODE_ID,
        "vault_id": vault_id,
        "group_public_key": {"x": hex(gpk[0]), "y": hex(gpk[1])},
        "eth_address": pubkey_to_eth_address(gpk),
    }
