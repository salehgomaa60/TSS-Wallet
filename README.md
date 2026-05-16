# TSS Vault — Threshold Signature Scheme Multi-Party Wallet

> The private key controlling this wallet never existed 
> as a complete value. Not during creation. Not during signing. Not ever.

A production-grade implementation of a threshold signature 
scheme wallet where M-of-N parties must cryptographically 
agree before any transaction executes. Built from mathematical 
primitives with no black-box cryptography libraries.

Mirrors the architecture used by Fireblocks and Coinbase 
Custody to protect institutional crypto assets.

---

## What This Is

A corporate treasury wallet where:

- The private key is **never assembled** at any point
- **5 independent nodes** each hold one mathematical share
- Any **3 of 5** must collaborate to sign a transaction
- Executives log in with **email and password** — no MetaMask
- A **smart contract** on Ethereum enforces every rule
- Every action produces an **immutable on-chain audit trail**

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│              React Frontend                     │
│   Login · Dashboard · Approve · Audit Log       │
└─────────────────┬───────────────────────────────┘
                  │ JWT
┌─────────────────▼───────────────────────────────┐
│           FastAPI Coordinator                   │
│           (port 8000)                           │
│   Orchestrates DKG and MPC signing              │
│   Holds zero key material                       │
└──────┬──────────┬──────────┬────────────────────┘
       │          │          │
  ┌────▼──┐  ┌────▼──┐  ┌────▼──┐
  │Node 1 │  │Node 2 │  │Node 3 │  ... Node 4, 5
  │Share 1│  │Share 2│  │Share 3│
  └───────┘  └───────┘  └───────┘
                  │
┌─────────────────▼───────────────────────────────┐
│         VaultContract.sol (Sepolia)             │
│   ecrecover · M-of-N enforcement · Auto-execute │
└─────────────────────────────────────────────────┘
```

---

## Cryptographic Stack

### Layer 1 — Primitives (Python, from scratch)

| Module | What It Does |
|---|---|
| `crypto/ecc.py` | secp256k1 elliptic curve arithmetic — point addition, scalar multiplication, key generation |
| `crypto/shamir.py` | Shamir's Secret Sharing over GF(N) — polynomial split and Lagrange reconstruction |
| `crypto/feldman_vss.py` | Feldman VSS commitments (aᵢ·G) — share verification without revealing secrets |
| `crypto/threshold_sign.py` | Threshold ECDSA — partial signatures per node, aggregation without key reconstruction |

### Layer 2 — Distributed Protocol (FastAPI)

| Component | Role |
|---|---|
| `nodes/coordinator.py` | Orchestrates DKG and MPC signing sessions |
| `nodes/node_app.py` | Independent signer node — holds one share per company |
| `services/deployer.py` | Automatically deploys VaultContract.sol per company |
| `services/relayer.py` | Broadcasts transactions — pays gas so users never need ETH |

### Layer 3 — Blockchain (Solidity)

| Contract | Role |
|---|---|
| `contracts/VaultContract.sol` | Per-company vault — proposeTransaction, approveTransaction, ecrecover verification, auto-execute at threshold |

---

## How It Works

### Key Generation (DKG)

```
1. Each node generates a random polynomial locally
2. Nodes exchange Feldman VSS commitments (aᵢ·G)
3. Each node sends encrypted shares to every other node
4. Each node verifies received shares against commitments
5. Each node computes its final share: Sⱼ = Σ sᵢⱼ mod N
6. Group public key: Q = Σ Cᵢ₀ = K·G
7. Ethereum address: A = keccak256(Q)[12:]

Private key K = Σ aᵢ₀ — never computed by anyone.
```

### Signing (Threshold ECDSA)

```
1. M nodes each generate ephemeral nonce kᵢ
2. Nodes broadcast nonce commitments Rᵢ = kᵢ·G
3. Combined nonce: R = ΣRᵢ, r = R.x mod N
4. Each node computes partial signature:
   σᵢ = kᵢ⁻¹(m + r·λᵢ·Sᵢ) mod N
5. Coordinator aggregates: s = Σσᵢ mod N
6. Final signature: (v, r, s) — EIP-155 formatted
7. ecrecover(hash, v, r, s) == wallet address ✅

Private key never reconstructed during signing.
```

---

## Verified Output

```json
{
  "transaction": {
    "to": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
    "value": 100000000000000000,
    "chainId": 11155111
  },
  "signature": {
    "v": 22310258,
    "r": "0xc60468ee6f46661361b399d12c3692c676ad55f2...",
    "s": "0x23fb1fcba7159687854e9d4575e6dc7121f273c1..."
  },
  "from": "0x1615Cf8927Fc0a45101273CC15aB416Fe6e0CD2E",
  "ecrecover_verified": true
}
```

---

## Features

```
✅ True DKG — private key never assembled anywhere
✅ Threshold ECDSA — no key reconstruction during signing
✅ Feldman VSS — cryptographic share verification
✅ EIP-155 — replay attack protection
✅ Smart contract per company — auto-deployed on signup
✅ Role based access — OWNER, CFO, EXECUTIVE, VIEWER
✅ Gas abstraction — relayer pays all gas fees
✅ Email notifications — approval requests and confirmations
✅ On-chain audit trail — every event permanent on Ethereum
✅ Multi-company isolation — separate DKG per company
✅ Non-sequential node selection — tested with nodes 1, 3, 5
```

---

## Tech Stack

```
Cryptography:   Python 3.11 (from scratch — no crypto libs)
Blockchain:     Solidity 0.8.19 · web3.py · Ethereum Sepolia
Backend:        FastAPI · SQLAlchemy · PostgreSQL · JWT
Frontend:       React · Tailwind CSS · ethers.js
Infrastructure: Hardhat · Infura · SendGrid · Railway
```

---

## Project Structure

```
tss_vault/
├── crypto/
│   ├── ecc.py                 # secp256k1 curve arithmetic
│   ├── shamir.py              # Shamir's Secret Sharing
│   ├── feldman_vss.py         # Feldman VSS verification
│   └── threshold_sign.py      # Threshold ECDSA signing
├── nodes/
│   ├── coordinator.py         # DKG + MPC orchestrator
│   └── node_app.py            # Independent signer node
├── contracts/
│   └── VaultContract.sol      # Per-company Ethereum vault
├── services/
│   ├── deployer.py            # Automatic contract deployment
│   ├── relayer.py             # Gas abstraction layer
│   └── email_service.py       # Notification system
├── routers/
│   ├── auth.py                # Registration, login, invite
│   ├── transactions.py        # Propose, approve, history
│   ├── companies.py           # Vault management
│   └── admin.py               # Platform administration
├── scripts/
│   ├── start_nodes.py         # Launch all nodes
│   └── deploy_contract.py     # Manual contract deployment
└── frontend/                  # React dashboard
```

---

## Quick Start

```bash
# Clone the repository
git clone https://github.com/yourusername/tss-vault.git
cd tss-vault

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Fill in: INFURA_URL, RELAYER_PRIVATE_KEY, 
#          DATABASE_URL, JWT_SECRET, SENDGRID_API_KEY

# Run database migrations
alembic upgrade head

# Start all nodes
python scripts/start_nodes.py --nodes 5

# In a new terminal — start the API
uvicorn nodes.coordinator:app --port 8000 --reload

# In a new terminal — start the frontend
cd frontend && npm install && npm run dev
```

---

## Running The Test Suite

```bash
# Unit tests — crypto primitives
pytest tests/test_shamir.py -v
pytest tests/test_feldman.py -v
pytest tests/test_ecc.py -v
pytest tests/test_threshold_sign.py -v

# Integration test — full API flow
python tests/test_api_integration.py

# Expected output:
# ✅ DKG Completed
# ✅ MPC Signing Completed  
# ✅ ecrecover verified
# ✅ All tests passed
```

---

## Security Model

```
Attack: Hacker compromises the database
Result: Gets emails and hashed passwords only
        Key shares live exclusively in TSS nodes
        Cannot produce valid signatures
        Cannot move any funds ✅

Attack: Hacker compromises 2 of 5 nodes
Result: Gets 2 key shares
        Needs 3 minimum (Shamir threshold)
        2 shares reveal mathematically nothing
        Cannot move any funds ✅

Attack: Rogue executive acts alone
Result: Controls 1 node only
        Needs M=3 nodes to collaborate
        Cannot produce valid signature alone
        Cannot move any funds ✅

Attack: Coordinator is compromised
Result: Availability failure — not security failure
        Coordinator holds zero key material
        Cannot sign anything without node collaboration
        Funds remain safe — system temporarily paused ✅
```

---

## Known Limitations

```
1. Coordinator single point of failure (liveness)
   The coordinator can cause downtime but not theft.
   Production fix: BFT coordinator cluster (Raft consensus)
   or peer-to-peer FROST protocol.

2. Simplified nonce protocol
   Production TSS (GG18, FROST) uses zero-knowledge proofs
   during nonce sharing to prevent malicious partial
   signatures from leaking key material.
   This is acknowledged and documented as future work.

3. Simulated node separation
   Nodes run on the same machine on different ports.
   Production deployment: separate servers, separate regions.
```

---

## Academic Context

This project implements the cryptographic architecture 
described in:

- Shamir, A. (1979). *How to share a secret*
- Feldman, P. (1987). *A practical scheme for non-interactive verifiable secret sharing*
- Gennaro, R. et al. (1999). *Secure distributed key generation for discrete-log based cryptosystems*
- Boneh, D. et al. (2018). *Threshold Signatures*

And mirrors the production architecture of:
- Fireblocks MPC-CMP protocol
- Coinbase Custody threshold signing
- Safe (Gnosis) multisig model

---

## License

MIT — use it, learn from it, build on it.

---

Open to internship opportunities in:
cryptography engineering · blockchain infrastructure · 
Web3 backend development

[LinkedIn](your-linkedin-url) · [Email](your-email)
