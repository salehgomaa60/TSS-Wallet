"""
Script to manually test the vault contract deployment.

Usage:
    python scripts/deploy_contract.py

This script:
1. Compiles the contract (if needed)
2. Deploys to Sepolia using the relayer wallet
3. Verifies the deployment by calling getBalance()
4. Outputs the contract address and Etherscan link
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from services.deployer import VaultDeployer


async def main():
    print("=" * 70)
    print("VAULT CONTRACT DEPLOYMENT TEST")
    print("=" * 70)
    
    # Initialize deployer
    deployer = VaultDeployer()
    
    # Check web3 connection
    if not deployer.w3.is_connected():
        print("ERROR: Web3 not connected. Check INFURA_URL in .env")
        return 1
    print(f"Web3 connected to: {deployer.infura_url}")
    
    # Check relayer
    if not deployer.relayer_account:
        print("ERROR: Relayer account not configured. Check RELAYER_PRIVATE_KEY in .env")
        return 1
    print(f"Relayer address: {deployer.relayer_address}")
    
    # Check balance
    balance_wei = deployer.w3.eth.get_balance(deployer.relayer_address)
    balance_eth = balance_wei / 1e18
    print(f"Relayer balance: {balance_eth:.6f} ETH")
    
    if balance_eth < 0.01:
        print("WARNING: Relayer balance may be too low for deployment.")
        print("Fund the relayer wallet with Sepolia ETH from sepoliafaucet.com")
        return 1
    
    # Compile contract if needed
    if not deployer.is_compiled():
        print("\nContract not compiled. Compiling now...")
        try:
            await deployer.compile_contract()
        except Exception as e:
            print(f"ERROR: Compilation failed: {e}")
            return 1
    else:
        print("\nContract already compiled.")
    
    # Test deployment parameters
    from web3 import Web3
    test_company_id = "test-company-123"
    test_tss_wallet = Web3.to_checksum_address("0x1234567890123456789012345678901234567890")  # Placeholder
    test_executives = [Web3.to_checksum_address(deployer.relayer_address)]  # Use relayer as test executive
    test_names = ["Test Executive"]
    test_threshold = 1
    test_limit = 10_000_000_000_000_000_000  # 10 ETH in wei
    
    print(f"\nTest deployment parameters:")
    print(f"  Company ID: {test_company_id}")
    print(f"  TSS Wallet: {test_tss_wallet}")
    print(f"  Executives: {test_executives}")
    print(f"  Threshold: {test_threshold}")
    print(f"  Spending Limit: {test_limit} wei (10 ETH)")
    
    # Confirm deployment
    print("\n" + "=" * 70)
    response = input("Deploy contract to Sepolia? (yes/no): ")
    if response.lower() not in ['yes', 'y']:
        print("Deployment cancelled.")
        return 0
    
    # Deploy
    print("\nDeploying contract...")
    try:
        contract_address = await deployer.deploy_vault(
            company_id=test_company_id,
            tss_wallet_address=test_tss_wallet,
            executive_addresses=test_executives,
            executive_names=test_names,
            threshold=test_threshold,
            spending_limit_wei=test_limit
        )
        
        print("\n" + "=" * 70)
        print("DEPLOYMENT SUCCESSFUL!")
        print("=" * 70)
        print(f"Contract address: {contract_address}")
        print(f"Etherscan URL: https://sepolia.etherscan.io/address/{contract_address}")
        
        # Test getBalance
        abi = deployer._load_abi()
        contract = deployer.w3.eth.contract(address=contract_address, abi=abi)
        balance = contract.functions.getBalance().call()
        print(f"\nContract balance: {balance} wei")
        
        # Test getExecutives
        execs = contract.functions.getExecutives().call()
        print(f"Executives: {execs}")
        
        print("\n" + "=" * 70)
        print("Verification successful!")
        
    except Exception as e:
        print(f"\nERROR: Deployment failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
