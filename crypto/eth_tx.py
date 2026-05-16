# crypto/eth_tx.py
# Phase 6 — Ethereum Transaction Formatting
#
# PURPOSE:
#   Takes the raw (r, s) output from threshold_sign.py and produces
#   a fully Ethereum-compatible signed transaction:
#     - RLP-encoded unsigned tx → keccak256 hash → feed to TSS signer
#     - Convert (r, s) → (v, r, s) with correct Ethereum recovery id
#     - Verify: ecrecover(hash, v, r, s) == wallet_address
#     - Build final broadcastable raw transaction hex
#
# ETHEREUM SIGNATURE FORMAT:
#   v = 27 or 28  (pre-EIP-155, legacy)
#   v = chainId*2 + 35 or chainId*2 + 36  (EIP-155 replay protection)
#
# STOPPING POINT: We produce the signed tx object ready for broadcast.
# Actual broadcasting to Sepolia is out of scope.

import rlp
from rlp.sedes import big_endian_int, Binary, List
from Crypto.Hash import keccak as _keccak
from py_ecc.secp256k1 import secp256k1
from crypto.ecc import N, point_multiply, point_add


# ─────────────────────────────────────────────
# UTILITY — keccak256
# ─────────────────────────────────────────────
def keccak256(data: bytes) -> bytes:
    """
    Returns the raw 32-byte keccak256 digest of `data`.
    Used for hashing RLP-encoded transactions before signing.

    Parameters:
        data : raw bytes

    Returns:
        32-byte digest (bytes)
    """
    k = _keccak.new(digest_bits=256)
    k.update(data)
    return k.digest()


def keccak256_int(data: bytes) -> int:
    """Returns keccak256 digest as an integer (for ECDSA math)."""
    return int.from_bytes(keccak256(data), 'big') % N


# ─────────────────────────────────────────────
# ETHEREUM ADDRESS — from secp256k1 public key
# ─────────────────────────────────────────────
def pubkey_to_eth_address(public_key: tuple) -> str:
    """
    Converts a secp256k1 public key point to an Ethereum address.

    Algorithm:
        1. Encode public key as uncompressed 64 bytes (x || y, no 0x04 prefix)
        2. keccak256 of those 64 bytes
        3. Take the last 20 bytes → Ethereum address

    Parameters:
        public_key : (x, y) integers — secp256k1 point

    Returns:
        Checksummed Ethereum address string: "0x..."
    """
    x, y = public_key
    # Uncompressed public key bytes (64 bytes, no 0x04 prefix)
    pub_bytes = x.to_bytes(32, 'big') + y.to_bytes(32, 'big')
    addr_bytes = keccak256(pub_bytes)[-20:]
    return _to_checksum_address(addr_bytes.hex())


def _to_checksum_address(hex_addr: str) -> str:
    """
    Applies EIP-55 checksum encoding to a lowercase hex address.

    Parameters:
        hex_addr : 40-character lowercase hex string (no 0x)

    Returns:
        "0x" + EIP-55 checksummed address
    """
    hex_addr = hex_addr.lower()
    checksum_hash = keccak256(hex_addr.encode('ascii')).hex()
    result = []
    for i, ch in enumerate(hex_addr):
        if ch.isalpha():
            result.append(ch.upper() if int(checksum_hash[i], 16) >= 8 else ch)
        else:
            result.append(ch)
    return '0x' + ''.join(result)


# ─────────────────────────────────────────────
# RLP ENCODING — Unsigned Transaction
# EIP-155 replay-protected format
# ─────────────────────────────────────────────
def encode_unsigned_tx(tx: dict) -> bytes:
    """
    RLP-encodes an unsigned Ethereum transaction (EIP-155 format).

    EIP-155 unsigned tx fields (in order):
        nonce, gasPrice, gasLimit, to, value, data, chainId, 0, 0

    The extra (chainId, 0, 0) fields prevent replay attacks across chains.
    This encoded bytes blob is hashed to get the signing hash.

    Parameters:
        tx : dict with keys:
            nonce    : int
            gasPrice : int (in wei)
            gasLimit : int
            to       : str "0x..." address
            value    : int (in wei)
            data     : bytes or "" (empty for ETH transfer)
            chainId  : int (11155111 for Sepolia, 1 for mainnet)

    Returns:
        RLP-encoded bytes of unsigned transaction
    """
    to_bytes = bytes.fromhex(tx['to'].replace('0x', ''))
    data_bytes = tx.get('data', b'') or b''
    if isinstance(data_bytes, str):
        data_bytes = bytes.fromhex(data_bytes.replace('0x', '')) if data_bytes else b''

    # RLP list: [nonce, gasPrice, gasLimit, to, value, data, chainId, 0, 0]
    fields = [
        _int_to_bytes(tx['nonce']),
        _int_to_bytes(tx['gasPrice']),
        _int_to_bytes(tx['gasLimit']),
        to_bytes,
        _int_to_bytes(tx['value']),
        data_bytes,
        _int_to_bytes(tx['chainId']),
        b'',   # v placeholder = 0
        b'',   # r placeholder = 0
    ]
    return _rlp_encode(fields)


def get_signing_hash(tx: dict) -> tuple[bytes, int]:
    """
    Computes the hash that signers must sign for a given transaction.

    Steps:
        1. RLP-encode unsigned tx (EIP-155 format)
        2. keccak256 of the encoded bytes
        3. Return both raw digest (bytes) and integer form

    Parameters:
        tx : transaction dict (see encode_unsigned_tx)

    Returns:
        (hash_bytes: bytes, hash_int: int)
        hash_int is fed into TSS signing as the message hash e
    """
    rlp_bytes = encode_unsigned_tx(tx)
    h = keccak256(rlp_bytes)
    return h, int.from_bytes(h, 'big') % N


# ─────────────────────────────────────────────
# RECOVERY ID — compute v for Ethereum
# v tells verifiers which of 2 possible R points was used
# ─────────────────────────────────────────────
def compute_recovery_id(
    message_hash: int,
    r: int,
    s: int,
    public_key: tuple,
    chain_id: int = None,
) -> int:
    """
    Computes the Ethereum recovery parameter v.

    ECDSA recovery_id encodes two bits of information:
        bit 0: y-parity of the nonce point R (0=even, 1=odd)
        bit 1: whether r overflowed (x = r + N); almost never happens on secp256k1

    We try all 4 candidates (recovery_id 0..3) and pick the one whose
    recovered public key matches our known group public key.

    For legacy transactions: v ∈ {27, 28} (recovery_id 0 or 1)
    For EIP-155 (replay protected): v = chainId*2 + 35 + recovery_id

    Parameters:
        message_hash : int  — keccak256(RLP tx) as integer, reduced mod N
        r, s         : int  — ECDSA signature components
        public_key   : (x,y) — the signer's known secp256k1 public key
        chain_id     : int or None — if None, returns legacy v (27/28)

    Returns:
        v : int — the Ethereum recovery parameter

    Raises:
        ValueError if no recovery_id produces the expected public key
    """
    # Ethereum only uses recovery_id 0 and 1 in practice
    # (recovery_id 2 and 3 require r >= N which is astronomically rare on secp256k1)
    for recovery_id in [0, 1, 2, 3]:
        candidate = _recover_public_key(message_hash, r, s, recovery_id)
        if candidate is not None and candidate == public_key:
            if chain_id is None:
                return 27 + (recovery_id & 1)  # legacy: 27 or 28
            else:
                # EIP-155: v = chainId * 2 + 35 + (recovery_id & 1)
                return chain_id * 2 + 35 + (recovery_id & 1)

    raise ValueError(
        "Could not determine recovery id — signature may be invalid.\n"
        "Check that message_hash used during signing matches the tx hash."
    )


def _recover_public_key(message_hash: int, r: int, s: int, recovery_id: int):
    """
    Recovers the public key from an ECDSA signature.

    Algorithm (SECG SEC1 §4.1.6):
        j     = recovery_id >> 1  (which R x-candidate: j=0 → x=r, j=1 → x=r+N)
        parity = recovery_id & 1  (0=even y, 1=odd y)
        x = r + j*N
        Lift x → two R candidates (y-even and y-odd); choose by parity
        Q = r⁻¹ · (s·R − e·G)

    Parameters:
        message_hash : int — keccak256 of signed data, reduced mod N
        r, s         : int — ECDSA signature components
        recovery_id  : int — 0, 1, 2, or 3

    Returns:
        (x, y) candidate public key point, or None if invalid
    """
    P = secp256k1.P

    # j selects which x candidate; parity selects which y
    j = recovery_id >> 1       # 0 for recovery_id 0,1 — 1 for recovery_id 2,3
    y_parity = recovery_id & 1  # 0 = even y, 1 = odd y

    # x coordinate of the nonce point R
    x = r + j * N
    if x >= P:
        return None

    # Compute y: y² = x³ + 7 mod P, then take square root
    # secp256k1 has P ≡ 3 mod 4, so sqrt = y_sq^((P+1)/4) mod P
    y_sq = (pow(x, 3, P) + 7) % P
    y = pow(y_sq, (P + 1) // 4, P)

    # Verify x is actually on the curve
    if pow(y, 2, P) != y_sq:
        return None

    # Select the y with the correct parity
    if (y & 1) != y_parity:
        y = P - y

    R_point = (x, y)

    # Recover public key: Q = r⁻¹ · (s·R − e·G)
    r_inv = pow(r, -1, N)
    e = message_hash

    sR = secp256k1.multiply(R_point, s)
    # Negate e·G by flipping y
    eG = secp256k1.multiply(secp256k1.G, e)
    neg_eG = (eG[0], (-eG[1]) % P)
    diff = secp256k1.add(sR, neg_eG)

    if diff is None:
        return None

    Q = secp256k1.multiply(diff, r_inv)
    return Q


# ─────────────────────────────────────────────
# ENCODE SIGNED TRANSACTION
# Produces the final broadcastable raw hex
# ─────────────────────────────────────────────
def encode_signed_tx(tx: dict, v: int, r: int, s: int) -> bytes:
    """
    RLP-encodes the signed transaction for broadcasting.

    Signed tx fields:
        [nonce, gasPrice, gasLimit, to, value, data, v, r, s]

    Parameters:
        tx : original transaction dict
        v  : recovery parameter (from compute_recovery_id)
        r  : signature r component (int)
        s  : signature s component (int)

    Returns:
        Raw signed transaction as bytes
    """
    to_bytes = bytes.fromhex(tx['to'].replace('0x', ''))
    data_bytes = tx.get('data', b'') or b''
    if isinstance(data_bytes, str):
        data_bytes = bytes.fromhex(data_bytes.replace('0x', '')) if data_bytes else b''

    fields = [
        _int_to_bytes(tx['nonce']),
        _int_to_bytes(tx['gasPrice']),
        _int_to_bytes(tx['gasLimit']),
        to_bytes,
        _int_to_bytes(tx['value']),
        data_bytes,
        _int_to_bytes(v),
        _int_to_bytes(r),
        _int_to_bytes(s),
    ]
    return _rlp_encode(fields)


# ─────────────────────────────────────────────
# ECRECOVER VERIFICATION
# Proves our signature is Ethereum-valid
# ─────────────────────────────────────────────
def ecrecover_verify(
    tx_hash_bytes: bytes,
    v: int,
    r: int,
    s: int,
    expected_address: str,
) -> bool:
    """
    Verifies a signature using ecrecover logic.

    This is the same computation Ethereum nodes perform on-chain
    when verifying a transaction signature. If ecrecover(hash, v, r, s)
    returns the expected address, our TSS signature is valid.

    Parameters:
        tx_hash_bytes    : 32-byte keccak256 hash of the unsigned tx
        v, r, s          : Ethereum signature components
        expected_address : the TSS wallet's Ethereum address

    Returns:
        True if recovered address matches expected_address
    """
    hash_int = int.from_bytes(tx_hash_bytes, 'big') % N

    # v to recovery_id (y-parity bit)
    # Legacy: v=27 → recovery_id=0 (even y), v=28 → recovery_id=1 (odd y)
    # EIP-155: recovery_id = (v - 35) & 1
    if v in (27, 28):
        recovery_id = v - 27
    else:
        recovery_id = (v - 35) & 1

    # Try both j=0 and j=1 variants (same y-parity) in case r >= N caused j=1
    for rid in [recovery_id, recovery_id + 2]:
        candidate_pubkey = _recover_public_key(hash_int, r, s, rid)
        if candidate_pubkey is not None:
            recovered_address = pubkey_to_eth_address(candidate_pubkey)
            if recovered_address.lower() == expected_address.lower():
                return True

    return False


# ─────────────────────────────────────────────
# MAIN ENTRY POINT — build_signed_transaction
# Takes TSS output + tx details → complete signed tx JSON
# ─────────────────────────────────────────────
def build_signed_transaction(
    tx: dict,
    r: int,
    s: int,
    public_key: tuple,
) -> dict:
    """
    Converts TSS (r, s) output into a complete Ethereum signed transaction.

    This is the final step of the TSS wallet pipeline:
        TSS output (r, s) → Ethereum (v, r, s) → RLP signed tx → broadcast

    Steps:
        1. Compute the wallet's Ethereum address from the public key
        2. Get signing hash from the transaction
        3. Compute recovery parameter v
        4. Verify with ecrecover
        5. RLP-encode the signed transaction
        6. Return the full broadcastable object

    Parameters:
        tx         : dict with nonce, gasPrice, gasLimit, to, value, chainId
        r, s       : raw ECDSA output from tss_sign()
        public_key : (x, y) secp256k1 point — TSS group public key

    Returns:
        dict in the exact format specified in the project brief:
        {
            "transaction": { ... },
            "signature": {"v": int, "r": "0x...", "s": "0x..."},
            "from": "0x...",
            "raw": "0x<RLP encoded signed transaction>"
        }

    Raises:
        ValueError if ecrecover verification fails
    """
    # Step 1: Wallet address
    wallet_address = pubkey_to_eth_address(public_key)

    # Step 2: Signing hash
    tx_hash_bytes, tx_hash_int = get_signing_hash(tx)

    # Step 3: Recovery id → v
    chain_id = tx.get('chainId')
    v = compute_recovery_id(tx_hash_int, r, s, public_key, chain_id)

    # Step 4: ecrecover verification
    verified = ecrecover_verify(tx_hash_bytes, v, r, s, wallet_address)
    if not verified:
        raise ValueError(
            "ecrecover FAILED — TSS signature does not recover to wallet address.\n"
            f"  Expected: {wallet_address}\n"
            "  Check that the correct public key and shares were used."
        )

    # Step 5: RLP-encode signed tx
    raw_bytes = encode_signed_tx(tx, v, r, s)
    raw_hex = '0x' + raw_bytes.hex()

    return {
        "transaction": {
            "to": tx['to'],
            "value": tx['value'],
            "nonce": tx['nonce'],
            "gasLimit": tx['gasLimit'],
            "gasPrice": tx['gasPrice'],
            "chainId": tx.get('chainId', 1),
            "data": tx.get('data', '0x'),
        },
        "signature": {
            "v": v,
            "r": hex(r),
            "s": hex(s),
        },
        "from": wallet_address,
        "txHash": '0x' + tx_hash_bytes.hex(),
        "raw": raw_hex,
        "ecrecover_verified": True,
    }


# ─────────────────────────────────────────────
# RLP HELPERS
# Minimal RLP encoder (no external rlp lib needed for our use case)
# ─────────────────────────────────────────────
def _int_to_bytes(n: int) -> bytes:
    """Converts a non-negative integer to big-endian bytes, stripping leading zeros."""
    if n == 0:
        return b''
    length = (n.bit_length() + 7) // 8
    return n.to_bytes(length, 'big')


def _rlp_encode_length(length: int, offset: int) -> bytes:
    """Encodes RLP length prefix."""
    if length < 56:
        return bytes([offset + length])
    len_bytes = _int_to_bytes(length)
    return bytes([offset + 55 + len(len_bytes)]) + len_bytes


def _rlp_encode_item(item: bytes) -> bytes:
    """RLP-encodes a single byte string."""
    if len(item) == 1 and item[0] < 0x80:
        return item
    return _rlp_encode_length(len(item), 0x80) + item


def _rlp_encode(items: list) -> bytes:
    """RLP-encodes a list of byte strings."""
    encoded_items = b''.join(_rlp_encode_item(item) for item in items)
    return _rlp_encode_length(len(encoded_items), 0xC0) + encoded_items
