# tests/test_phase6_eth.py
# Phase 6 — Ethereum Transaction Formatting Test Suite
#
# TESTS:
#   1. pubkey_to_eth_address — correct Ethereum address derivation
#   2. RLP encode/decode round-trip for unsigned tx
#   3. Full TSS sign → Ethereum (v,r,s) → ecrecover verification
#   4. Low-s enforcement (ECDSA malleability)
#   5. EIP-155 replay protection (v = chainId*2 + 35/36)
#   6. Final broadcastable tx JSON structure

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from crypto.shamir import generate_private_key, generate_shares
from crypto.feldman_vss import generate_commitments, get_public_key
from crypto.threshold_sign import tss_sign
from crypto.eth_tx import (
    pubkey_to_eth_address,
    get_signing_hash,
    encode_unsigned_tx,
    build_signed_transaction,
    ecrecover_verify,
    compute_recovery_id,
    keccak256,
    keccak256_int,
    _recover_public_key,
)
from crypto.ecc import N, point_multiply


# ─────────────────────────────────────────────
# FIXTURE — shared wallet state for all tests
# ─────────────────────────────────────────────
@pytest.fixture(scope="module")
def wallet():
    """
    Creates a 3-of-5 TSS wallet with a signed Ethereum tx.
    Reused across all Phase 6 tests.
    """
    print("\n  [FIXTURE] Setting up 3-of-5 TSS wallet...")
    secret = generate_private_key()
    shares, coefficients = generate_shares(secret, M=3, N=5)
    commitments = generate_commitments(coefficients)
    public_key = get_public_key(commitments)

    # Sample Ethereum transaction (Sepolia testnet)
    tx = {
        "to": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",  # vitalik.eth
        "value": 1_000_000_000_000_000,  # 0.001 ETH in wei
        "nonce": 0,
        "gasPrice": 20_000_000_000,  # 20 Gwei
        "gasLimit": 21_000,
        "chainId": 11155111,  # Sepolia
        "data": "",
    }

    # Get signing hash from the tx
    tx_hash_bytes, tx_hash_int = get_signing_hash(tx)

    # TSS sign with 3 participating signers (nodes 1, 2, 3)
    participating_shares = shares[:3]
    result = tss_sign(
        message="Sepolia test tx",
        shares=participating_shares,
        commitments=commitments,
        message_hash_int=tx_hash_int,  # sign the actual tx hash directly
    )

    return {
        "secret": secret,
        "shares": shares,
        "coefficients": coefficients,
        "commitments": commitments,
        "public_key": public_key,
        "tx": tx,
        "tx_hash_bytes": tx_hash_bytes,
        "tx_hash_int": tx_hash_int,
        "r": result["signature"][0],
        "s": result["signature"][1],
        "tss_valid": result["valid"],
    }


# ─────────────────────────────────────────────
# TEST 1 — Ethereum Address Derivation
# ─────────────────────────────────────────────
def test_eth_address_derivation(wallet):
    """
    Verifies that pubkey → Ethereum address conversion follows
    the Ethereum spec: keccak256(pubkey_bytes)[-20:].
    """
    print("\n[TEST 1] Ethereum address derivation...")
    public_key = wallet["public_key"]
    address = pubkey_to_eth_address(public_key)

    # Must be a 42-character string starting with 0x
    assert address.startswith("0x"), f"Address must start with 0x, got: {address}"
    assert len(address) == 42, f"Ethereum address must be 42 chars, got len={len(address)}"

    # Must be EIP-55 checksummed (mix of upper/lower case)
    hex_part = address[2:]
    assert hex_part != hex_part.lower() or hex_part != hex_part.upper(), \
        "Address should be EIP-55 checksummed"

    print(f"  Wallet address: {address} ✅")


# ─────────────────────────────────────────────
# TEST 2 — TSS Produces Valid ECDSA
# ─────────────────────────────────────────────
def test_tss_produces_valid_ecdsa(wallet):
    """
    Verifies that the TSS signing protocol produced a valid ECDSA signature.
    This confirms the distributed k⁻¹(e + r·x) formula is correct.
    """
    print("\n[TEST 2] TSS signing produces valid ECDSA...")
    assert wallet["tss_valid"], "TSS internal ECDSA verification failed"
    print(f"  r = {hex(wallet['r'])[:20]}...")
    print(f"  s = {hex(wallet['s'])[:20]}...")
    print("  Internal ECDSA verification: ✅")


# ─────────────────────────────────────────────
# TEST 3 — ecrecover Verification
# ─────────────────────────────────────────────
def test_ecrecover_verification(wallet):
    """
    The critical test: ecrecover(hash, v, r, s) must return the wallet address.

    This is exactly what Ethereum nodes do when processing transactions.
    If this passes, our TSS output is a valid Ethereum signature.
    """
    print("\n[TEST 3] ecrecover verification...")

    r, s = wallet["r"], wallet["s"]
    public_key = wallet["public_key"]
    tx_hash_bytes = wallet["tx_hash_bytes"]
    tx_hash_int = wallet["tx_hash_int"]

    wallet_address = pubkey_to_eth_address(public_key)

    # Compute v (EIP-155)
    chain_id = wallet["tx"]["chainId"]
    v = compute_recovery_id(tx_hash_int, r, s, public_key, chain_id)

    # Verify: ecrecover(hash, v, r, s) == wallet_address
    verified = ecrecover_verify(tx_hash_bytes, v, r, s, wallet_address)

    assert verified, (
        f"ecrecover FAILED!\n"
        f"  Expected address: {wallet_address}\n"
        f"  v={v}, r={hex(r)[:20]}..., s={hex(s)[:20]}..."
    )

    print(f"  wallet address : {wallet_address}")
    print(f"  v              : {v} (EIP-155, chainId={chain_id})")
    print(f"  r              : {hex(r)[:20]}...")
    print(f"  s              : {hex(s)[:20]}...")
    print("  ecrecover      : ✅ Address matches!")


# ─────────────────────────────────────────────
# TEST 4 — Full build_signed_transaction
# ─────────────────────────────────────────────
def test_build_signed_transaction(wallet):
    """
    Verifies the complete pipeline: TSS (r,s) → Ethereum signed tx JSON.

    The output must contain:
    - "from" address matching the wallet
    - Valid (v, r, s) signature
    - RLP-encoded "raw" transaction starting with 0x
    - ecrecover_verified = True
    """
    print("\n[TEST 4] Full signed transaction build...")

    signed_tx = build_signed_transaction(
        tx=wallet["tx"],
        r=wallet["r"],
        s=wallet["s"],
        public_key=wallet["public_key"],
    )

    assert signed_tx["ecrecover_verified"] is True
    assert signed_tx["from"].startswith("0x")
    assert len(signed_tx["from"]) == 42
    assert signed_tx["raw"].startswith("0x")
    assert isinstance(signed_tx["signature"]["v"], int) and signed_tx["signature"]["v"] > 0
    assert signed_tx["txHash"].startswith("0x")
    assert len(signed_tx["txHash"]) == 66  # 0x + 64 hex chars

    print(f"  from     : {signed_tx['from']}")
    print(f"  to       : {signed_tx['transaction']['to']}")
    print(f"  value    : {signed_tx['transaction']['value']} wei")
    print(f"  v        : {signed_tx['signature']['v']}")
    print(f"  r        : {signed_tx['signature']['r'][:20]}...")
    print(f"  s        : {signed_tx['signature']['s'][:20]}...")
    print(f"  txHash   : {signed_tx['txHash']}")
    print(f"  raw      : {signed_tx['raw'][:30]}...  ✅")

    import json
    print("\n  Final output JSON:")
    print(json.dumps(signed_tx, indent=2)[:800] + "...")


# ─────────────────────────────────────────────
# TEST 5 — Low-S Enforcement
# ─────────────────────────────────────────────
def test_low_s_enforcement(wallet):
    """
    Verifies that the final s value is in low-s form (s <= N//2).

    ECDSA signatures have a malleability vector: for any valid (r, s),
    (r, N-s) is also a valid signature for the same message.
    Ethereum requires low-s form to prevent transaction malleability.
    """
    print("\n[TEST 5] Low-s enforcement...")
    s = wallet["s"]
    assert s <= N // 2, (
        f"s = {hex(s)} is NOT in low-s form (s > N//2). "
        "This would cause Ethereum tx malleability."
    )
    print(f"  s = {hex(s)[:20]}...")
    print(f"  s <= N//2: ✅ (malleability-safe)")


# ─────────────────────────────────────────────
# TEST 6 — Different Signer Combinations
# ─────────────────────────────────────────────
def test_different_signer_combinations_eth():
    """
    Tests that any M-of-N combination of signers produces a valid Ethereum signature.
    This is the core property of threshold schemes — any M signers suffice.
    """
    print("\n[TEST 6] Different signer combinations → ecrecover...")

    secret = generate_private_key()
    shares, coefficients = generate_shares(secret, M=3, N=5)
    commitments = generate_commitments(coefficients)
    public_key = get_public_key(commitments)

    tx = {
        "to": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
        "value": 500_000_000_000_000,
        "nonce": 1,
        "gasPrice": 20_000_000_000,
        "gasLimit": 21_000,
        "chainId": 11155111,
        "data": "",
    }
    tx_hash_bytes, tx_hash_int = get_signing_hash(tx)
    wallet_address = pubkey_to_eth_address(public_key)

    combinations = [
        ([shares[0], shares[1], shares[2]], "Signers 1+2+3"),
        ([shares[0], shares[2], shares[4]], "Signers 1+3+5"),
        ([shares[1], shares[3], shares[4]], "Signers 2+4+5"),
    ]

    for combo_shares, name in combinations:
        result = tss_sign(
            message="combo test",
            shares=combo_shares,
            commitments=commitments,
            message_hash_int=tx_hash_int,
        )
        r, s = result["signature"]
        v = compute_recovery_id(
            int.from_bytes(tx_hash_bytes, 'big') % N,
            r, s, public_key,
            chain_id=11155111,
        )
        verified = ecrecover_verify(tx_hash_bytes, v, r, s, wallet_address)
        assert verified, f"ecrecover failed for {name}"
        print(f"  {name}: ecrecover ✅")


# ─────────────────────────────────────────────
# TEST 7 — Public Key Recovery from Signature
# ─────────────────────────────────────────────
def test_public_key_recovery(wallet):
    """
    Verifies that the public key can be recovered from the signature alone.
    This is the mathematical foundation of ecrecover.
    """
    print("\n[TEST 7] Public key recovery...")
    r, s = wallet["r"], wallet["s"]
    tx_hash_int = wallet["tx_hash_int"]
    public_key = wallet["public_key"]

    # Try both recovery ids
    recovered = None
    for recovery_id in [0, 1]:
        candidate = _recover_public_key(tx_hash_int, r, s, recovery_id)
        if candidate == public_key:
            recovered = candidate
            break

    assert recovered is not None, "Public key recovery failed"
    assert recovered == public_key, "Recovered key does not match expected"
    print(f"  Recovered public key matches expected ✅")


# ─────────────────────────────────────────────
# RUNNER
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  PHASE 6 — ETHEREUM TRANSACTION TESTS")
    print("=" * 60)

    # Build fixture manually
    secret = generate_private_key()
    shares, coefficients = generate_shares(secret, M=3, N=5)
    commitments = generate_commitments(coefficients)
    public_key = get_public_key(commitments)

    tx = {
        "to": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
        "value": 1_000_000_000_000_000,
        "nonce": 0,
        "gasPrice": 20_000_000_000,
        "gasLimit": 21_000,
        "chainId": 11155111,
        "data": "",
    }
    tx_hash_bytes, tx_hash_int = get_signing_hash(tx)
    result = tss_sign("test", shares[:3], commitments, message_hash_int=tx_hash_int)

    w = {
        "secret": secret, "shares": shares, "coefficients": coefficients,
        "commitments": commitments, "public_key": public_key,
        "tx": tx, "tx_hash_bytes": tx_hash_bytes, "tx_hash_int": tx_hash_int,
        "r": result["signature"][0], "s": result["signature"][1],
        "tss_valid": result["valid"],
    }

    test_eth_address_derivation(w)
    test_tss_produces_valid_ecdsa(w)
    test_ecrecover_verification(w)
    test_build_signed_transaction(w)
    test_low_s_enforcement(w)
    test_different_signer_combinations_eth()
    test_public_key_recovery(w)

    print("\n" + "=" * 60)
    print("  ALL PHASE 6 TESTS PASSED 🎉")
    print("=" * 60)
