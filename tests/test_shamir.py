# Run this to verify shamir.py works correctly

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from crypto.shamir import generate_private_key, generate_shares, reconstruct_secret

def test_basic_reconstruction():
    """3 of 5 shares should reconstruct correctly"""
    print("\n[TEST 1] Basic 3-of-5 reconstruction...")

    secret = generate_private_key()
    shares, _ = generate_shares(secret, M=3, N=5)

    # Try reconstructing with first 3 shares (Alice, Bob, Carol)
    reconstructed = reconstruct_secret(shares[:3])

    assert reconstructed == secret
    print(f"  Original  : {hex(secret)[:30]}...")
    print(f"  Reconstructed: {hex(reconstructed)[:30]}...")
    print("  PASSED [OK]")


def test_different_share_combinations():
    """Any combination of 3 shares should work"""
    print("\n[TEST 2] Different share combinations...")

    secret = generate_private_key()
    shares, _ = generate_shares(secret, M=3, N=5)

    # Try different combinations
    combinations = [
        [shares[0], shares[1], shares[2]],  # Alice Bob Carol
        [shares[0], shares[2], shares[4]],  # Alice Carol Eve
        [shares[1], shares[3], shares[4]],  # Bob Dave Eve
        [shares[2], shares[3], shares[4]],  # Carol Dave Eve
    ]

    for i, combo in enumerate(combinations):
        result = reconstruct_secret(combo)
        assert result == secret
        names = ["Alice+Bob+Carol", "Alice+Carol+Eve",
                 "Bob+Dave+Eve", "Carol+Dave+Eve"]
        print(f"  {names[i]}: PASSED [OK]")


def test_insufficient_shares_fail():
    """2 shares should NOT reconstruct correctly"""
    print("\n[TEST 3] Insufficient shares (2 of 3 threshold)...")

    secret = generate_private_key()
    shares, _ = generate_shares(secret, M=3, N=5)

    # Only 2 shares — should give wrong result
    wrong_result = reconstruct_secret(shares[:2])

    assert wrong_result != secret
    print(f"  With 2 shares got : {hex(wrong_result)[:30]}...")
    print(f"  Actual secret was : {hex(secret)[:30]}...")
    print("  Correctly FAILED to reconstruct [OK]")


def test_single_share_reveals_nothing():
    """1 share should give completely wrong result"""
    print("\n[TEST 4] Single share reveals nothing...")

    secret = generate_private_key()
    shares, _ = generate_shares(secret, M=3, N=5)

    wrong_result = reconstruct_secret([shares[0]])
    assert wrong_result != secret
    print("  Single share reveals nothing [OK]")


if __name__ == "__main__":
    print("=" * 50)
    print("  SHAMIR'S SECRET SHARING - TEST SUITE")
    print("=" * 50)

    test_basic_reconstruction()
    test_different_share_combinations()
    test_insufficient_shares_fail()
    test_single_share_reveals_nothing()

    print("\n" + "=" * 50)
    print("  ALL TESTS PASSED [SUCCESS]")
    print("=" * 50)