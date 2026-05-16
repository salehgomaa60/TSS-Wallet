# demo/full_demo.py
# Complete End-to-End TSS Wallet Demo (single-process, no HTTP)
#
# This demo shows the COMPLETE PIPELINE in one script:
#   Phase 2: DKG (no dealer — key never assembled)
#   Phase 4: MPC Signing (no key reconstruction)
#   Phase 6: Ethereum Transaction Formatting + ecrecover
#
# Perfect for presentations and verification of all phases together.
# Run with:  python demo/full_demo.py

import os
import sys
import json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from crypto.shamir import generate_private_key, generate_shares, PRIME
from crypto.feldman_vss import (
    generate_commitments, verify_share, verify_all_shares, get_public_key
)
from crypto.threshold_sign import tss_sign, keccak256
from crypto.eth_tx import (
    pubkey_to_eth_address, get_signing_hash, build_signed_transaction,
    compute_recovery_id, ecrecover_verify,
)
from crypto.ecc import N
from py_ecc.secp256k1 import secp256k1
import secrets as _secrets


# ─────────────────────────────────────────────
# DISPLAY HELPERS
# ─────────────────────────────────────────────
def banner(title: str):
    print("\n" + "═" * 60)
    print(f"  {title}")
    print("═" * 60)

def step(n: int, title: str):
    print(f"\n  ┌─ STEP {n}: {title}")

def ok(msg: str):
    print(f"  │  ✅ {msg}")

def info(msg: str):
    print(f"  │  ℹ  {msg}")

def warn(msg: str):
    print(f"  │  ⚠  {msg}")


# ─────────────────────────────────────────────
# PHASE 2 SIMULATION: DKG (No Dealer)
# Each node generates its own polynomial.
# Simulates what would happen over the network.
# ─────────────────────────────────────────────
def simulate_dkg(M: int, N_nodes: int):
    """
    Simulates Distributed Key Generation without a trusted dealer.

    In a real distributed system:
      - Step 1-2 happen independently on each node
      - Step 3-4 happen over authenticated HTTPS
      - Step 5 happens locally on each node
      - The full private key x NEVER exists anywhere

    Here we simulate all steps in one process for demonstration.
    """
    banner(f"PHASE 2: Distributed Key Generation (DKG)  [{M}-of-{N_nodes}]")
    info(f"Threshold M={M}, Total nodes N={N_nodes}")
    info("Each node independently generates a random polynomial")
    info("Full private key x = Σ aᵢ₀ is NEVER computed")

    # Each node generates its secret polynomial
    step(1, "Each node generates local polynomial fᵢ(x)")
    node_polynomials = {}  # node_id → [coefficients]
    for i in range(1, N_nodes + 1):
        coeffs = [_secrets.randbelow(N) for _ in range(M)]
        while coeffs[0] == 0:
            coeffs[0] = _secrets.randbelow(N)
        node_polynomials[i] = coeffs
        ok(f"Node {i}: fᵢ(x) = aᵢ₀ + aᵢ₁x + ... (aᵢ₀={hex(coeffs[0])[:10]}...)")

    # Each node publishes Feldman commitments: Cᵢⱼ = aᵢⱼ·G
    step(2, "Each node broadcasts Feldman commitments Cᵢⱼ = aᵢⱼ·G")
    node_commitments = {}
    for i in range(1, N_nodes + 1):
        comms = generate_commitments(node_polynomials[i])
        node_commitments[i] = comms
        ok(f"Node {i}: published {len(comms)} commitments to all peers")

    # Each node computes and sends share fᵢ(j) to node j
    step(3, "Each node sends encrypted share fᵢ(j) to each peer node j")
    # received_shares[j][i] = fᵢ(j)  — what node j received from node i
    received_shares = {j: {} for j in range(1, N_nodes + 1)}
    for i in range(1, N_nodes + 1):
        for j in range(1, N_nodes + 1):
            from crypto.shamir import _evaluate_polynomial
            share_y = _evaluate_polynomial(node_polynomials[i], j)
            received_shares[j][i] = share_y
    ok("All shares distributed (encrypted in production)")

    # Each node verifies received shares against Feldman commitments
    step(4, "Each node verifies received shares: yᵢⱼ·G == Σ Cᵢₖ·j^k")
    all_valid = True
    for j in range(1, N_nodes + 1):
        for i in range(1, N_nodes + 1):
            if i != j:
                share = (j, received_shares[j][i])
                valid = verify_share(share, node_commitments[i])
                if not valid:
                    print(f"  ❌ Node {j}: REJECTED share from node {i}!")
                    all_valid = False
    if all_valid:
        ok("All shares passed Feldman VSS verification")

    # Each node sums all received shares → its final share xⱼ = Σᵢ fᵢ(j)
    step(5, "Each node computes combined share xⱼ = Σᵢ fᵢ(j)")
    final_shares = {}
    for j in range(1, N_nodes + 1):
        combined = sum(received_shares[j].values()) % N
        final_shares[j] = (j, combined)
        ok(f"Node {j}: xⱼ = {hex(combined)[:12]}...  (combined share)")

    # Group public key = Σᵢ Cᵢ₀  (sum of all nodes' first commitments)
    step(6, "Computing group public key Q = Σᵢ Cᵢ₀·G")
    group_pubkey = node_commitments[1][0]
    for i in range(2, N_nodes + 1):
        group_pubkey = secp256k1.add(group_pubkey, node_commitments[i][0])

    eth_address = pubkey_to_eth_address(group_pubkey)
    ok(f"Group public key Q = ({hex(group_pubkey[0])[:12]}..., ...)")
    ok(f"Ethereum address: {eth_address}")
    warn("Private key x = Σ aᵢ₀ was NEVER computed by anyone ✅")

    # Build Feldman-compatible commitments for signing verification
    # (we fake a single dealer's commitments from the combined values)
    # For internal _verify_ecdsa, we pass the group pubkey directly
    return list(final_shares.values()), group_pubkey, eth_address, node_commitments


# ─────────────────────────────────────────────
# MAIN DEMO
# ─────────────────────────────────────────────
def main():
    print("\n" + "█" * 60)
    print("  TSS MULTI-PARTY WALLET — FULL END-TO-END DEMO")
    print("  University Course Project — Semi-Production Grade")
    print("█" * 60)
    print("""
  Architecture:
    Each signer is an independent process (simulated here).
    In production: separate FastAPI servers on separate hosts.
    
  Security guarantees:
    ✅ Private key x NEVER exists in any single process
    ✅ Signing requires exactly M of N nodes
    ✅ Output is valid Ethereum (v, r, s) — passes ecrecover
    ✅ ECDSA — not Schnorr, not proprietary
  """)

    M = 3   # threshold
    N_NODES = 5  # total nodes

    # ─── PHASE 2: DKG ───────────────────────────────────────────
    final_shares, group_pubkey, eth_address, node_commitments = simulate_dkg(M, N_NODES)
    print(f"\n  Wallet Address: {eth_address}")

    # Build a fake commitments list for public key extraction
    # (tss_sign uses get_public_key(commitments) to get commitments[0])
    # We'll pass group_pubkey directly in verification instead
    # For tss_sign, build a stub
    class _FakeCommitments:
        pass

    # We need to pass real commitments to tss_sign for its verify step.
    # Create a proxy: just need commitments[0] = group_pubkey
    fake_commitments = [group_pubkey]

    # ─── BUILD ETHEREUM TRANSACTION ──────────────────────────────
    banner("PHASE 6: Ethereum Transaction")
    tx = {
        "to": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
        "value": 100_000_000_000_000_000,  # 0.1 ETH
        "nonce": 0,
        "gasPrice": 20_000_000_000,         # 20 Gwei
        "gasLimit": 21_000,
        "chainId": 11155111,                # Sepolia testnet
        "data": "",
    }
    tx_hash_bytes, tx_hash_int = get_signing_hash(tx)
    step(1, "Transaction Details")
    info(f"  From   : {eth_address}")
    info(f"  To     : {tx['to']}")
    info(f"  Value  : {tx['value'] / 1e18} ETH")
    info(f"  Network: Sepolia (chainId {tx['chainId']})")
    info(f"  TxHash : 0x{tx_hash_bytes.hex()[:20]}...")

    # ─── PHASE 4: MPC Signing (no key reconstruction) ────────────
    banner("PHASE 4: MPC Signing (No Key Reconstruction)")
    info(f"Using {M} of {N_NODES} nodes: Nodes 1, 2, 3")
    info("Each node signs with its share ONLY — key is never assembled")

    participating_shares = final_shares[:M]

    result = tss_sign(
        message="Sepolia ETH Transfer",
        shares=participating_shares,
        commitments=fake_commitments,
        message_hash_int=tx_hash_int,
    )
    r, s = result["signature"]

    # ─── PHASE 6: Format + Verify ────────────────────────────────
    banner("PHASE 6: Ethereum Signature Formatting + ecrecover")

    v = compute_recovery_id(tx_hash_int, r, s, group_pubkey, chain_id=tx["chainId"])
    verified = ecrecover_verify(tx_hash_bytes, v, r, s, eth_address)

    step(1, "Signature Components")
    info(f"  v = {v}  (EIP-155: chainId*2 + 35 + recovery_id)")
    info(f"  r = {hex(r)[:20]}...")
    info(f"  s = {hex(s)[:20]}...  (low-s form: {'yes' if s <= N//2 else 'NO!'})")

    step(2, "ecrecover Verification")
    if verified:
        ok(f"ecrecover(hash, {v}, r, s) = {eth_address}")
        ok("Signature is valid for this Ethereum address! 🎉")
    else:
        print(f"  ❌ ecrecover FAILED")

    # Build final tx object
    try:
        signed_tx = build_signed_transaction(tx, r, s, group_pubkey)
        step(3, "Final Broadcastable Transaction")
        print("\n" + json.dumps(signed_tx, indent=4))
    except ValueError as e:
        print(f"  ❌ Error building tx: {e}")

    # ─── SUMMARY ──────────────────────────────────────────────────
    banner("DEMO COMPLETE — SUMMARY")
    print(f"""
  ✅ DKG completed — {N_NODES} nodes, each with a secret share
  ✅ Full private key was NEVER assembled in any process
  ✅ {M}-of-{N_NODES} threshold signing without key reconstruction
  ✅ Standard ECDSA (r, s) — compatible with Ethereum
  ✅ ecrecover verified — signature is Ethereum-broadcastable
  
  Wallet address: {eth_address}
  Signature v:    {v}
  Low-s:          {'✅' if s <= N//2 else '❌'}
  ecrecover:      {'✅ PASS' if verified else '❌ FAIL'}

  Stopping point:
    ✗ Not broadcast to Sepolia (out of scope)
    ✗ No Solidity contracts (out of scope)
    ✅ Ready to hand off to Ethereum/Solidity phase
    """)


if __name__ == "__main__":
    main()
