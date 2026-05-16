# Feldman Verifiable Secret Sharing
# Allows each signer to verify their share is legitimate
# without revealing the secret or other shares

from py_ecc.secp256k1 import secp256k1
from crypto.shamir import PRIME

# ─────────────────────────────────────────────
# secp256k1 curve parameters
# G is the generator point — a fixed public point on the curve
# Every operation is done on this curve
# ─────────────────────────────────────────────
G = secp256k1.G   # Generator point (x, y)
N = secp256k1.N   # Curve order (how many points exist)


# ─────────────────────────────────────────────
# STEP 1 — Generate public commitments
# These are published by the dealer to everyone
# ─────────────────────────────────────────────
def generate_commitments(coefficients: list) -> list:
    """
    For each polynomial coefficient, compute its commitment on the curve

    Parameters:
        coefficients : list of polynomial coefficients [secret, a1, a2, ...]
                      returned from generate_shares() in shamir.py

    Returns:
        List of elliptic curve points (x, y)
        One commitment per coefficient

    The math:
        C0 = secret * G
        C1 = a1 * G
        C2 = a2 * G
        ...
    These are PUBLIC — posted to all signers
    They prove the dealer used a consistent polynomial
    without revealing secret or any coefficient
    """
    commitments = []

    for coefficient in coefficients:
        # Scalar multiplication on secp256k1
        # coefficient * G = point on the curve
        commitment = secp256k1.multiply(G, coefficient % N)
        commitments.append(commitment)

    return commitments


# ─────────────────────────────────────────────
# STEP 2 — Verify a single share
# Each signer runs this on their own share
# ─────────────────────────────────────────────
def verify_share(share: tuple, commitments: list) -> bool:
    """
    Verifies that a share is consistent with the public commitments

    Parameters:
        share       : (x, y) tuple — the signer's share
        commitments : list of curve points published by dealer

    Returns:
        True  → share is legitimate ✅
        False → share is fake or tampered ❌

    The math:
        Check if:  y * G == C0 + C1*x + C2*x² + ...

        Left side:  y * G  (scalar multiply share value by G)
        Right side: evaluate commitment polynomial at x
    """
    x, y = share

    # ── Left side: y * G ──
    left_side = secp256k1.multiply(G, y % N)

    # ── Right side: C0 + C1*x + C2*x² + ... ──
    # Start with the point at infinity (zero point for addition)
    right_side = None  # None represents point at infinity in py_ecc

    for power, commitment in enumerate(commitments):
        # Calculate x^power mod N
        x_power = pow(x, power, N)

        # Multiply commitment by x^power
        # Ci * x^i
        term = secp256k1.multiply(commitment, x_power)

        # Add to running sum
        if right_side is None:
            right_side = term
        else:
            right_side = secp256k1.add(right_side, term)

    # ── Compare left and right ──
    return left_side == right_side


# ─────────────────────────────────────────────
# STEP 3 — Verify ALL shares at once
# The dealer runs this before distributing
# ─────────────────────────────────────────────
def verify_all_shares(shares: list, commitments: list) -> dict:
    """
    Verifies all shares against the commitments

    Parameters:
        shares      : list of (x, y) tuples
        commitments : list of curve points

    Returns:
        Dictionary mapping signer index to verification result
        {1: True, 2: True, 3: False, ...}
    """
    results = {}
    for share in shares:
        x, y = share
        results[x] = verify_share(share, commitments)
    return results


# ─────────────────────────────────────────────
# STEP 4 — Extract the public key from commitments
# C0 = secret * G = the public key
# We get the public key WITHOUT knowing the secret
# ─────────────────────────────────────────────
def get_public_key(commitments: list) -> tuple:
    """
    Extracts the public key from the commitments

    C0 is always secret * G which is exactly the public key
    This is how signers can get the group public key
    without anyone revealing the secret

    Returns:
        (x, y) point on secp256k1 — the public key
    """
    # C0 = secret * G = public key
    return commitments[0]