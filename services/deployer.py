"""
VaultDeployer service.

Deploys a new VaultContract.sol for each company automatically when they sign up.
No human involvement required.
"""

import os
import json
import asyncio
from pathlib import Path
from typing import List, Optional, Dict, Any

from web3 import Web3
from eth_account import Account

# solcx imports for compilation
from solcx import compile_source, install_solc, get_installable_solc_versions, get_compilable_solc_versions


class VaultDeployer:
    """
    Service that deploys Vault contracts to Sepolia via the relayer wallet.
    """
    
    def __init__(self):
        """
        Initialize the deployer.
        
        - Connect web3.py to Infura/Alchemy via INFURA_URL env var
        - Load relayer wallet from RELAYER_PRIVATE_KEY env var
        - Load compiled contract ABI from contracts/VaultContract.abi
        - Load compiled bytecode from contracts/VaultContract.bin
        """
        self.infura_url = os.getenv("INFURA_URL")
        self.relayer_key = os.getenv("RELAYER_PRIVATE_KEY")
        self.relayer_address = os.getenv("RELAYER_ADDRESS")
        
        # Initialize Web3 connection
        self.w3 = Web3(Web3.HTTPProvider(self.infura_url))
        
        # Load relayer account
        if self.relayer_key and self.relayer_key.startswith('0x'):
            self.relayer_account = Account.from_key(self.relayer_key)
        elif self.relayer_key:
            self.relayer_account = Account.from_key('0x' + self.relayer_key)
        else:
            self.relayer_account = None
            
        # Contract paths
        self.contracts_dir = Path(__file__).parent.parent / "contracts"
        self.abi_path = self.contracts_dir / "VaultContract.abi"
        self.bin_path = self.contracts_dir / "VaultContract.bin"
        self.sol_path = self.contracts_dir / "VaultContract.sol"
        
        # Cached ABI and bytecode
        self._abi: Optional[List[Dict[str, Any]]] = None
        self._bytecode: Optional[str] = None
        
    def _load_abi(self) -> List[Dict[str, Any]]:
        """Load ABI from file or compile if needed."""
        if self._abi is not None:
            return self._abi
            
        if self.abi_path.exists():
            self._abi = json.loads(self.abi_path.read_text())
            return self._abi
            
        # Need to compile first
        raise RuntimeError("Contract not compiled. Run compile_contract() first.")
    
    def _load_bytecode(self) -> str:
        """Load bytecode from file or compile if needed."""
        if self._bytecode is not None:
            return self._bytecode
            
        if self.bin_path.exists():
            self._bytecode = self.bin_path.read_text().strip()
            return self._bytecode
            
        # Need to compile first
        raise RuntimeError("Contract not compiled. Run compile_contract() first.")
    
    async def deploy_vault(
        self,
        company_id: str,
        tss_wallet_address: str,
        executive_addresses: List[str],
        executive_names: List[str],
        threshold: int,
        spending_limit_wei: int
    ) -> str:
        """
        Deploy a new CorporateVault contract for a company.
        
        Steps:
        1. Build constructor transaction with all parameters
        2. Get current nonce from relayer address
        3. Estimate gas for deployment
        4. Sign transaction with relayer private key
        5. Broadcast to Sepolia via web3.py
        6. Wait for transaction receipt (poll every 3 seconds)
        7. Extract contract address from receipt
        8. Verify contract deployed (call getBalance())
        9. Log deployment to audit_log
        10. Return contract address
        
        Args:
            company_id: UUID of the company
            tss_wallet_address: Ethereum address from TSS group public key
            executive_addresses: List of executive Ethereum addresses
            executive_names: List of executive names (parallel to addresses)
            threshold: M-of-N threshold required for approvals
            spending_limit_wei: Daily spending limit in wei
            
        Returns:
            Deployed contract address (0x...)
        """
        if not self.w3.is_connected():
            raise RuntimeError("Web3 not connected to Sepolia. Check INFURA_URL.")
        
        if not self.relayer_account:
            raise RuntimeError("Relayer account not configured. Check RELAYER_PRIVATE_KEY.")
        
        # Load ABI and bytecode
        abi = self._load_abi()
        bytecode = self._load_bytecode()
        
        # Convert addresses to checksum format
        relayer_checksum = Web3.to_checksum_address(self.relayer_address)
        tss_checksum = Web3.to_checksum_address(tss_wallet_address)
        exec_checksums = [Web3.to_checksum_address(a) for a in executive_addresses]
        
        # Build contract instance
        Contract = self.w3.eth.contract(abi=abi, bytecode=bytecode)
        
        # Build constructor transaction
        construct_txn = Contract.constructor(
            relayer_checksum,
            tss_checksum,
            exec_checksums,
            executive_names,
            threshold,
            spending_limit_wei
        ).build_transaction({
            'from': relayer_checksum,
            'nonce': self.w3.eth.get_transaction_count(relayer_checksum),
            'gas': 3000000,  # Deployment gas limit
            'gasPrice': self.w3.eth.gas_price,
            'chainId': int(os.getenv("CHAIN_ID", 11155111)),
        })
        
        # Sign transaction
        signed_txn = self.relayer_account.sign_transaction(construct_txn)
        
        # Broadcast
        tx_hash = self.w3.eth.send_raw_transaction(signed_txn.raw_transaction)
        tx_hash_hex = tx_hash.hex()
        
        print(f"[deployer] Deploying vault for company {company_id}...")
        print(f"[deployer] Tx hash: 0x{tx_hash_hex}")
        
        # Wait for receipt (poll every 3 seconds)
        receipt = None
        max_attempts = 30  # 90 seconds max
        for attempt in range(max_attempts):
            try:
                receipt = self.w3.eth.get_transaction_receipt(tx_hash)
                if receipt:
                    break
            except Exception:
                pass
            await asyncio.sleep(3)
        
        if not receipt:
            raise RuntimeError(f"Deployment timed out. Tx hash: 0x{tx_hash_hex}")
        
        if receipt['status'] != 1:
            raise RuntimeError(f"Deployment failed. Tx hash: 0x{tx_hash_hex}")
        
        # Extract contract address
        contract_address = receipt['contractAddress']
        if not contract_address:
            raise RuntimeError("Contract address not found in receipt.")
        
        # Verify deployment (call getBalance())
        contract = self.w3.eth.contract(address=contract_address, abi=abi)
        try:
            # This should work even if balance is 0
            balance = contract.functions.getBalance().call()
            print(f"[deployer] Contract deployed at {contract_address}")
            print(f"[deployer] Initial balance: {balance} wei")
        except Exception as e:
            print(f"[deployer] Warning: Could not verify contract: {e}")
        
        return contract_address
    
    async def compile_contract(self) -> None:
        """
        Compile VaultContract.sol using py-solc-x.
        
        Saves:
        - contracts/VaultContract.abi
        - contracts/VaultContract.bin
        
        Call this once at server startup if files don't exist.
        """
        if not self.sol_path.exists():
            raise FileNotFoundError(f"Contract source not found: {self.sol_path}")
        
        # Install solc if needed
        try:
            # Try to install solc 0.8.19
            install_solc('0.8.19')
        except Exception as e:
            print(f"[deployer] Note: Could not install solc 0.8.19: {e}")
            print("[deployer] May already be installed or need manual installation.")
        
        # Read source
        source = self.sol_path.read_text()
        
        # Compile
        print("[deployer] Compiling VaultContract.sol...")
        compiled = compile_source(
            source,
            output_values=['abi', 'bin'],
            solc_version='0.8.19',
            evm_version='paris'
        )
        
        # Extract ABI and bytecode
        # compiled is a dict with keys like '<stdin>:CorporateVault'
        contract_key = None
        for key in compiled.keys():
            if 'CorporateVault' in key or 'Vault' in key:
                contract_key = key
                break
        
        if not contract_key:
            contract_key = list(compiled.keys())[0]
        
        contract_data = compiled[contract_key]
        abi = contract_data['abi']
        bytecode = contract_data['bin']
        
        # Save to files
        self.abi_path.write_text(json.dumps(abi, indent=2))
        self.bin_path.write_text(bytecode)
        
        # Cache
        self._abi = abi
        self._bytecode = bytecode
        
        print(f"[deployer] Contract compiled successfully!")
        print(f"[deployer] ABI saved to: {self.abi_path}")
        print(f"[deployer] Bytecode saved to: {self.bin_path}")
    
    def is_compiled(self) -> bool:
        """Check if contract has been compiled and files exist."""
        return self.abi_path.exists() and self.bin_path.exists()
