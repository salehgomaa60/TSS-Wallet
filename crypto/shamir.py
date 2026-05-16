# Shamir's Secret Sharing Scheme
# Splits a private key into N shares — any M can reconstruct it

import secrets
import functools
from py_ecc.secp256k1 import secp256k1

# ─────────────────────────────────────────────
# secp256k1 group order (N)
# This is the order of the generator point.
# All our private key math happens modulo this number
# ─────────────────────────────────────────────
PRIME = secp256k1.N


# ─────────────────────────────────────────────
# STEP 1 — Generate a cryptographically secure private key
# ─────────────────────────────────────────────
def generate_private_key() -> int:
    """
    Generates a random 256-bit private key
    within the valid range for secp256k1
    Returns an integer
    """
    # secrets module is cryptographically secure
    # unlike random module which is NOT safe for crypto
    key = secrets.randbelow(PRIME)
    return key


# ─────────────────────────────────────────────
# STEP 2 — Evaluate a polynomial at point x
# This is the core math of Shamir's scheme
# ─────────────────────────────────────────────
def _evaluate_polynomial(coefficients: list, x: int) -> int:
    """
    Evaluates polynomial at point x over the finite field

    Example with M=3:
    f(x) = secret + a1*x + a2*x^2  (mod PRIME)

    coefficients[0] = secret  (the thing we are hiding)
    coefficients[1] = a1      (random number)
    coefficients[2] = a2      (random number)

    This uses Horner's method for efficiency:
    f(x) = secret + x*(a1 + x*(a2))
    """
    result = 0
    # We go through coefficients in reverse for Horner's method
    for coefficient in reversed(coefficients):
        result = (result * x + coefficient) % PRIME
    return result


# ─────────────────────────────────────────────
# STEP 3 — Split the secret into N shares
# ─────────────────────────────────────────────
def generate_shares(secret: int, M: int, N: int) -> list[tuple]:
    """
    Splits a secret into N shares where any M can reconstruct it

    Parameters:
        secret : the private key (integer)
        M      : minimum shares needed to reconstruct (threshold)
        N      : total number of shares to generate

    Returns:
        List of (x, y) tuples — one per signer
        x = signer index (1,2,3,4,5)
        y = their secret share value

    Example:
        shares = generate_shares(secret, M=3, N=5)
        gives shares for Alice(1), Bob(2), Carol(3), Dave(4), Eve(5)
    """

    # Validate inputs
    if M > N:
        raise ValueError(f"Threshold M={M} cannot exceed total signers N={N}")
    if M < 2:
        raise ValueError("Threshold M must be at least 2")
    if not (0 < secret < PRIME):
        raise ValueError("Secret must be within the field range")

    # Build the polynomial coefficients
    # coefficients[0] = secret (this is what f(0) equals)
    # coefficients[1..M-1] = random values
    coefficients = [secret] + [
        secrets.randbelow(PRIME) for _ in range(M - 1)
    ]

    # Generate one share per signer
    # x starts at 1 (never 0, because f(0) = secret itself)
    shares = []
    for x in range(1, N + 1):
        y = _evaluate_polynomial(coefficients, x)
        shares.append((x, y))

    return shares, coefficients  # we return coefficients too for Feldman VSS


# ─────────────────────────────────────────────
# STEP 4 — Reconstruct the secret from M shares
# Uses Lagrange Interpolation
# ─────────────────────────────────────────────
def reconstruct_secret(shares: list[tuple]) -> int:
    """
    Reconstructs the secret from M shares using Lagrange interpolation

    Parameters:
        shares : list of (x, y) tuples from any M signers

    Returns:
        The reconstructed secret (integer)

    The math:
        f(0) = Σ yᵢ * Lᵢ(0)   for each share i

        Where Lᵢ(0) = Π (0 - xⱼ)/(xᵢ - xⱼ)   for j ≠ i

        This is Lagrange basis polynomial evaluated at x=0
        because f(0) = secret
    """

    secret = 0
    x_values = [share[0] for share in shares]
    y_values = [share[1] for share in shares]

    for i in range(len(shares)):
        xi = x_values[i]
        yi = y_values[i]

        # Calculate Lagrange basis polynomial Li(0)
        numerator = 1
        denominator = 1

        for j in range(len(shares)):
            if i != j:
                xj = x_values[j]
                # numerator:   (0 - xj) = -xj
                # denominator: (xi - xj)
                numerator = (numerator * (-xj)) % PRIME
                denominator = (denominator * (xi - xj)) % PRIME

        # Modular inverse of denominator
        # In a finite field: a/b = a * b^(p-2) mod p
        lagrange_coeff = (numerator * pow(denominator, -1, PRIME)) % PRIME

        # Add this share's contribution
        secret = (secret + yi * lagrange_coeff) % PRIME

    return secret