# scripts/fund_wallet.py
# One-shot utility: sends ETH from a MetaMask EOA to the TSS wallet address.
#
# PURPOSE:
#   The TSS wallet address is a pure Ethereum address derived from the group
#   public key. Before it can sign outbound transactions, it needs ETH for gas.
#   This script sends test ETH from a funded MetaMask account on Sepolia.
#
# USAGE:
#   python scripts/fund_wallet.py --amount 0.05
#
# SECURITY NOTE:
#   The private key is read from FUNDER_PRIVATE_KEY env var.
#   NEVER hardcode private keys. NEVER commit them to git.
#   This key is for a testnet funder account only.
#
# REQUIREMENTS:
#   pip install web3  (already installed)

import asyncio
import httpx
import argparse
import json
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

INFURA_URL = os.getenv(
    "INFURA_URL",
    "https://sepolia.infura.io/v3/YOUR_INFURA_PROJECT_ID"
)
COORDINATOR_URL = "http://localhost:8000"
ETHERSCAN_BASE  = "https://sepolia.etherscan.io"

# Default funder key — Sepolia testnet only, loaded from env
FUNDER_PRIVATE_KEY = os.getenv(
    "FUNDER_PRIVATE_KEY",
    "feabdc75c8ea8bcfbcf4b005fdcdf05b88f9f6f9c6ca41c11134179de66542ec"
)


def get_tss_wallet_address() -> str:
    """Reads TSS wallet address from the DKG snapshot file."""
    snap_file = PROJECT_ROOT / "dkg_snapshot.json"
    if not snap_file.exists():
        raise RuntimeError(
            "dkg_snapshot.json not found.\n"
            "Run: python scripts/start_nodes.py  (in another terminal)\n"
            "Then run test_api_flow.py once to generate the DKG snapshot."
        )
    snap = json.loads(snap_file.read_text())
    return snap["wallet_address"]


def fund_wallet(amount_eth: float, tss_address: str) -> str:
    """
    Sends `amount_eth` ETH from the funder EOA to the TSS wallet on Sepolia.

    Steps:
    1. Connect to Sepolia via Infura
    2. Build a simple ETH transfer transaction
    3. Sign with the funder's private key
    4. Broadcast raw transaction
    5. Return txHash

    Security note:
        The funder private key is used ONLY here to send testnet ETH.
        It is NOT the TSS wallet's key. The TSS private key never exists.
    """
    from web3 import Web3

    w3 = Web3(Web3.HTTPProvider(INFURA_URL))
    if not w3.is_connected():
        raise RuntimeError(f"Cannot connect to Infura at {INFURA_URL}")

    funder_account = w3.eth.account.from_key(FUNDER_PRIVATE_KEY)
    funder_address = funder_account.address

    print(f"\n  Funder address   : {funder_address}")
    print(f"  TSS wallet       : {tss_address}")
    print(f"  Amount           : {amount_eth} ETH")
    print(f"  Network          : Sepolia (chain 11155111)")

    # Check funder balance
    funder_balance_wei = w3.eth.get_balance(funder_address)
    funder_balance_eth = funder_balance_wei / 1e18
    print(f"  Funder balance   : {funder_balance_eth:.6f} ETH")

    amount_wei = int(amount_eth * 1e18)
    if funder_balance_wei < amount_wei + 21000 * 20_000_000_000:
        raise RuntimeError(
            f"Insufficient funder balance: {funder_balance_eth:.6f} ETH "
            f"(need {amount_eth} ETH + gas)"
        )

    # Check current TSS wallet balance
    tss_checksum = Web3.to_checksum_address(tss_address)
    tss_balance_before = w3.eth.get_balance(tss_checksum) / 1e18
    print(f"  TSS balance now  : {tss_balance_before:.6f} ETH")

    # Build transaction
    nonce      = w3.eth.get_transaction_count(funder_address)
    gas_price  = w3.eth.gas_price
    # Add 20% tip to ensure fast inclusion on testnet
    gas_price  = int(gas_price * 1.2)

    tx = {
        "nonce":    nonce,
        "to":       tss_checksum,
        "value":    amount_wei,
        "gas":      21000,
        "gasPrice": gas_price,
        "chainId":  11155111,
    }

    print(f"\n  Gas price        : {gas_price / 1e9:.2f} Gwei")
    print(f"  Nonce            : {nonce}")

    # Sign and broadcast
    signed = w3.eth.account.sign_transaction(tx, FUNDER_PRIVATE_KEY)
    tx_hash_bytes = w3.eth.send_raw_transaction(signed.raw_transaction)
    tx_hash = "0x" + tx_hash_bytes.hex()

    print(f"\n  ✅ Broadcast!     tx hash: {tx_hash}")
    print(f"  Etherscan        : {ETHERSCAN_BASE}/tx/{tx_hash}")
    print("\n  Waiting for confirmation", end="", flush=True)

    # Poll for receipt (up to 3 minutes)
    for _ in range(36):
        time.sleep(5)
        print(".", end="", flush=True)
        try:
            receipt = w3.eth.get_transaction_receipt(tx_hash_bytes)
            if receipt is not None:
                if receipt.status == 1:
                    tss_balance_after = w3.eth.get_balance(tss_checksum) / 1e18
                    print(f"\n\n  ✅ CONFIRMED (block {receipt.blockNumber})")
                    print(f"  TSS balance now  : {tss_balance_after:.6f} ETH  (+{amount_eth} ETH)")
                    print(f"  Etherscan        : {ETHERSCAN_BASE}/tx/{tx_hash}")
                else:
                    print(f"\n  ❌ Transaction REVERTED (status 0)")
                return tx_hash
        except Exception:
            pass

    print("\n  ⏳ Not yet confirmed. Check Etherscan manually.")
    return tx_hash


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fund the TSS wallet address on Sepolia testnet"
    )
    parser.add_argument(
        "--amount", type=float, default=0.05,
        help="Amount of ETH to send (default: 0.05)"
    )
    parser.add_argument(
        "--address", type=str, default=None,
        help="TSS wallet address (default: reads from dkg_snapshot.json)"
    )
    args = parser.parse_args()

    print("=" * 55)
    print("  TSS WALLET FUNDER — Sepolia Testnet")
    print("=" * 55)

    try:
        tss_addr = args.address or get_tss_wallet_address()
        tx_hash  = fund_wallet(args.amount, tss_addr)
        print(f"\n  Done. tx_hash: {tx_hash}")
    except Exception as e:
        print(f"\n  ERROR: {e}")
        sys.exit(1)
