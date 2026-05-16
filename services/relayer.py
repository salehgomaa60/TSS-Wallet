"""
Relayer service.

Broadcasts all signed transactions on behalf of users.
Users never pay gas. Never need ETH. Never need MetaMask.
"""

import os
import json
from pathlib import Path
from typing import Optional, Dict, Any, List

from web3 import Web3
from eth_account import Account


class Relayer:
    """
    Service that handles all on-chain interactions using the relayer wallet.
    """
    
    def __init__(self):
        """Initialize web3 connection and load relayer wallet."""
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
        
        # Load contract ABI
        self.contracts_dir = Path(__file__).parent.parent / "contracts"
        self.abi_path = self.contracts_dir / "VaultContract.abi"
        self._abi = None
    
    async def broadcast_transaction(self, signed_tx_raw: str) -> str:
        """
        Broadcast a signed transaction to the network.
        
        Args:
            signed_tx_raw: RLP-encoded signed transaction as hex string
            
        Returns:
            Transaction hash (0x...)
        """
        # TODO: Implement in Phase 4
        raise NotImplementedError("Broadcast transaction - implement in Phase 4")
    
    async def call_contract_propose(
        self,
        contract_address: str,
        to: str,
        value: int,
        description: str,
        proposed_by: str
    ) -> int:
        """
        Call proposeTransaction() on the vault contract.
        
        Args:
            contract_address: Address of the company's vault contract
            to: Recipient address
            value: Amount in wei
            description: Transaction description
            proposed_by: Address of the proposing executive
            
        Returns:
            On-chain transaction ID
        """
        # TODO: Implement in Phase 4
        raise NotImplementedError("Contract propose - implement in Phase 4")
    
    async def call_contract_approve(
        self,
        contract_address: str,
        tx_id: int,
        approved_by: str,
        tss_signature: bytes
    ) -> Dict[str, Any]:
        """
        Call approveTransaction() on the vault contract.
        
        Args:
            contract_address: Address of the company's vault contract
            tx_id: On-chain transaction ID
            approved_by: Address of the approving executive
            tss_signature: Aggregated TSS signature bytes
            
        Returns:
            Receipt with execution status
        """
        # TODO: Implement in Phase 4
        raise NotImplementedError("Contract approve - implement in Phase 4")
    
    def _load_abi(self) -> List[Dict[str, Any]]:
        """Load contract ABI from file."""
        if self._abi is not None:
            return self._abi
        if not self.abi_path.exists():
            raise RuntimeError("Contract ABI not found. Run deployer.compile_contract() first.")
        self._abi = json.loads(self.abi_path.read_text())
        return self._abi
    
    async def get_vault_balance(self, contract_address: str) -> int:
        """
        Get the ETH balance of a vault contract.
        
        Args:
            contract_address: Address of the vault contract
            
        Returns:
            Balance in wei
        """
        if not self.w3.is_connected():
            raise RuntimeError("Web3 not connected")
        
        checksum_addr = Web3.to_checksum_address(contract_address)
        return self.w3.eth.get_balance(checksum_addr)
    
    async def get_relayer_balance(self) -> int:
        """
        Get the relayer wallet's ETH balance.
        
        Returns:
            Balance in wei
        """
        if not self.w3.is_connected():
            raise RuntimeError("Web3 not connected")
        
        checksum_addr = Web3.to_checksum_address(self.relayer_address)
        return self.w3.eth.get_balance(checksum_addr)
    
    async def call_contract_view(
        self,
        contract_address: str,
        function_name: str,
        *args
    ) -> Any:
        """
        Call a view function on the vault contract.
        
        Args:
            contract_address: Contract address
            function_name: Function to call
            *args: Function arguments
            
        Returns:
            Function return value
        """
        if not self.w3.is_connected():
            raise RuntimeError("Web3 not connected")
        
        abi = self._load_abi()
        checksum_addr = Web3.to_checksum_address(contract_address)
        contract = self.w3.eth.contract(address=checksum_addr, abi=abi)
        
        func = getattr(contract.functions, function_name)
        return func(*args).call()
