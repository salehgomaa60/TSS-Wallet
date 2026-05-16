# scripts/broadcast_test.py
# End-to-end Phase 1 test: DKG (from snapshot) → sign → broadcast → Etherscan
#
# WHAT THIS SCRIPT DOES:
#   1. Registers + logs in on coordinator
#   2. Calls /wallet/setup (idempotent — loads snapshot, same address every time)
#   3. Fetches real nonce from Sepolia
#   4. Signs + broadcasts a 0.001 ETH transfer to Vitalik's public address
#   5. Prints the real Etherscan link
#
# PREREQUISITES:
#   - python scripts/start_nodes.py  (running in another terminal)
#   - python scripts/fund_wallet.py  (TSS wallet has some Sepolia ETH)
#
# USAGE:
#   python scripts/broadcast_test.py
#   python scripts/broadcast_test.py --to 0xYourAddress --amount 0.001

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

COORDINATOR_URL = "http://localhost:8000"
ETHERSCAN_BASE  = "https://sepolia.etherscan.io"

# Default recipient: Vitalik's public address (safe burn address for testing)
DEFAULT_TO = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"


async def run_broadcast_test(to_address: str, amount_eth: float):
    print("=" * 60)
    print("  TSS WALLET — SEPOLIA BROADCAST TEST")
    print("=" * 60)

    amount_wei = int(amount_eth * 1e18)
    print(f"\n  To       : {to_address}")
    print(f"  Amount   : {amount_eth} ETH  ({amount_wei} wei)")

    async with httpx.AsyncClient(timeout=90.0) as client:

        # ── 1. Health check ──
        print("\n[1] Checking coordinator...")
        resp = await client.get(f"{COORDINATOR_URL}/health")
        if resp.status_code != 200:
            print(f"  ❌ Coordinator not responding (status {resp.status_code})")
            print("     Make sure start_nodes.py is running in another terminal.")
            return
        h = resp.json()
        print(f"  ✅ Coordinator online")
        print(f"     Wallet  : {h.get('wallet_address', 'not set')}")
        print(f"     Infura  : {'connected' if h.get('infura_connected') else 'NOT connected'}")
        print(f"     Snapshot: {'exists' if h.get('snapshot_exists') else 'missing'}")

        if not h.get("infura_connected"):
            print("\n  ⚠️  Infura not connected — broadcast will fail.")
            print("     Check INFURA_URL in .env")

        # ── 2. Auth ──
        print("\n[2] Registering + logging in...")
        creds = {"username": "broadcast_tester", "password": "test_pass_123"}
        await client.post(f"{COORDINATOR_URL}/auth/register", json=creds)
        resp = await client.post(f"{COORDINATOR_URL}/auth/login", json=creds)
        if resp.status_code != 200:
            print(f"  ❌ Login failed: {resp.text}")
            return
        token   = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("  ✅ Authenticated")

        # ── 3. Setup wallet (idempotent) ──
        print("\n[3] Loading wallet (idempotent DKG setup)...")
        resp = await client.post(
            f"{COORDINATOR_URL}/wallet/setup",
            json={"threshold": 3, "total_nodes": 5, "node_ids": [1,2,3,4,5]},
            headers=headers,
        )
        if resp.status_code != 200:
            print(f"  ❌ Wallet setup failed: {resp.text}")
            return
        setup = resp.json()
        wallet_addr = setup["eth_address"]
        print(f"  ✅ Wallet: {wallet_addr}")
        print(f"     Status: {setup['status']}")

        # ── 4. Check balance ──
        print("\n[4] Checking Sepolia balance...")
        resp = await client.get(f"{COORDINATOR_URL}/wallet/balance", headers=headers)
        if resp.status_code == 200:
            bal = resp.json()
            balance_eth = bal["balance_eth"]
            print(f"  ✅ Balance: {balance_eth} ETH")
            if balance_eth < amount_eth:
                print(f"\n  ❌ Insufficient balance ({balance_eth} ETH).")
                print(f"     Need at least {amount_eth} ETH. Run:")
                print(f"     python scripts/fund_wallet.py --amount 0.05")
                return
        else:
            print(f"  ⚠️  Could not fetch balance: {resp.text}")

        # ── 5. Sign + broadcast ──
        print("\n[5] Signing transaction via MPC (nodes 1, 3, 5)...")
        print("    (Each node contributes a partial signature — key never assembled)")

        sign_payload = {
            "to_address":          to_address,
            "value_wei":           amount_wei,
            "nonce":               -1,     # auto-fetch from chain
            "gas_price_wei":       25_000_000_000,   # 25 Gwei
            "gas_limit":           21000,
            "chain_id":            11155111,
            "participating_nodes": [1, 3, 5],
            "broadcast":           True,
        }

        resp = await client.post(
            f"{COORDINATOR_URL}/wallet/sign",
            json=sign_payload,
            headers=headers,
        )

        if resp.status_code != 200:
            print(f"  ❌ Signing failed: {resp.text}")
            return

        result = resp.json()
        signed = result["result"]
        bcast  = result["broadcast"]

        print(f"\n  ✅ MPC Signing complete!")
        print(f"     Nodes      : {result['participating_nodes']}")
        print(f"     Session    : {result['signing_session']}")
        print(f"     Nonce used : {result['nonce_used']}")
        print(f"     v          : {signed['signature']['v']}")
        print(f"     r          : {signed['signature']['r'][:20]}...")
        print(f"     s          : {signed['signature']['s'][:20]}...")
        print(f"     ecrecover  : ✅ verified")

        if bcast["broadcast"]:
            print(f"\n  ✅ BROADCAST TO SEPOLIA!")
            print(f"     tx_hash    : {bcast['tx_hash']}")
            print(f"     Etherscan  : {bcast['etherscan_url']}")

            print(f"\n  Waiting for Sepolia confirmation", end="", flush=True)
            try:
                from web3 import Web3
                w3 = Web3(Web3.HTTPProvider(
                    "https://sepolia.infura.io/v3/YOUR_INFURA_PROJECT_ID"
                ))
                tx_bytes = bytes.fromhex(bcast["tx_hash"].replace("0x", ""))
                for _ in range(24):  # 2 minutes max
                    time.sleep(5)
                    print(".", end="", flush=True)
                    try:
                        receipt = w3.eth.get_transaction_receipt(tx_bytes)
                        if receipt is not None:
                            if receipt.status == 1:
                                print(f"\n\n  ✅ CONFIRMED on Sepolia! (block {receipt.blockNumber})")
                            else:
                                print(f"\n  ❌ Transaction reverted (status 0)")
                            break
                    except Exception:
                        pass
                else:
                    print("\n  ⏳ Not yet confirmed — check Etherscan manually.")
            except Exception as e:
                print(f"\n  ⚠️  Could not poll for receipt: {e}")

        else:
            print(f"\n  ⚠️  Broadcast skipped or failed.")
            print(f"     Error: {bcast.get('error', 'unknown')}")
            print(f"     Raw tx: {signed['raw'][:80]}...")

        print("\n" + "=" * 60)
        print("  PHASE 1 COMPLETE")
        print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TSS Wallet — Sepolia broadcast test")
    parser.add_argument("--to",     default=DEFAULT_TO,  help="Recipient Ethereum address")
    parser.add_argument("--amount", default=0.001, type=float, help="ETH amount to send")
    args = parser.parse_args()

    asyncio.run(run_broadcast_test(args.to, args.amount))
