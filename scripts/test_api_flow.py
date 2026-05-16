import asyncio
import httpx 
import json
import time
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

COORDINATOR_URL = "http://localhost:8000"

async def main():
    print("==================================================")
    print("  TSS WALLET — DISTRIBUTED API INTEGRATION TEST  ")
    print("==================================================")
    print("Ensure you have run `python scripts/start_nodes.py` in another terminal.")
    time.sleep(1)

    async with httpx.AsyncClient(timeout=60.0) as client:
        # 1. Health check to ensure coordinator is up
        try:
            resp = await client.get(f"{COORDINATOR_URL}/health")
            if resp.status_code != 200:
                print("Coordinator not ready. Status code:", resp.status_code)
                return
            print("[*] Coordinator is ONLINE")
        except httpx.ConnectError:
            print("[-] Could not connect to Coordinator at", COORDINATOR_URL)
            print("Please run: python scripts/start_nodes.py")
            return

        # 2. Register & Login User
        print("\n[*] Registering and logging in user to Coordinator...")
        user_payload = {"username": "alice", "password": "securepassword"}
        resp = await client.post(f"{COORDINATOR_URL}/auth/register", json=user_payload)
        if resp.status_code not in (200, 409): # 409 means already exists
            print("Register failed:", resp.text)
            return

        resp = await client.post(f"{COORDINATOR_URL}/auth/login", json=user_payload)
        if resp.status_code != 200:
            print("Login failed:", resp.text)
            return
        
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("  ✅ User authenticated, JWT obtained.")

        # 3. Setup Wallet (DKG)
        print("\n[*] Initiating Distributed Key Generation (DKG) across all nodes...")
        print("    Threshold M=3, Total N=5. Please wait, this takes a moment...")
        setup_payload = {
            "threshold": 3,
            "total_nodes": 5,
            "node_ids": [1, 2, 3, 4, 5]
        }
        resp = await client.post(
            f"{COORDINATOR_URL}/wallet/setup", 
            json=setup_payload, 
            headers=headers
        )
        if resp.status_code != 200:
            print("Wallet setup failed:", resp.text)
            return
        
        setup_data = resp.json()
        print("  ✅ DKG Completed Successfully!")
        print("    Wallet Address:", setup_data["eth_address"])
        print("    Group Public Key (x):", setup_data["group_public_key"]["x"])

        # 4. Sign a transaction
        print("\n[*] Orchestrating MPC Signing without key reconstruction...")
        tx_payload = {
            "to_address": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
            "value_wei": 100000000000000000, # 0.1 ETH
            "nonce": 0,
            "gas_price_wei": 20000000000, # 20 gwei
            "gas_limit": 21000,
            "chain_id": 11155111, # Sepolia
            "participating_nodes": [1, 3, 5] # We need M=3
        }
        
        resp = await client.post(
            f"{COORDINATOR_URL}/wallet/sign",
            json=tx_payload,
            headers=headers
        )
        
        if resp.status_code != 200:
            print("Wallet sign failed:", resp.text)
            return
            
        sign_data = resp.json()
        print("  ✅ MPC Signing Completed Successfully!")
        print(f"    Participating Nodes: {sign_data['participating_nodes']}")
        print(f"    Signing Session ID : {sign_data['signing_session']}")
        
        print("\n[*] Final Signed Ethereum Transaction:")
        print(json.dumps(sign_data["result"], indent=4))
        
        print("\n==================================================")
        print("  ALL TESTS PASSED! DISTRIBUTED API WORKS PERFECTLY.")
        print("==================================================")

if __name__ == "__main__":
    asyncio.run(main())
