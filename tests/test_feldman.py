# tests/test_feldman.py
# Verifies that Feldman VSS works correctly

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from crypto.shamir import generate_private_key, generate_shares
from crypto.feldman_vss import (
    generate_commitments,
    verify_share,
    verify_all_shares,
    get_public_key
)
from py_ecc.secp256k1 import secp256k1

G = secp256k1.G
N = secp256k1.N


def test_all_shares_valid():
    """All legitimate shares should pass verification"""
    print("\n[TEST 1] All legitimate shares pass verification...")

    secret = generate_private_key()
    shares, coefficients = generate_shares(secret, M=3, N=5)
    commitments = generate_commitments(coefficients)

    signers = ["Alice", "Bob", "Carol", "Dave", "Eve"]
    results = verify_all_shares(shares, commitments)

    for share, name in zip(shares, signers):
        x, _ = share
        assert results[x] == True
        print(f"  {name}: Share verification PASSED ✅")


def test_tampered_share_fails():
    """A tampered share should fail verification"""
    print("\n[TEST 2] Tampered share fails verification...")

    secret = generate_private_key()
    shares, coefficients = generate_shares(secret, M=3, N=5)
    commitments = generate_commitments(coefficients)

    # Tamper with Alice's share
    alice_share = shares[0]
    tampered_share = (alice_share[0], alice_share[1] + 1)  # change y by 1

    result = verify_share(tampered_share, commitments)
    assert result == False
    print(f"  Tampered share correctly REJECTED ✅")


def test_wrong_commitments_fail():
    """Shares from one secret should fail against different commitments"""
    print("\n[TEST 3] Wrong commitments fail verification...")

    # Generate two completely different secrets
    secret1 = generate_private_key()
    secret2 = generate_private_key()

    shares1, coefficients1 = generate_shares(secret1, M=3, N=5)
    shares2, coefficients2 = generate_shares(secret2, M=3, N=5)

    # Use commitments from secret2 to verify shares from secret1
    commitments2 = generate_commitments(coefficients2)

    result = verify_share(shares1[0], commitments2)
    assert result == False
    print(f"  Cross-secret verification correctly REJECTED ✅")


def test_public_key_extraction():
    """Public key from commitments should match secret * G"""
    print("\n[TEST 4] Public key extraction from commitments...")

    secret = generate_private_key()
    shares, coefficients = generate_shares(secret, M=3, N=5)
    commitments = generate_commitments(coefficients)

    # Get public key from commitments (C0 = secret * G)
    public_key_from_commitments = get_public_key(commitments)

    # Calculate public key directly
    public_key_direct = secp256k1.multiply(G, secret)

    assert public_key_from_commitments == public_key_direct
    print(f"  Public key (from commitments): "
          f"({hex(public_key_from_commitments[0])[:20]}...)")
    print(f"  Public key (direct calc)     : "
          f"({hex(public_key_direct[0])[:20]}...)")
    print(f"  Both match ✅")


if __name__ == "__main__":
    print("=" * 50)
    print("  FELDMAN VSS — TEST SUITE")
    print("=" * 50)

    test_all_shares_valid()
    test_tampered_share_fails()
    test_wrong_commitments_fail()
    test_public_key_extraction()

    print("\n" + "=" * 50)
    print("  ALL TESTS PASSED 🎉")
    print("=" * 50)