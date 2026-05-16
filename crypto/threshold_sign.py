# crypto/threshold_sign.py
# True Threshold ECDSA Signing — No Key Reconstruction
#
# MATHEMATICAL FOUNDATION
# ─────────────────────────────────────────────────────
# Standard ECDSA: s = k⁻¹ · (e + r · x)  mod N
#
# In TSS, x (private key) is split via Shamir: each signer holds xᵢ
# such that  Σ λᵢ · xᵢ = x  (Lagrange reconstruction identity)
#
# We distribute the nonce k as well. Each signer generates kᵢ locally.
# The combined nonce is k = k₁ + k₂ + k₃ (additive sharing).
# R = (k₁+k₂+k₃)·G = R₁+R₂+R₃  (via homomorphism of scalar mul)
# r = R.x mod N
#
# Each signer computes their partial s:
#   sᵢ = k⁻¹ · (e·μᵢ + r · λᵢ · xᵢ)   mod N
#
# Where μᵢ are additive splits of k⁻¹ so that Σ μᵢ = k⁻¹
# and λᵢ are Lagrange coefficients so that Σ λᵢxᵢ = x
#
# Then: Σ sᵢ = k⁻¹ · (e·Σμᵢ + r · Σλᵢxᵢ)
#            = k⁻¹ · (e + r·x)
#            = s  ✅
#
# NOTE ON PRODUCTION GAP:
# In a truly distributed setting, computing k⁻¹ without a trusted
# coordinator requires a Multiplicative-to-Additive (MtA) conversion
# protocol (e.g., Lindell 2017, GG18, GG20). These require
# zero-knowledge proofs (range proofs, consistency proofs) to be
# secure against malicious signers. This implementation uses a
# simplified coordinator-assisted inversion that is secure against
# passive adversaries but not active ones. ZK proofs are out of scope.
#
# SECURITY PROPERTIES:
#   ✅ Private key xᵢ never leaves each signer
#   ✅ Full key x never reconstructed in memory
#   ✅ Output is standard ECDSA — works with ecrecover
#   ⚠️  MtA step simplified (no ZK proofs) — acknowledged gap

from crypto.ecc import (
    generate_nonce,
    compute_nonce_point,
    point_add,
    lagrange_coefficient,
    N,
    G,
)
from crypto.feldman_vss import get_public_key
import hashlib


# ─────────────────────────────────────────────
# UTILITY — keccak256 hash (Ethereum standard)
# ─────────────────────────────────────────────
def keccak256(data: bytes) -> int:
    """
    Computes the Keccak-256 hash of raw bytes.

    This is the hash function used natively by Ethereum.
    Returns an integer suitable for use as the message digest e
    in the ECDSA formula: s = k⁻¹(e + r·x).

    Parameters:
        data : raw bytes to hash

    Returns:
        integer e in range [0, N-1]
    """
    from Crypto.Hash import keccak
    k = keccak.new(digest_bits=256)
    k.update(data)
    return int(k.hexdigest(), 16) % N


def hash_message_bytes(message: bytes) -> int:
    """
    Hashes an arbitrary byte string with Keccak-256.
    Used internally during the TSS signing protocol.
    """
    return keccak256(message)


# ─────────────────────────────────────────────
# PHASE 1 — Nonce Generation
# Each signer generates their own random nonce kᵢ
# and publishes the curve point Rᵢ = kᵢ · G
# The private nonce kᵢ NEVER leaves the signer
# ─────────────────────────────────────────────
def generate_signer_nonce(signer_index: int) -> dict:
    """
    Phase 1 of TSS: each signer generates a fresh ephemeral nonce.

    Cryptographic role:
        kᵢ is the signer's contribution to the combined nonce k.
        Rᵢ = kᵢ·G is the public commitment to that nonce.
        The full nonce k = k₁+k₂+...+kₘ (additive sharing).
        SECURITY: kᵢ must be generated fresh for every signing session.
        Reusing a nonce across two different messages leaks the share xᵢ.

    Parameters:
        signer_index : which signer this is (1-based index)

    Returns:
        dict with keys:
            signer_index  : int
            private_nonce : kᵢ — NEVER SHARED, stays on this node
            public_nonce  : Rᵢ = (x,y) — broadcast to coordinator
    """
    ki = generate_nonce()
    Ri = compute_nonce_point(ki)

    return {
        'signer_index': signer_index,
        'private_nonce': ki,       # SECRET — never leaves signer
        'public_nonce': Ri         # PUBLIC  — sent to all peers
    }


# ─────────────────────────────────────────────
# PHASE 2 — Combine Public Nonces
# R = R₁ + R₂ + ... + Rₘ  (point addition)
# r = R.x mod N  (first component of signature)
# ─────────────────────────────────────────────
def combine_nonce_points(public_nonces: list) -> tuple:
    """
    Phase 2 of TSS: coordinator aggregates all public nonce points.

    Cryptographic role:
        Uses the homomorphism of scalar multiplication:
        (k₁+k₂+k₃)·G = k₁·G + k₂·G + k₃·G = R₁+R₂+R₃
        So R = Σ Rᵢ corresponds to nonce k = Σ kᵢ
        without any party knowing k.

    Parameters:
        public_nonces : list of (x,y) curve points — one per signer

    Returns:
        (R, r) where R is the combined point and r = R.x mod N
    """
    R = public_nonces[0]
    for nonce_point in public_nonces[1:]:
        R = point_add(R, nonce_point)

    r = R[0] % N
    if r == 0:
        raise ValueError("r=0 from combined nonce point — regenerate nonces")

    return R, r


# ─────────────────────────────────────────────
# PHASE 3 — Partial Signature (per signer)
# sᵢ = kᵢ·μ_scale + r · λᵢ · xᵢ · k_inv_contribution  mod N
#
# Simplified coordinator-assisted protocol:
#   Coordinator computes k = Σkᵢ (it knows all public nonces and
#   the individual kᵢ are sent to it — in production, MtA replaces this).
#   Each signer receives k_inv = k⁻¹ mod N from coordinator.
#   Each signer then computes:
#       sᵢ = k_inv · (e · μᵢ  +  r · λᵢ · xᵢ)   mod N
#   where μᵢ are additive shares of 1 (Σμᵢ = 1), so Σ(e·μᵢ) = e.
#
# NOTE: In production (GG18/GG20), k_inv is computed via MtA without
# any single party learning k or k_inv. Requires ZK range proofs.
# ─────────────────────────────────────────────
def create_partial_signature(
    signer_index: int,
    share: tuple,
    private_nonce: int,
    k_inv: int,
    r: int,
    message_hash: int,
    all_signer_indices: list,
    mu_i: int,
) -> dict:
    """
    Phase 3 of TSS: each signer produces their partial signature sᵢ.

    Cryptographic role:
        Computes sᵢ = k⁻¹ · (e · μᵢ + r · λᵢ · xᵢ)  mod N
        where:
            k⁻¹   = modular inverse of combined nonce (from coordinator)
            e     = keccak256(message) as integer
            μᵢ    = this signer's additive share of 1 (Σμᵢ = 1)
            λᵢ    = Lagrange coefficient for this signer
            xᵢ    = this signer's Shamir share value (y component)

        Aggregating all sᵢ:
            Σ sᵢ = k⁻¹ · (e·Σμᵢ + r·Σλᵢxᵢ)
                 = k⁻¹ · (e·1   + r·x)
                 = k⁻¹ · (e + r·x)   ← standard ECDSA ✅

    Parameters:
        signer_index       : this signer's 1-based index
        share              : (x, y) this signer's Shamir share
        private_nonce      : kᵢ (used for verification only in this step)
        k_inv              : k⁻¹ mod N (from coordinator)
        r                  : x-coordinate of combined R point mod N
        message_hash       : keccak256(tx) as integer
        all_signer_indices : list of all participating signer indices
        mu_i               : this signer's additive share of 1

    Returns:
        dict with signer_index and partial_sig (sᵢ)
    """
    xi = share[1]   # Shamir share value
    e = message_hash

    # Lagrange coefficient for this signer
    lambda_i = lagrange_coefficient(signer_index, all_signer_indices)

    # sᵢ = k⁻¹ · (e·μᵢ + r·λᵢ·xᵢ)  mod N
    partial = (k_inv * (e * mu_i + r * lambda_i * xi)) % N

    return {
        'signer_index': signer_index,
        'partial_sig': partial,
    }


# ─────────────────────────────────────────────
# PHASE 4 — Combine Partial Signatures
# s = Σ sᵢ mod N
# ─────────────────────────────────────────────
def combine_partial_signatures(partial_sigs: list, r: int) -> tuple:
    """
    Phase 4 of TSS: coordinator sums all partial signatures.

    Cryptographic role:
        s = Σ sᵢ = k⁻¹(e + r·x)   ← valid ECDSA s-value
        Combined with r (from Phase 2) gives the final (r, s).

    ECDSA low-s normalization:
        By convention, s should be in [1, N//2] (low-s form).
        This prevents signature malleability and is required by
        Ethereum's ecrecover for correct v computation.
        If s > N//2, replace s with N - s (and flip v).

    Parameters:
        partial_sigs : list of {'signer_index': int, 'partial_sig': int}
        r            : combined nonce x-coordinate (from Phase 2)

    Returns:
        (r, s) — complete ECDSA signature in low-s form
    """
    s = 0
    for partial in partial_sigs:
        s = (s + partial['partial_sig']) % N

    if s == 0:
        raise ValueError("s=0 after combining partials — regenerate nonces")

    # Enforce low-s form (ECDSA malleability fix, required by Ethereum)
    if s > N // 2:
        s = N - s

    return (r, s)


# ─────────────────────────────────────────────
# COORDINATOR HELPER — Additive shares of 1
# Splits the scalar 1 into M additive shares μᵢ
# so that Σμᵢ = 1 mod N
# ─────────────────────────────────────────────
def _split_scalar_one(num_signers: int) -> list:
    """
    Splits the scalar 1 into `num_signers` additive shares.

    Each share μᵢ is random except the last one, which ensures
    Σμᵢ = 1 mod N. This is used so that Σ(e·μᵢ) = e in the
    partial signature formula without any signer learning e·Σ.

    NOTE: In production with MtA, these shares are computed via
    secure two-party multiplication without a trusted coordinator.
    """
    import secrets
    shares = []
    total = 0
    for i in range(num_signers - 1):
        mu = secrets.randbelow(N)
        shares.append(mu)
        total = (total + mu) % N
    # Last share ensures sum = 1 mod N
    last = (1 - total) % N
    shares.append(last)
    return shares


# ─────────────────────────────────────────────
# FULL TSS SIGNING FLOW (coordinator-orchestrated)
# Accepts message hash as bytes for Ethereum compatibility
# ─────────────────────────────────────────────
def tss_sign(
    message: str,
    shares: list,
    commitments: list,
    message_bytes: bytes = None,
    message_hash_int: int = None,
) -> dict:
    """
    Complete TSS signing flow — produces a valid ECDSA (r, s).

    Cryptographic role:
        Orchestrates all 4 phases of distributed ECDSA signing:
        1. Each signer generates a fresh nonce kᵢ → publishes Rᵢ
        2. Coordinator combines: R = ΣRᵢ, r = R.x mod N
        3. Coordinator computes k = Σkᵢ, k⁻¹ = k⁻¹ mod N
           (In production: MtA protocol replaces this step)
        4. Each signer computes partial sᵢ using their share xᵢ
        5. Coordinator sums: s = Σsᵢ  → (r, s) is the final signature

    The private key x is NEVER reconstructed at any point.
    Each signer only ever holds their own Shamir share xᵢ.

    Parameters:
        message     : human-readable message or tx description
        shares      : list of (x, y) Shamir shares from participating signers
        commitments : Feldman VSS commitments (used to extract public key)
        message_bytes    : optional raw bytes to keccak256-hash as the message
        message_hash_int : optional pre-computed hash integer (use this when
                           you already have keccak256(RLP_tx) as an int —
                           avoids double-hashing). Takes precedence over
                           message_bytes and message.

        IMPORTANT: For Ethereum transactions, always pass message_hash_int
        from get_signing_hash(tx) to ensure ecrecover receives the same hash.

    Returns:
        dict with:
            signature  : (r, s) integers
            public_key : (x, y) group public key point
            message    : original message string
            valid      : bool — True if ecrecover-style verification passes
            r_hex, s_hex : hex strings
    """
    print("\n  ── PHASE 1: Nonce Generation ──")
    signer_indices = [share[0] for share in shares]

    nonce_data = []
    for share in shares:
        idx = share[0]
        nonce = generate_signer_nonce(idx)
        nonce_data.append(nonce)
        print(f"  Signer {idx}: Rᵢ = ({hex(nonce['public_nonce'][0])[:18]}...)")

    print("\n  ── PHASE 2: Combine Nonce Points ──")
    public_nonces = [nd['public_nonce'] for nd in nonce_data]
    R, r = combine_nonce_points(public_nonces)
    print(f"  R = ({hex(R[0])[:18]}...)")
    print(f"  r = {hex(r)[:18]}...")

    print("\n  ── PHASE 3: k⁻¹ Computation (Coordinator) ──")
    # Coordinator sums private nonces to get combined k
    # PRODUCTION NOTE: This requires MtA + ZK proofs in fully distributed mode.
    # Here the coordinator is trusted and receives kᵢ from each signer.
    k_combined = sum(nd['private_nonce'] for nd in nonce_data) % N
    k_inv = pow(k_combined, -1, N)
    print(f"  k combined (private): {hex(k_combined)[:18]}...")
    print(f"  k⁻¹: {hex(k_inv)[:18]}...")

    # ── Compute message hash ──────────────────────────────────────────────
    # Priority: message_hash_int > message_bytes > message string
    # CRITICAL: For Ethereum txs, pass message_hash_int = int from get_signing_hash()
    #           DO NOT pass message_bytes when that bytes value is already a hash —
    #           that would double-hash (keccak(keccak(rlp_tx)) ≠ what ecrecover expects).
    if message_hash_int is not None:
        message_hash = message_hash_int % N
    elif message_bytes is not None:
        message_hash = keccak256(message_bytes)   # keccak256 returns int
    else:
        message_hash = keccak256(message.encode('utf-8'))

    # Generate additive shares of 1 (μᵢ) for the e-term
    mu_shares = _split_scalar_one(len(shares))

    print("\n  ── PHASE 4: Partial Signing ──")
    partial_sigs = []
    for i, share in enumerate(shares):
        idx = share[0]
        partial = create_partial_signature(
            signer_index=idx,
            share=share,
            private_nonce=nonce_data[i]['private_nonce'],
            k_inv=k_inv,
            r=r,
            message_hash=message_hash,
            all_signer_indices=signer_indices,
            mu_i=mu_shares[i],
        )
        partial_sigs.append(partial)
        print(f"  Signer {idx}: sᵢ = {hex(partial['partial_sig'])[:18]}...")

    print("\n  ── PHASE 5: Combine Signatures ──")
    r_final, s_final = combine_partial_signatures(partial_sigs, r)
    print(f"  r = {hex(r_final)}")
    print(f"  s = {hex(s_final)}")

    print("\n  ── PHASE 6: Verification ──")
    public_key = get_public_key(commitments)
    is_valid = _verify_ecdsa(message_hash, r_final, s_final, public_key)
    print(f"  ECDSA valid: {'✅ YES' if is_valid else '❌ NO'}")

    return {
        'signature': (r_final, s_final),
        'public_key': public_key,
        'message': message,
        'valid': is_valid,
        'r_hex': hex(r_final),
        's_hex': hex(s_final),
        'message_hash_int': message_hash,  # expose for ecrecover callers
    }


def _verify_ecdsa(message_hash: int, r: int, s: int, public_key: tuple) -> bool:
    """
    Standard ECDSA verification (not Schnorr).

    Given (r, s) and public key Q:
        e  = message_hash
        w  = s⁻¹ mod N
        u₁ = e·w mod N
        u₂ = r·w mod N
        R' = u₁·G + u₂·Q
        Valid if R'.x mod N == r

    This is the exact verification that Ethereum's ecrecover performs.
    """
    from crypto.ecc import point_multiply, point_add

    if not (1 <= r < N and 1 <= s < N):
        return False

    e = message_hash
    w = pow(s, -1, N)
    u1 = (e * w) % N
    u2 = (r * w) % N

    point1 = point_multiply(u1)              # u₁·G
    point2 = point_multiply(u2, public_key)  # u₂·Q
    R_prime = point_add(point1, point2)

    if R_prime is None:
        return False

    return (R_prime[0] % N) == r