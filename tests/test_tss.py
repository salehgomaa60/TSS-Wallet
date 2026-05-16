# tests/test_tss.py
# Updated test suite for the refactored True TSS signing flow
# Now produces proper ECDSA (r, s) verified by standard ECDSA verifier
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from crypto.shamir import generate_private_key, generate_shares
from crypto.feldman_vss import generate_commitments, get_public_key
from crypto.threshold_sign import tss_sign, _verify_ecdsa, keccak256
from crypto.ecc import N


def test_full_tss_3_of_5():
    """
    Complete 3-of-5 TSS signing flow producing valid ECDSA (r, s).
    Key is NEVER reconstructed — only shares are used.
    """
    print("\n[TEST 1] Full 3-of-5 TSS signing (ECDSA output)...")

    secret = generate_private_key()
    shares, coefficients = generate_shares(secret, M=3, N=5)
    commitments = generate_commitments(coefficients)

    participating_shares = shares[:3]
    message = "Send 100 ETH to cold storage wallet"

    result = tss_sign(message, participating_shares, commitments)

    assert result['valid'] is True, "ECDSA verification of TSS output failed"
    r, s = result['signature']
    assert 1 <= r < N
    assert 1 <= s < N
    assert s <= N // 2, "s must be in low-s form"

    print(f"  Message: '{message}'")
    print(f"  Signers: 1, 2, 3 (3-of-5)")
    print(f"  r: {hex(r)[:20]}...")
    print(f"  s: {hex(s)[:20]}...")
    print(f"  Result: PASSED ✅")


def test_different_signer_combinations():
    """
    Any 3 of 5 signers should produce a valid ECDSA signature.
    This is the core threshold property.
    """
    print("\n[TEST 2] Different signer combinations all produce valid ECDSA...")

    secret = generate_private_key()
    shares, coefficients = generate_shares(secret, M=3, N=5)
    commitments = generate_commitments(coefficients)
    message = "Transfer funds to treasury"

    combinations = [
        ([shares[0], shares[1], shares[2]], "1+2+3"),
        ([shares[0], shares[2], shares[4]], "1+3+5"),
        ([shares[1], shares[3], shares[4]], "2+4+5"),
        ([shares[0], shares[1], shares[4]], "1+2+5"),
        ([shares[2], shares[3], shares[4]], "3+4+5"),
    ]

    for combo_shares, name in combinations:
        result = tss_sign(message, combo_shares, commitments)
        assert result['valid'] is True, f"Failed for signers {name}"
        r, s = result['signature']
        assert s <= N // 2, f"s not in low-s form for signers {name}"
        print(f"  Signers {name}: ✅")


def test_key_never_reconstructed():
    """
    Signing completes without ever calling reconstruct_secret.
    The private key never exists as a whole during signing.
    """
    print("\n[TEST 3] Key never reconstructed during signing...")

    secret = generate_private_key()
    shares, coefficients = generate_shares(secret, M=3, N=5)
    commitments = generate_commitments(coefficients)

    # Patch reconstruct_secret to detect if it's called
    import crypto.shamir as shamir_mod
    original = shamir_mod.reconstruct_secret
    called = []

    def patched(*args, **kwargs):
        called.append(True)
        return original(*args, **kwargs)

    shamir_mod.reconstruct_secret = patched

    try:
        result = tss_sign("Test transaction", shares[:3], commitments)
        assert result['valid'] is True
        assert len(called) == 0, "reconstruct_secret was called! Key was reconstructed!"
    finally:
        shamir_mod.reconstruct_secret = original

    print("  Signing completed without calling reconstruct_secret ✅")
    print("  Private key never assembled in memory ✅")


def test_ecdsa_standard_verification():
    """
    Verifies the signature using the standard ECDSA verification algorithm
    (same as Ethereum's ecrecover). This is NOT the Schnorr-style check
    from the original code — it's the real thing.
    """
    print("\n[TEST 4] Standard ECDSA verification (ecrecover-compatible)...")

    secret = generate_private_key()
    shares, coefficients = generate_shares(secret, M=3, N=5)
    commitments = generate_commitments(coefficients)
    public_key = get_public_key(commitments)

    message = "Ethereum tx hash test"
    msg_hash = keccak256(message.encode())

    result = tss_sign(message, shares[:3], commitments)
    r, s = result['signature']

    # Verify using the ECDSA algorithm (same as ecrecover)
    verified = _verify_ecdsa(msg_hash, r, s, public_key)
    assert verified, "Standard ECDSA verification failed"
    print("  Standard ECDSA (ecrecover-compatible) verification: ✅")


def test_2_of_3_threshold():
    """
    Tests a different (2-of-3) threshold configuration.
    M and N must be fully dynamic — not hardcoded.
    """
    print("\n[TEST 5] Dynamic M=2, N=3 threshold...")

    secret = generate_private_key()
    shares, coefficients = generate_shares(secret, M=2, N=3)
    commitments = generate_commitments(coefficients)

    result = tss_sign("2-of-3 test", shares[:2], commitments)
    assert result['valid'] is True
    print("  2-of-3 signing: ✅")


def test_4_of_7_threshold():
    """
    Tests a larger (4-of-7) threshold for extensibility.
    """
    print("\n[TEST 6] Dynamic M=4, N=7 threshold...")

    secret = generate_private_key()
    shares, coefficients = generate_shares(secret, M=4, N=7)
    commitments = generate_commitments(coefficients)

    # Use signers 2, 4, 5, 7 (non-sequential — tests Lagrange correctness)
    result = tss_sign("4-of-7 test", [shares[1], shares[3], shares[4], shares[6]], commitments)
    assert result['valid'] is True
    print("  4-of-7 signing (non-sequential signers): ✅")


if __name__ == "__main__":
    print("=" * 60)
    print("  TRUE TSS — COMPLETE SIGNING TEST SUITE (ECDSA)")
    print("=" * 60)

    test_full_tss_3_of_5()
    test_different_signer_combinations()
    test_key_never_reconstructed()
    test_ecdsa_standard_verification()
    test_2_of_3_threshold()
    test_4_of_7_threshold()

    print("\n" + "=" * 60)
    print("  ALL TSS TESTS PASSED 🎉")
    print("=" * 60)