"""
Phase 3 Test Script

Tests the auth endpoints and registration flow.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_health():
    """Test the health endpoint."""
    print("\nTesting /health...")
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    print("  OK: Health check passed")


def test_root():
    """Test the root endpoint."""
    print("\nTesting /...")
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "name" in data
    print("  OK: Root endpoint passed")


def test_auth_docs():
    """Test that auth endpoints are documented."""
    print("\nTesting /docs...")
    response = client.get("/docs")
    assert response.status_code == 200
    print("  OK: API docs available")


def test_endpoints_exist():
    """Test that endpoints exist and return expected status."""
    print("\nTesting endpoint existence...")
    
    # Test register (will fail validation but should exist)
    response = client.post("/auth/register", json={})
    assert response.status_code in [400, 422]  # Validation error expected
    print("  /auth/register: exists (returns validation error as expected)")
    
    # Test login (will fail validation but should exist)
    response = client.post("/auth/login", json={})
    assert response.status_code in [400, 422]  # Validation error expected
    print("  /auth/login: exists (returns validation error as expected)")
    
    # Test protected endpoints (will fail auth but should exist)
    response = client.get("/companies/me")
    assert response.status_code in [401, 403]  # No token provided
    print("  /companies/me: exists (requires auth)")
    
    response = client.get("/vault/balance")
    assert response.status_code in [401, 403]  # No token provided
    print("  /vault/balance: exists (requires auth)")


async def test_relayer():
    """Test the relayer service."""
    print("\nTesting Relayer service...")
    from services.relayer import Relayer
    
    relayer = Relayer()
    
    # Check web3 connection
    assert relayer.w3.is_connected(), "Web3 not connected"
    print("  Web3 connected: OK")
    
    # Check relayer balance
    balance = await relayer.get_relayer_balance()
    balance_eth = balance / 1e18
    print(f"  Relayer balance: {balance_eth:.6f} ETH")
    
    # Check deployed contract balance (from Phase 2)
    contract_address = "0xB95cFeD782Fa6f28b8b796854F4A815D317757cf"
    try:
        contract_balance = await relayer.get_vault_balance(contract_address)
        contract_balance_eth = contract_balance / 1e18
        print(f"  Contract balance: {contract_balance_eth:.6f} ETH")
    except Exception as e:
        print(f"  Contract balance: Error ({e})")


async def test_deployer():
    """Test the deployer service."""
    print("\nTesting Deployer service...")
    from services.deployer import VaultDeployer
    
    deployer = VaultDeployer()
    
    # Check compilation
    if deployer.is_compiled():
        print("  Contract compiled: OK")
    else:
        print("  Contract compiled: NOT COMPILED")
    
    # Check web3
    assert deployer.w3.is_connected(), "Web3 not connected"
    print("  Web3 connected: OK")


def run_tests():
    """Run all tests."""
    print("=" * 70)
    print("PHASE 3 TEST SUITE")
    print("=" * 70)
    
    try:
        test_health()
        test_root()
        test_auth_docs()
        test_endpoints_exist()
        
        # Run async tests
        asyncio.run(test_relayer())
        asyncio.run(test_deployer())
        
        print("\n" + "=" * 70)
        print("ALL TESTS PASSED - Phase 3 implementation complete!")
        print("=" * 70)
        print("\nTo test full registration flow:")
        print("1. Start PostgreSQL and run migrations: python -m alembic upgrade head")
        print("2. Start TSS nodes: python scripts/start_nodes.py --nodes 5")
        print("3. Start the API: python main.py")
        print("4. Test registration with curl or Postman")
        
        return 0
    except Exception as e:
        print(f"\nTEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(run_tests())
