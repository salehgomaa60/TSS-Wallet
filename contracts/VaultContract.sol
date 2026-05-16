// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title CorporateVault
 * @notice Enterprise multi-signature treasury vault with TSS integration
 * @dev Each company gets their own deployed instance. The relayer handles all
 *      gas costs so companies never need ETH or MetaMask.
 */
contract CorporateVault {
    
    // ── State ──────────────────────────────────────────────────
    address public relayer;
    address public tssWalletAddress;  // the TSS group public key address
    uint256 public threshold;
    uint256 public spendingLimitWei;
    uint256 public dailySpentWei;
    uint256 public lastResetDay;
    bool public vaultLocked;
    
    mapping(address => bool) public isExecutive;
    mapping(address => string) public executiveNames;
    address[] public executives;
    
    uint256 public transactionCount;
    mapping(uint256 => VaultTransaction) public transactions;
    mapping(uint256 => mapping(address => bool)) public hasApproved;
    mapping(uint256 => uint256) public approvalCount;
    
    // ── Structs ────────────────────────────────────────────────
    struct VaultTransaction {
        uint256 id;
        address to;
        uint256 value;
        string description;
        address proposedBy;
        uint256 proposedAt;
        uint256 expiresAt;
        bool executed;
        bool cancelled;
        bytes32 txHash;
    }
    
    // ── Events (on-chain audit trail) ──────────────────────────
    event VaultCreated(address indexed tssAddress, uint256 threshold);
    event TransactionProposed(
        uint256 indexed txId, 
        address indexed proposedBy, 
        address to, 
        uint256 value,
        string description
    );
    event TransactionApproved(
        uint256 indexed txId, 
        address indexed approvedBy,
        uint256 approvalsCount,
        uint256 threshold
    );
    event TransactionExecuted(
        uint256 indexed txId, 
        bytes32 txHash,
        address to,
        uint256 value
    );
    event TransactionCancelled(uint256 indexed txId, address by);
    event ExecutiveAdded(address indexed executive, string name);
    event ExecutiveRemoved(address indexed executive);
    event ThresholdChanged(uint256 oldThreshold, uint256 newThreshold);
    event FundsReceived(address indexed from, uint256 value);
    event SpendingLimitChanged(uint256 newLimit);
    
    // ── Modifiers ──────────────────────────────────────────────
    modifier onlyRelayer() {
        require(msg.sender == relayer, "Only relayer");
        _;
    }
    
    modifier onlyExecutive() {
        require(isExecutive[msg.sender], "Not an executive");
        _;
    }
    
    modifier txExists(uint256 txId) {
        require(txId < transactionCount, "Tx does not exist");
        _;
    }
    
    modifier notExecuted(uint256 txId) {
        require(!transactions[txId].executed, "Already executed");
        _;
    }
    
    modifier notExpired(uint256 txId) {
        require(
            block.timestamp < transactions[txId].expiresAt, 
            "Transaction expired"
        );
        _;
    }
    
    // ── Constructor ────────────────────────────────────────────
    constructor(
        address _relayer,
        address _tssWalletAddress,
        address[] memory _executives,
        string[] memory _executiveNames,
        uint256 _threshold,
        uint256 _spendingLimitWei
    ) {
        require(_executives.length >= _threshold, "Not enough executives");
        require(_threshold > 0, "Threshold must be > 0");
        
        relayer = _relayer;
        tssWalletAddress = _tssWalletAddress;
        threshold = _threshold;
        spendingLimitWei = _spendingLimitWei;
        lastResetDay = block.timestamp / 1 days;
        
        for (uint i = 0; i < _executives.length; i++) {
            isExecutive[_executives[i]] = true;
            executiveNames[_executives[i]] = _executiveNames[i];
            executives.push(_executives[i]);
        }
        
        emit VaultCreated(_tssWalletAddress, _threshold);
    }
    
    // ── Core Functions ─────────────────────────────────────────
    
    /**
     * @notice Propose a new treasury transaction
     * @dev Called by relayer when executive proposes via dashboard
     * @param _to Recipient address
     * @param _value Amount in wei
     * @param _description Purpose of the transaction
     * @param _proposedBy Address of the proposing executive
     * @return txId The on-chain transaction ID
     */
    function proposeTransaction(
        address _to,
        uint256 _value,
        string memory _description,
        address _proposedBy
    ) external onlyRelayer returns (uint256) {
        require(_to != address(0), "Invalid recipient");
        require(_value > 0, "Value must be > 0");
        require(_value <= address(this).balance, "Insufficient balance");
        
        uint256 txId = transactionCount++;
        transactions[txId] = VaultTransaction({
            id: txId,
            to: _to,
            value: _value,
            description: _description,
            proposedBy: _proposedBy,
            proposedAt: block.timestamp,
            expiresAt: block.timestamp + 48 hours,
            executed: false,
            cancelled: false,
            txHash: bytes32(0)
        });
        
        emit TransactionProposed(txId, _proposedBy, _to, _value, _description);
        return txId;
    }
    
    /**
     * @notice Approve a pending transaction
     * @dev Called by relayer when executive approves via dashboard.
     *      The tssSignature is the aggregated signature from threshold nodes.
     * @param _txId Transaction ID to approve
     * @param _approvedBy Address of the approving executive
     * @param _tssSignature Aggregated TSS signature bytes
     */
    function approveTransaction(
        uint256 _txId,
        address _approvedBy,
        bytes memory _tssSignature
    ) external onlyRelayer txExists(_txId) notExecuted(_txId) notExpired(_txId) {
        require(isExecutive[_approvedBy], "Not an executive");
        require(!hasApproved[_txId][_approvedBy], "Already approved");
        
        // Verify the TSS signature from this executive's node
        bytes32 txHash = keccak256(abi.encodePacked(
            transactions[_txId].to,
            transactions[_txId].value,
            _txId
        ));
        
        address recovered = recoverSigner(txHash, _tssSignature);
        require(recovered == tssWalletAddress, "Invalid TSS signature");
        
        hasApproved[_txId][_approvedBy] = true;
        approvalCount[_txId]++;
        
        emit TransactionApproved(
            _txId, 
            _approvedBy, 
            approvalCount[_txId], 
            threshold
        );
        
        // Auto-execute when threshold reached
        if (approvalCount[_txId] >= threshold) {
            _executeTransaction(_txId);
        }
    }
    
    /**
     * @notice Internal execution - called automatically when threshold reached
     * @param _txId Transaction ID to execute
     */
    function _executeTransaction(uint256 _txId) internal {
        VaultTransaction storage txn = transactions[_txId];
        
        // Enforce spending limit
        _resetDailyLimitIfNeeded();
        require(
            dailySpentWei + txn.value <= spendingLimitWei,
            "Exceeds daily spending limit"
        );
        
        txn.executed = true;
        dailySpentWei += txn.value;
        
        // Execute the transfer
        (bool success, ) = txn.to.call{value: txn.value}("");
        require(success, "Transfer failed");
        
        bytes32 txHash = keccak256(abi.encodePacked(
            txn.to, txn.value, block.timestamp
        ));
        txn.txHash = txHash;
        
        emit TransactionExecuted(_txId, txHash, txn.to, txn.value);
    }
    
    // ── Helper Functions ───────────────────────────────────────
    
    /**
     * @notice Recover signer address from signature
     * @param hash The message hash that was signed
     * @param signature The signature bytes
     * @return The recovered address
     */
    function recoverSigner(
        bytes32 hash, 
        bytes memory signature
    ) internal pure returns (address) {
        bytes32 ethHash = keccak256(abi.encodePacked(
            "\x19Ethereum Signed Message:\n32", hash
        ));
        (bytes32 r, bytes32 s, uint8 v) = splitSignature(signature);
        return ecrecover(ethHash, v, r, s);
    }
    
    /**
     * @notice Split signature into r, s, v components
     * @param sig The signature bytes (65 bytes)
     * @return r The r component
     * @return s The s component  
     * @return v The recovery id
     */
    function splitSignature(
        bytes memory sig
    ) internal pure returns (bytes32 r, bytes32 s, uint8 v) {
        require(sig.length == 65, "Invalid signature length");
        assembly {
            r := mload(add(sig, 32))
            s := mload(add(sig, 64))
            v := byte(0, mload(add(sig, 96)))
        }
    }
    
    /**
     * @notice Reset daily spending limit if a new day has started
     */
    function _resetDailyLimitIfNeeded() internal {
        uint256 today = block.timestamp / 1 days;
        if (today > lastResetDay) {
            dailySpentWei = 0;
            lastResetDay = today;
        }
    }
    
    // ── View Functions ─────────────────────────────────────────
    
    /**
     * @notice Get full transaction details
     * @param txId Transaction ID
     * @return The VaultTransaction struct
     */
    function getTransaction(uint256 txId) 
        external view returns (VaultTransaction memory) {
        return transactions[txId];
    }
    
    /**
     * @notice Get current approval count for a transaction
     * @param txId Transaction ID
     * @return Number of approvals received
     */
    function getApprovalCount(uint256 txId) 
        external view returns (uint256) {
        return approvalCount[txId];
    }
    
    /**
     * @notice Get contract ETH balance
     * @return Balance in wei
     */
    function getBalance() external view returns (uint256) {
        return address(this).balance;
    }
    
    /**
     * @notice Get list of all executives
     * @return Array of executive addresses
     */
    function getExecutives() external view returns (address[] memory) {
        return executives;
    }
    
    /**
     * @notice Check if an address is an executive
     * @param addr Address to check
     * @return True if executive
     */
    function checkIsExecutive(address addr) external view returns (bool) {
        return isExecutive[addr];
    }
    
    // ── Admin Functions (require threshold approval) ───────────
    
    /**
     * @notice Update the required approval threshold
     * @dev Only callable by relayer after threshold approval off-chain
     * @param newThreshold New threshold value
     */
    function updateThreshold(uint256 newThreshold) 
        external onlyRelayer {
        require(newThreshold > 0, "Invalid threshold");
        require(newThreshold <= executives.length, "Too high");
        emit ThresholdChanged(threshold, newThreshold);
        threshold = newThreshold;
    }
    
    /**
     * @notice Update the daily spending limit
     * @dev Only callable by relayer after threshold approval off-chain
     * @param newLimit New limit in wei
     */
    function updateSpendingLimit(uint256 newLimit) 
        external onlyRelayer {
        spendingLimitWei = newLimit;
        emit SpendingLimitChanged(newLimit);
    }
    
    // ── Receive ETH ────────────────────────────────────────────
    
    /**
     * @notice Receive ETH deposits
     */
    receive() external payable {
        emit FundsReceived(msg.sender, msg.value);
    }
    
    /**
     * @notice Fallback for direct ETH transfers with data
     */
    fallback() external payable {
        emit FundsReceived(msg.sender, msg.value);
    }
}
