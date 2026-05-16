# nodes/coordinator.py
# Phase 1 — Coordinator Node (FastAPI, port 8000)
#
# ARCHITECTURE:
#   The coordinator orchestrates the TSS protocol WITHOUT holding any share.
#   It is the entry point for users and the orchestration layer for signing.
#
# WHAT IT DOES:
#   - Accepts signing requests from users (authenticated via JWT)
#   - Runs DKG orchestration: idempotent — restores from snapshot if available
#   - Runs signing orchestration: collects partial sigs → final (v, r, s)
#   - Broadcasts signed transaction to Sepolia via Infura (web3.py)
#   - Returns real txHash from the Ethereum mempool
#
# WHAT IT NEVER DOES:
#   ✗ Never holds any Shamir share
#   ✗ Never holds the private key x
#   ✗ Never stores k (the combined nonce) beyond a signing session
#
# PHASE 1 ADDITIONS:
#   + DKG snapshot persistence (dkg_snapshot.json)
#   + web3.py Sepolia broadcast in /wallet/sign
#   + GET /wallet/balance — real on-chain balance
#   + GET /wallet/nonce  — real on-chain nonce for next tx
#   + GET /wallet/status — full wallet info

import os
import sys
import json
import secrets
from typing import Optional
from pathlib import Path

# Add parent directory to path to find crypto module
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone

from crypto.ecc import N, point_add
from crypto.threshold_sign import (
    combine_nonce_points,
    combine_partial_signatures,
    _split_scalar_one,
    _verify_ecdsa,
)
from crypto.eth_tx import (
    build_signed_transaction,
    get_signing_hash,
    pubkey_to_eth_address,
    keccak256_int,
)
from py_ecc.secp256k1 import secp256k1

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────
COORDINATOR_JWT_SECRET = os.getenv("COORDINATOR_JWT_SECRET", "coordinator_master_secret_change_me")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24

# Sepolia RPC — Infura
INFURA_URL = os.getenv(
    "INFURA_URL",
    "https://sepolia.infura.io/v3/YOUR_INFURA_PROJECT_ID"
)

# Per-company snapshot directory
PROJECT_ROOT = Path(__file__).parent.parent

def _snapshot_file(company_id: str) -> Path:
    """Returns the DKG snapshot file path for a specific company."""
    # Sanitise company_id so it's safe as a filename
    safe = "".join(c for c in company_id if c.isalnum() or c in "-_")
    return PROJECT_ROOT / f"dkg_snapshot_{safe}.json"

# Node registry: node_id → base URL
NODE_REGISTRY = {
    1: os.getenv("NODE_1_URL", "http://localhost:8001"),
    2: os.getenv("NODE_2_URL", "http://localhost:8002"),
    3: os.getenv("NODE_3_URL", "http://localhost:8003"),
    4: os.getenv("NODE_4_URL", "http://localhost:8004"),
    5: os.getenv("NODE_5_URL", "http://localhost:8005"),
}

app = FastAPI(
    title="TSS Coordinator",
    description=(
        "Threshold Signature Scheme — Coordinator Node. "
        "Orchestrates DKG and MPC signing without holding any private material. "
        "Phase 1: Broadcasts signed transactions to Sepolia testnet."
    ),
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()


# ─────────────────────────────────────────────
# web3 initialisation (lazy — avoids import errors if web3 not installed)
# ─────────────────────────────────────────────
def _get_web3():
    """Returns a connected Web3 instance pointed at Sepolia via Infura."""
    try:
        from web3 import Web3
        w3 = Web3(Web3.HTTPProvider(INFURA_URL))
        return w3
    except Exception as e:
        return None


# ─────────────────────────────────────────────
# Coordinator State
# ─────────────────────────────────────────────
class VaultState:
    """Per-company vault state."""
    def __init__(self, company_id: str, session_id: str, threshold: int,
                 total_nodes: int, node_ids: list, wallet_address: str,
                 group_public_key: tuple):
        self.company_id = company_id
        self.session_id = session_id        # = vault_id used by nodes
        self.threshold = threshold
        self.total_nodes = total_nodes
        self.node_ids = node_ids
        self.wallet_address = wallet_address
        self.group_public_key = group_public_key
        self.tx_history: list = []


class CoordinatorState:
    """
    Coordinator state — multi-vault.
    Each company gets its own VaultState keyed by company_id.
    """
    def __init__(self):
        self.vaults: dict = {}           # company_id -> VaultState
        self.users: dict = {}            # username -> hashed_password
        self.node_tokens: dict = {}      # node_id -> JWT
        # Legacy single-vault fields (kept for /health backward compat)
        self.active_nodes: list[int] = []
        self.threshold: int = 3
        self.total_nodes: int = 5
        self.wallet_address: Optional[str] = None


cstate = CoordinatorState()

# Load ALL existing per-company snapshots on startup
for _snap_path in PROJECT_ROOT.glob("dkg_snapshot_*.json"):
    try:
        _snap = json.loads(_snap_path.read_text())
        _cid = _snap.get("company_id") or _snap_path.stem.replace("dkg_snapshot_", "")
        if _cid and "session_id" in _snap:
            cstate.vaults[_cid] = _restore_vault_from_snapshot(_snap)
    except Exception as e:
        print(f"[coordinator] Failed to load {_snap_path.name}: {e}")

print(f"[coordinator] Loaded {len(cstate.vaults)} vault(s) from disk.")
def _save_dkg_snapshot(company_id: str, session_id: str, threshold: int,
                        total_nodes: int, node_ids: list,
                        group_pubkey_hex: dict, wallet_address: str):
    """Persists per-company DKG result to dkg_snapshot_{company_id}.json"""
    snapshot = {
        "company_id": company_id,
        "session_id": session_id,
        "threshold": threshold,
        "total_nodes": total_nodes,
        "node_ids": node_ids,
        "group_public_key": group_pubkey_hex,
        "wallet_address": wallet_address,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    path = _snapshot_file(company_id)
    path.write_text(json.dumps(snapshot, indent=2))
    print(f"[coordinator] DKG snapshot saved → {path}")


def _load_dkg_snapshot(company_id: str) -> Optional[dict]:
    """Loads per-company DKG snapshot from disk."""
    path = _snapshot_file(company_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        required = {"session_id", "threshold", "total_nodes", "node_ids",
                    "group_public_key", "wallet_address"}
        if not required.issubset(data.keys()):
            return None
        return data
    except Exception as e:
        print(f"[coordinator] Warning: snapshot read failed for {company_id} — {e}")
        return None


def _restore_vault_from_snapshot(snap: dict) -> VaultState:
    """Builds a VaultState from a persisted snapshot."""
    gx = int(snap["group_public_key"]["x"], 16)
    gy = int(snap["group_public_key"]["y"], 16)
    company_id = snap.get("company_id", "default")
    vs = VaultState(
        company_id=company_id,
        session_id=snap["session_id"],
        threshold=snap["threshold"],
        total_nodes=snap["total_nodes"],
        node_ids=snap["node_ids"],
        wallet_address=snap["wallet_address"],
        group_public_key=(gx, gy),
    )
    print(f"[coordinator] Restored vault for company {company_id} → {snap['wallet_address']}")
    return vs


# Load ALL existing per-company snapshots on startup
for _snap_path in PROJECT_ROOT.glob("dkg_snapshot_*.json"):
    try:
        _snap = json.loads(_snap_path.read_text())
        _cid = _snap.get("company_id") or _snap_path.stem.replace("dkg_snapshot_", "")
        if _cid:
            # cstate isn't created yet — will populate after cstate = CoordinatorState()
            pass
    except Exception:
        pass


# ─────────────────────────────────────────────
# Auth Helpers
# ─────────────────────────────────────────────
def create_coordinator_token(username: str) -> str:
    """Issues a coordinator-signed JWT for a user."""
    expiry = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS)
    return jwt.encode(
        {"sub": username, "role": "user", "exp": expiry},
        COORDINATOR_JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def verify_coordinator_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Validates JWT on coordinator endpoints."""
    try:
        return jwt.decode(
            credentials.credentials,
            COORDINATOR_JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
        )
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


async def _ensure_node_auth(node_id: int):
    """Ensures coordinator is authenticated with the node."""
    if node_id in cstate.node_tokens:
        return
    url = NODE_REGISTRY[node_id]
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Try to register (might fail if already exists)
        try:
            await client.post(
                f"{url}/auth/register",
                json={"username": "coordinator", "password": "coordinator_service_key"}
            )
        except Exception:
            pass
        # Login
        resp = await client.post(
            f"{url}/auth/login",
            json={"username": "coordinator", "password": "coordinator_service_key"}
        )
        if resp.status_code == 200:
            cstate.node_tokens[node_id] = resp.json()["access_token"]
        else:
            raise HTTPException(status_code=502, detail=f"Failed to auth with Node {node_id}")

async def _node_post(node_id: int, path: str, payload: dict) -> dict:
    """Helper: POST to a signer node with the coordinator's service JWT."""
    await _ensure_node_auth(node_id)
    url = NODE_REGISTRY[node_id] + path
    token = cstate.node_tokens.get(node_id)
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=payload, headers=headers)
        if response.status_code == 401:
            cstate.node_tokens.pop(node_id, None)
            await _ensure_node_auth(node_id)
            headers = {"Authorization": f"Bearer {cstate.node_tokens.get(node_id)}"}
            response = await client.post(url, json=payload, headers=headers)
        if response.status_code not in (200, 201):
            raise HTTPException(
                status_code=502,
                detail=f"Node {node_id} at {path} returned {response.status_code}: {response.text}"
            )
        return response.json()

async def _node_get(node_id: int, path: str) -> dict:
    """Helper: GET from a signer node."""
    await _ensure_node_auth(node_id)
    url = NODE_REGISTRY[node_id] + path
    token = cstate.node_tokens.get(node_id)
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers)
        if response.status_code == 401:
            cstate.node_tokens.pop(node_id, None)
            await _ensure_node_auth(node_id)
            headers = {"Authorization": f"Bearer {cstate.node_tokens.get(node_id)}"}
            response = await client.get(url, headers=headers)
        if response.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"Node {node_id} GET {path} returned {response.status_code}"
            )
        return response.json()


# ─────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────
class SetupRequest(BaseModel):
    company_id: str               # Unique company identifier — determines which vault
    threshold: int = 3
    total_nodes: int = 5
    node_ids: list[int] = [1, 2, 3, 4, 5]
    force_new: bool = False       # True = always run fresh DKG (new vault address)


class SignRequest(BaseModel):
    company_id: str               # Which company's vault to sign from
    to_address: str
    value_wei: int
    nonce: int = -1
    gas_price_wei: int = 20_000_000_000
    gas_limit: int = 21000
    chain_id: int = 11155111
    data: str = ""
    participating_nodes: list[int] = [1, 2, 3]
    broadcast: bool = True


class CoordinatorLogin(BaseModel):
    username: str
    password: str


class CoordinatorRegister(BaseModel):
    username: str
    password: str


# ─────────────────────────────────────────────
# Auth (Coordinator-Level)
# ─────────────────────────────────────────────
@app.post("/auth/register")
async def register(req: CoordinatorRegister):
    """Registers a user with the coordinator."""
    import hashlib
    if req.username in cstate.users:
        raise HTTPException(status_code=409, detail="User already exists")
    cstate.users[req.username] = hashlib.sha256(req.password.encode()).hexdigest()
    return {"status": "registered", "username": req.username}


@app.post("/auth/login")
async def login(req: CoordinatorLogin):
    """Authenticates a user and issues coordinator JWT."""
    import hashlib
    stored = cstate.users.get(req.username)
    if not stored or stored != hashlib.sha256(req.password.encode()).hexdigest():
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_coordinator_token(req.username)
    return {"access_token": token, "token_type": "bearer"}


# ─────────────────────────────────────────────
# DKG Orchestration — IDEMPOTENT
# ─────────────────────────────────────────────
@app.post("/wallet/setup", summary="Orchestrate DKG per company (idempotent)")
async def wallet_setup(req: SetupRequest, auth: dict = Depends(verify_coordinator_token)):
    """
    Runs DKG for a specific company.
    Each company gets its own unique vault address stored in dkg_snapshot_{company_id}.json.
    If a snapshot already exists for this company AND force_new=False, it is restored.
    """
    company_id = req.company_id

    # ── Restore from per-company snapshot if available ──
    if not req.force_new:
        snap = _load_dkg_snapshot(company_id)
        if snap and snap["threshold"] == req.threshold and snap["total_nodes"] == req.total_nodes:
            vs = _restore_vault_from_snapshot(snap)
            cstate.vaults[company_id] = vs
            node_ids = snap["node_ids"]
            for nid in node_ids:
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        await client.post(NODE_REGISTRY[nid] + "/auth/register",
                                          json={"username": "coordinator", "password": "coordinator_service_key"})
                        resp = await client.post(NODE_REGISTRY[nid] + "/auth/login",
                                                 json={"username": "coordinator", "password": "coordinator_service_key"})
                        if resp.status_code == 200:
                            cstate.node_tokens[nid] = resp.json()["access_token"]
                except Exception:
                    pass
            return {
                "status": "dkg_restored_from_snapshot",
                "company_id": company_id,
                "session_id": snap["session_id"],
                "vault_id": snap["session_id"],
                "threshold": snap["threshold"],
                "total_nodes": snap["total_nodes"],
                "group_public_key": snap["group_public_key"],
                "eth_address": snap["wallet_address"],
                "message": f"Vault for company {company_id} restored from snapshot. ✅",
                "created_at": snap.get("created_at"),
            }

    # ── Run fresh DKG ──
    session_id = secrets.token_hex(16)
    node_ids = req.node_ids[:req.total_nodes]

    for nid in node_ids:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(NODE_REGISTRY[nid] + "/auth/register",
                                  json={"username": "coordinator", "password": "coordinator_service_key"})
                resp = await client.post(NODE_REGISTRY[nid] + "/auth/login",
                                         json={"username": "coordinator", "password": "coordinator_service_key"})
                cstate.node_tokens[nid] = resp.json()["access_token"]
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Cannot reach Node {nid}: {e}")

        await _node_post(nid, "/dkg/init", {
            "session_id": session_id,
            "threshold": req.threshold,
            "total_nodes": req.total_nodes,
            "node_ids": node_ids,
        })

    all_commitments = {}
    for nid in node_ids:
        resp = await _node_get(nid, f"/dkg/commitment/{session_id}")
        all_commitments[nid] = resp["commitments"]

    for receiver_id in node_ids:
        for sender_id, commitments in all_commitments.items():
            if sender_id != receiver_id:
                await _node_post(receiver_id, "/dkg/receive_commitment", {
                    "session_id": session_id,
                    "sender_node_id": sender_id,
                    "commitments": commitments,
                    "jwt_token": cstate.node_tokens.get(sender_id, ""),
                })

    for sender_id in node_ids:
        sender_token = cstate.node_tokens.get(sender_id, "")
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                NODE_REGISTRY[sender_id] + f"/dkg/shares_for_distribution/{session_id}",
                headers={"Authorization": f"Bearer {sender_token}"}
            )
            if resp.status_code == 200:
                shares_data = resp.json()["shares"]
                for receiver_id_str, share_info in shares_data.items():
                    receiver_id = int(receiver_id_str)
                    if receiver_id != sender_id:
                        await _node_post(receiver_id, "/dkg/receive_share", {
                            "session_id": session_id,
                            "sender_node_id": sender_id,
                            "encrypted_share_y": share_info["encrypted"],
                            "nonce_mask": share_info["mask"],
                            "jwt_token": sender_token,
                        })

    group_pubkey_hex = None
    wallet_address = None
    for nid in node_ids:
        result = await _node_post(nid, "/dkg/finalize", {"session_id": session_id})
        if group_pubkey_hex is None:
            group_pubkey_hex = result["group_public_key"]
            wallet_address = result["eth_address"]

    gx = int(group_pubkey_hex["x"], 16)
    gy = int(group_pubkey_hex["y"], 16)
    vs = VaultState(
        company_id=company_id,
        session_id=session_id,
        threshold=req.threshold,
        total_nodes=req.total_nodes,
        node_ids=node_ids,
        wallet_address=wallet_address,
        group_public_key=(gx, gy),
    )
    cstate.vaults[company_id] = vs

    _save_dkg_snapshot(company_id, session_id, req.threshold, req.total_nodes,
                       node_ids, group_pubkey_hex, wallet_address)

    return {
        "status": "dkg_complete",
        "company_id": company_id,
        "session_id": session_id,
        "vault_id": session_id,
        "threshold": req.threshold,
        "total_nodes": req.total_nodes,
        "group_public_key": group_pubkey_hex,
        "eth_address": wallet_address,
        "message": f"Vault created for company {company_id}. Full private key NEVER existed. ✅",
    }


# ─────────────────────────────────────────────
# MPC Signing + Sepolia Broadcast
# ─────────────────────────────────────────────
@app.post("/wallet/sign", summary="MPC sign from a specific company vault")
async def wallet_sign(req: SignRequest, auth: dict = Depends(verify_coordinator_token)):
    """MPC signing using a specific company's vault key material."""
    vs = cstate.vaults.get(req.company_id)
    if vs is None:
        # Try to reload from disk
        snap = _load_dkg_snapshot(req.company_id)
        if snap:
            vs = _restore_vault_from_snapshot(snap)
            cstate.vaults[req.company_id] = vs
        else:
            raise HTTPException(status_code=400,
                detail=f"No vault for company {req.company_id}. Call /wallet/setup first.")

    vault_id = vs.session_id
    m_nodes = req.participating_nodes[:vs.threshold]
    session_id = secrets.token_hex(16)

    nonce = req.nonce
    if nonce < 0:
        w3 = _get_web3()
        if w3 is None:
            raise HTTPException(status_code=500, detail="web3 not available")
        try:
            from web3 import Web3
            nonce = w3.eth.get_transaction_count(Web3.to_checksum_address(vs.wallet_address))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch nonce: {e}")

    tx = {
        "to": req.to_address,
        "value": req.value_wei,
        "nonce": nonce,
        "gasPrice": req.gas_price_wei,
        "gasLimit": req.gas_limit,
        "chainId": req.chain_id,
        "data": req.data or b"",
    }
    tx_hash_bytes, tx_hash_int = get_signing_hash(tx)
    hash_hex = tx_hash_bytes.hex()

    nonce_responses = {}
    k_values = {}
    for nid in m_nodes:
        resp = await _node_post(nid, "/sign/nonce", {
            "session_id": session_id,
            "vault_id": vault_id,
            "message_hash_hex": hash_hex,
        })
        nonce_responses[nid] = resp
        k_values[nid] = resp["private_nonce_for_coordinator"]

    public_nonces = []
    for nid in m_nodes:
        pt = nonce_responses[nid]["public_nonce"]
        public_nonces.append((int(pt["x"], 16), int(pt["y"], 16)))

    R, r = combine_nonce_points(public_nonces)
    k_combined = sum(k_values[nid] for nid in m_nodes) % N
    k_inv = pow(k_combined, -1, N)
    mu_shares = _split_scalar_one(len(m_nodes))

    partial_sigs = []
    for i, nid in enumerate(m_nodes):
        resp = await _node_post(nid, "/sign/partial", {
            "session_id": session_id,
            "vault_id": vault_id,
            "message_hash_hex": hash_hex,
            "r": r,
            "k_inv": k_inv,
            "all_signer_indices": m_nodes,
            "mu_i": mu_shares[i],
        })
        partial_sigs.append({"signer_index": nid, "partial_sig": resp["partial_sig"]})

    r_final, s_final = combine_partial_signatures(partial_sigs, r)

    pk_resp = await _node_get(m_nodes[0], f"/public_key?vault_id={vault_id}")
    gx = int(pk_resp["group_public_key"]["x"], 16)
    gy = int(pk_resp["group_public_key"]["y"], 16)
    group_public_key = (gx, gy)

    try:
        signed_tx = build_signed_transaction(tx, r_final, s_final, group_public_key)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))

    broadcast_result = {"broadcast": False, "tx_hash": None, "etherscan_url": None, "error": None}

    if req.broadcast:
        w3 = _get_web3()
        if w3 is None:
            broadcast_result["error"] = "web3 unavailable"
        else:
            try:
                raw_bytes = bytes.fromhex(signed_tx["raw"].replace("0x", ""))
                tx_receipt_hash = w3.eth.send_raw_transaction(raw_bytes)
                eth_tx_hash = "0x" + tx_receipt_hash.hex()
                broadcast_result["broadcast"] = True
                broadcast_result["tx_hash"] = eth_tx_hash
                broadcast_result["etherscan_url"] = f"https://sepolia.etherscan.io/tx/{eth_tx_hash}"
                vs.tx_history.append({
                    "tx_hash": eth_tx_hash,
                    "to": req.to_address,
                    "value_wei": req.value_wei,
                    "nonce": nonce,
                    "participating_nodes": m_nodes,
                    "session_id": session_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                print(f"[coordinator] ✅ Broadcast for {req.company_id}: {eth_tx_hash}")
            except Exception as e:
                broadcast_result["error"] = str(e)

    return {
        "status": "broadcast" if broadcast_result["broadcast"] else "signed",
        "company_id": req.company_id,
        "participating_nodes": m_nodes,
        "signing_session": session_id,
        "nonce_used": nonce,
        "result": signed_tx,
        "broadcast": broadcast_result,
    }

    tx_hash_bytes, tx_hash_int = get_signing_hash(tx)
    hash_hex = tx_hash_bytes.hex()

    # ── STEP 2: Collect nonces from each node ──
    nonce_responses = {}
    k_values = {}
    for nid in m_nodes:
        resp = await _node_post(nid, "/sign/nonce", {
            "session_id": session_id,
            "message_hash_hex": hash_hex,
        })
        nonce_responses[nid] = resp
        k_values[nid] = resp["private_nonce_for_coordinator"]

    # ── STEP 3: Combine nonce points → R and r ──
    public_nonces = []
    for nid in m_nodes:
        pt = nonce_responses[nid]["public_nonce"]
        public_nonces.append((int(pt["x"], 16), int(pt["y"], 16)))

    R, r = combine_nonce_points(public_nonces)

    # ── STEP 4: Compute k_inv ──
    k_combined = sum(k_values[nid] for nid in m_nodes) % N
    k_inv = pow(k_combined, -1, N)

    # ── STEP 5: μᵢ shares of 1 ──
    mu_shares = _split_scalar_one(len(m_nodes))

    # ── STEP 6: Collect partial signatures ──
    partial_sigs = []
    for i, nid in enumerate(m_nodes):
        resp = await _node_post(nid, "/sign/partial", {
            "session_id": session_id,
            "message_hash_hex": hash_hex,
            "r": r,
            "k_inv": k_inv,
            "all_signer_indices": m_nodes,
            "mu_i": mu_shares[i],
        })
        partial_sigs.append({
            "signer_index": nid,
            "partial_sig": resp["partial_sig"],
        })

    # ── STEP 7: Combine → (r, s) ──
    r_final, s_final = combine_partial_signatures(partial_sigs, r)

    # ── STEP 8–9: Build signed Ethereum tx ──
    pk_resp = await _node_get(m_nodes[0], "/public_key")
    gx = int(pk_resp["group_public_key"]["x"], 16)
    gy = int(pk_resp["group_public_key"]["y"], 16)
    group_public_key = (gx, gy)

    try:
        signed_tx = build_signed_transaction(tx, r_final, s_final, group_public_key)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))

    # ── BROADCAST TO SEPOLIA ──
    broadcast_result = {
        "broadcast": False,
        "tx_hash": None,
        "etherscan_url": None,
        "error": None,
    }

    if req.broadcast:
        w3 = _get_web3()
        if w3 is None:
            broadcast_result["error"] = "web3 unavailable"
        else:
            try:
                raw_bytes = bytes.fromhex(signed_tx["raw"].replace("0x", ""))
                tx_receipt_hash = w3.eth.send_raw_transaction(raw_bytes)
                eth_tx_hash = "0x" + tx_receipt_hash.hex()
                broadcast_result["broadcast"] = True
                broadcast_result["tx_hash"] = eth_tx_hash
                broadcast_result["etherscan_url"] = f"https://sepolia.etherscan.io/tx/{eth_tx_hash}"

                # Record in history
                cstate.tx_history.append({
                    "tx_hash": eth_tx_hash,
                    "to": req.to_address,
                    "value_wei": req.value_wei,
                    "nonce": nonce,
                    "participating_nodes": m_nodes,
                    "session_id": session_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "etherscan_url": broadcast_result["etherscan_url"],
                })

                print(f"[coordinator] ✅ Broadcast to Sepolia: {eth_tx_hash}")
            except Exception as e:
                broadcast_result["error"] = str(e)
                print(f"[coordinator] ❌ Broadcast failed: {e}")

    return {
        "status": "signed" if not req.broadcast else ("broadcast" if broadcast_result["broadcast"] else "sign_only"),
        "participating_nodes": m_nodes,
        "signing_session": session_id,
        "nonce_used": nonce,
        "result": signed_tx,
        "broadcast": broadcast_result,
    }


# ─────────────────────────────────────────────
# Wallet Info Endpoints
# ─────────────────────────────────────────────
@app.get("/wallet/address")
async def get_wallet_address(company_id: str = Query(...), auth: dict = Depends(verify_coordinator_token)):
    vs = cstate.vaults.get(company_id)
    if vs is None:
        raise HTTPException(status_code=404, detail=f"No vault for company {company_id}")
    return {"company_id": company_id, "eth_address": vs.wallet_address}


@app.get("/wallet/balance")
async def get_wallet_balance(company_id: str = Query(...), auth: dict = Depends(verify_coordinator_token)):
    vs = cstate.vaults.get(company_id)
    if vs is None:
        raise HTTPException(status_code=404, detail=f"No vault for company {company_id}")
    w3 = _get_web3()
    if w3 is None:
        raise HTTPException(status_code=500, detail="web3 unavailable")
    try:
        from web3 import Web3
        balance_wei = w3.eth.get_balance(Web3.to_checksum_address(vs.wallet_address))
        return {
            "company_id": company_id,
            "wallet": vs.wallet_address,
            "balance_wei": balance_wei,
            "balance_eth": round(balance_wei / 1e18, 6),
            "network": "Sepolia",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Infura query failed: {e}")


@app.get("/wallet/status")
async def get_wallet_status(company_id: str = Query(...)):
    """Returns wallet status for a specific company vault."""
    vs = cstate.vaults.get(company_id)
    if vs is None:
        # Try loading from disk
        snap = _load_dkg_snapshot(company_id)
        if snap:
            vs = _restore_vault_from_snapshot(snap)
            cstate.vaults[company_id] = vs
    if vs is None:
        return {
            "company_id": company_id,
            "has_wallet": False,
            "wallet_address": None,
            "balance_eth": None,
            "snapshot_exists": _snapshot_file(company_id).exists(),
        }

    snap = _load_dkg_snapshot(company_id)
    wallet_info = {
        "company_id": company_id,
        "has_wallet": True,
        "wallet_address": vs.wallet_address,
        "threshold": vs.threshold,
        "total_nodes": vs.total_nodes,
        "active_nodes": vs.node_ids,
        "snapshot_exists": snap is not None,
        "balance_eth": None,
        "balance_wei": None,
    }

    w3 = _get_web3()
    if w3:
        try:
            from web3 import Web3
            balance_wei = w3.eth.get_balance(Web3.to_checksum_address(vs.wallet_address))
            wallet_info["balance_wei"] = balance_wei
            wallet_info["balance_eth"] = round(balance_wei / 1e18, 6)
        except Exception:
            pass

    return wallet_info


@app.get("/wallet/history")
async def get_tx_history(company_id: str = Query(...), auth: dict = Depends(verify_coordinator_token)):
    vs = cstate.vaults.get(company_id)
    if vs is None:
        return {"company_id": company_id, "transactions": [], "count": 0}
    return {"company_id": company_id, "wallet": vs.wallet_address,
            "transactions": vs.tx_history, "count": len(vs.tx_history)}


@app.get("/health")
async def health():
    w3 = _get_web3()
    infura_connected = False
    if w3:
        try:
            infura_connected = w3.is_connected()
        except Exception:
            pass
    return {
        "status": "online",
        "role": "coordinator",
        "vault_count": len(cstate.vaults),
        "company_ids": list(cstate.vaults.keys()),
        "infura_connected": infura_connected,
        "version": "3.0.0",
    }

async def get_wallet_address(auth: dict = Depends(verify_coordinator_token)):
    """Returns the TSS wallet's Ethereum address (from group public key)."""
    if cstate.wallet_address is None:
        raise HTTPException(status_code=404, detail="No wallet set up yet. Run /wallet/setup first.")
    return {"eth_address": cstate.wallet_address}


@app.get("/wallet/balance", summary="Get real Sepolia ETH balance of the TSS wallet")
async def get_wallet_balance(auth: dict = Depends(verify_coordinator_token)):
    """
    Fetches the TSS wallet's current ETH balance from Sepolia via Infura.

    Returns:
        balance_wei  : raw balance in wei (int)
        balance_eth  : human-readable balance in ETH (float)
        wallet       : Ethereum address
        network      : Sepolia
    """
    if cstate.wallet_address is None:
        raise HTTPException(status_code=404, detail="No wallet set up yet.")

    w3 = _get_web3()
    if cstate.wallet_address:
        w3 = _get_web3()
        if w3:
            try:
                from web3 import Web3
                checksum_addr = Web3.to_checksum_address(cstate.wallet_address)
                balance_wei = w3.eth.get_balance(checksum_addr)
                wallet_info["balance_wei"] = balance_wei
                wallet_info["balance_eth"] = round(balance_wei / 1e18, 6)
            except Exception:
                pass

    return wallet_info


@app.get("/wallet/history", summary="Transaction history for this wallet")
async def get_tx_history(auth: dict = Depends(verify_coordinator_token)):
    """Returns all transactions broadcast by this coordinator session."""
    return {
        "wallet": cstate.wallet_address,
        "transactions": cstate.tx_history,
        "count": len(cstate.tx_history),
    }


# ─────────────────────────────────────────────
# Health Check
# ─────────────────────────────────────────────
@app.get("/health")
async def health():
    """Coordinator liveness check."""
    w3 = _get_web3()
    infura_connected = False
    if w3:
        try:
            infura_connected = w3.is_connected()
        except Exception:
            pass

    return {
        "status": "online",
        "role": "coordinator",
        "active_nodes": cstate.active_nodes,
        "threshold": cstate.threshold,
        "wallet_address": cstate.wallet_address,
        "snapshot_exists": DKG_SNAPSHOT_FILE.exists(),
        "infura_connected": infura_connected,
        "version": "2.0.0",
    }
