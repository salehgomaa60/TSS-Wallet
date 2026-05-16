# crypto/ecc.py
# Elliptic Curve Cryptography toolkit
# secp256k1 — the curve used by Bitcoin and Ethereum
# This file provides all curve operations we need for TSS

from py_ecc.secp256k1 import secp256k1
import hashlib
import secrets

# ─────────────────────────────────────────────
# Curve parameters
# ─────────────────────────────────────────────
G = secp256k1.G    # Generator point
N = secp256k1.N    # Curve order — all scalar math is mod N
P = secp256k1.P    # Field prime — all point math is mod P


# ─────────────────────────────────────────────
# OPERATION 1 — Scalar Multiplication
# k * G = point on curve
# This is the ONE-WAY function that makes ECC secure
# Easy to compute forward, impossible to reverse
# ─────────────────────────────────────────────
def point_multiply(scalar: int, point=None) -> tuple:
    """
    Multiplies a scalar by a curve point
    Default point is G (generator)

    Parameters:
        scalar : integer (private key, nonce, share, etc.)
        point  : (x,y) curve point — defaults to G

    Returns:
        (x, y) point on secp256k1

    Example:
        public_key = point_multiply(private_key)
        → same as private_key * G
    """
    if point is None:
        point = G

    scalar = scalar % N  # Always reduce mod N

    if scalar == 0:
        raise ValueError("Scalar cannot be zero")

    return secp256k1.multiply(point, scalar)


# ─────────────────────────────────────────────
# OPERATION 2 — Point Addition
# A + B = another point on the curve
# Used to combine partial nonces and signatures
# ─────────────────────────────────────────────
def point_add(point1: tuple, point2: tuple) -> tuple:
    """
    Adds two elliptic curve points together

    Parameters:
        point1 : (x, y) first curve point
        point2 : (x, y) second curve point

    Returns:
        (x, y) resulting curve point

    Used in TSS to combine:
        R = R1 + R2 + R3  (nonce points from each signer)
    """
    if point1 is None:
        return point2
    if point2 is None:
        return point1

    return secp256k1.add(point1, point2)


# ─────────────────────────────────────────────
# OPERATION 3 — Hash a message
# Converts any message into a 256-bit integer
# This is what gets signed, not the raw message
# ─────────────────────────────────────────────
def hash_message(message: str) -> int:
    """
    Hashes a message using SHA-256
    Returns integer representation

    Parameters:
        message : string — the transaction data

    Returns:
        integer — the message hash (called 'e' or 'z' in ECDSA)

    In real Ethereum this uses keccak256
    We use SHA-256 here for clarity
    """
    if isinstance(message, str):
        message = message.encode('utf-8')

    digest = hashlib.sha256(message).digest()
    return int.from_bytes(digest, 'big') % N


# ─────────────────────────────────────────────
# OPERATION 4 — Generate a secure random nonce
# CRITICAL: nonce must NEVER be reused
# Reusing a nonce leaks the private key
# ─────────────────────────────────────────────
def generate_nonce() -> int:
    """
    Generates a cryptographically secure random nonce k

    SECURITY WARNING:
        Never reuse a nonce
        Never use predictable values as nonces
        Each signing session needs fresh nonces

    Returns:
        integer k in range [1, N-1]
    """
    while True:
        k = secrets.randbelow(N)
        if k != 0:  # k must not be zero
            return k


# ─────────────────────────────────────────────
# OPERATION 5 — Compute nonce point
# R = k * G
# The x-coordinate of R becomes part of the signature
# ─────────────────────────────────────────────
def compute_nonce_point(k: int) -> tuple:
    """
    Computes the public nonce point R = k * G

    Parameters:
        k : the private nonce integer

    Returns:
        R : (x, y) point on the curve

    In TSS:
        Each signer computes Ri = ki * G
        Then R = R1 + R2 + R3 is the combined nonce point
        r = R.x mod N becomes part of the signature
    """
    return point_multiply(k)


# ─────────────────────────────────────────────
# OPERATION 6 — Compute Lagrange coefficient
# This is what allows partial signatures to combine correctly
# Each signer's share gets weighted by their Lagrange coefficient
# ─────────────────────────────────────────────
def lagrange_coefficient(signer_index: int, all_indices: list) -> int:
    """
    Computes the Lagrange coefficient for a signer

    Parameters:
        signer_index : the x value of this signer (1,2,3,4,5)
        all_indices  : list of ALL participating signer indices

    Returns:
        integer — the Lagrange coefficient mod N

    The math:
        L_i(0) = Π (0 - x_j) / (x_i - x_j)   for j ≠ i

    Why we need this:
        In Shamir, shares are points on a polynomial
        To evaluate at x=0 (the secret), each share
        needs to be weighted by its Lagrange coefficient
        In TSS we apply this weighting DURING signing
        so we never need to evaluate at x=0 directly
    """
    numerator = 1
    denominator = 1

    for j in all_indices:
        if j != signer_index:
            # numerator:   (0 - xj) = -xj
            # denominator: (xi - xj)
            numerator = (numerator * (-j)) % N
            denominator = (denominator * (signer_index - j)) % N

    # Modular inverse using Fermat's little theorem
    # a^(-1) mod N = a^(N-2) mod N  (N is prime)
    coeff = (numerator * pow(denominator, -1, N)) % N
    return coeff


# ─────────────────────────────────────────────
# OPERATION 7 — Verify a complete ECDSA signature
# Used at the end to confirm our TSS signature is valid
# ─────────────────────────────────────────────
def verify_signature(message: str, r: int, s: int, public_key: tuple) -> bool:
    """
    Verifies a complete signature (Schnorr variant)

    Parameters:
        message    : original message string
        r, s       : the signature components
        public_key : (x, y) the group public key

    Returns:
        True  → signature is valid ✅
        False → signature is invalid ❌

    The math:
        e  = hash(message)
        s*G = R + e*PublicKey  =>  R' = s*G - e*PublicKey
        Valid if R'.x mod N == r
    """
    if not (1 <= r < N and 1 <= s < N):
        return False

    e = hash_message(message)

    # R' = s*G - e*PublicKey
    point1 = point_multiply(s)
    neg_e = (-e) % N
    point2 = point_multiply(neg_e, public_key)
    R_prime = point_add(point1, point2)

    if R_prime is None:
        return False

    # Valid if x coordinate matches r
    return (R_prime[0] % N) == r