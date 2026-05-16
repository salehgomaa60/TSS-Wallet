// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title ThresholdWallet
 * @notice A multi-party wallet controlled by a TSS (Threshold Signature Scheme) node network.
 *
 * @dev ARCHITECTURE:
 *   The TSS node network acts as the "owner" of this contract.
 *   The owner address is derived from the group public key — the private key
 *   was NEVER assembled anywhere (Distributed Key Generation, no dealer).
 *
 *   Transaction flow:
 *     1. Any authorized signer proposes a transaction   → proposeTransaction()
 *     2. M-of-N signers confirm it via ECDSA signatures → confirmTransaction()
 *     3. When confirmations >= threshold, it executes   → executeTransaction()
 *
 *   The TSS nodes sign the transaction hash off-chain.
 *   ecrecover() on-chain verifies each partial signer is an authorized address.
 *
 * @dev SECURITY PROPERTIES:
 *   - No single node can move funds (threshold enforcement)
 *   - Replay protection: each txId is unique, each sig bound to txId + chainId
 *   - Owner rotation: the group key can be migrated via M-of-N approval
 *   - Reentrancy guard on executeTransaction
 *
 * @dev DEPLOYMENT:
 *   constructor(owner, threshold, totalSigners, authorizedSigners[])
 *   owner            = TSS group Ethereum address (from group public key)
 *   threshold        = M (minimum confirmations to execute)
 *   totalSigners     = N (total nodes in the TSS network)
 *   authorizedSigners = list of N individual node addresses (for ecrecover)
 *
 * @author TSS Wallet Project
 */
contract ThresholdWallet {

    // ─────────────────────────────────────────────
    // State Variables
    // ─────────────────────────────────────────────

    /// @notice The TSS group address — derived from the group public key.
    ///         Signing requires M-of-N TSS nodes to cooperate.
    address public owner;

    /// @notice M — minimum number of confirmations required to execute a tx.
    uint256 public threshold;

    /// @notice N — total number of nodes in the TSS network.
    uint256 public totalSigners;

    /// @notice Total number of proposed transactions (used as txId counter).
    uint256 public txCount;

    /// @notice Whether the contract is locked (reentrancy guard).
    bool private _locked;

    /// @notice Addresses of the N authorized signer nodes.
    ///         Each node has an individual Ethereum address for ecrecover.
    mapping(uint256 => address) public signerAddresses;  // nodeId → address
    uint256[] public signerNodeIds;

    /// @notice Transactions proposed to this wallet.
    mapping(uint256 => Transaction) public transactions;

    /// @notice Confirmation tracking: txId → signerAddress → confirmed
    mapping(uint256 => mapping(address => bool)) public confirmations;

    // ─────────────────────────────────────────────
    // Structs
    // ─────────────────────────────────────────────

    struct Transaction {
        address to;           ///< Recipient address
        uint256 value;        ///< ETH value in wei
        bytes data;           ///< Call data (empty for ETH transfers)
        bool executed;        ///< Whether this tx has been executed
        uint256 confirmCount; ///< Current number of confirmations
        address proposedBy;   ///< Who proposed this transaction
        uint256 proposedAt;   ///< Block timestamp of proposal
    }

    // ─────────────────────────────────────────────
    // Events
    // ─────────────────────────────────────────────

    /// @notice Emitted when a new transaction is proposed.
    event TransactionProposed(
        uint256 indexed txId,
        address indexed proposedBy,
        address indexed to,
        uint256 value,
        bytes data
    );

    /// @notice Emitted when a signer confirms a transaction.
    event TransactionConfirmed(
        uint256 indexed txId,
        address indexed signer,
        uint256 confirmCount
    );

    /// @notice Emitted when a transaction is executed on-chain.
    event TransactionExecuted(
        uint256 indexed txId,
        address indexed to,
        uint256 value,
        bool success
    );

    /// @notice Emitted when a confirmation is revoked before execution.
    event ConfirmationRevoked(uint256 indexed txId, address indexed signer);

    /// @notice Emitted when the group key (owner) is rotated.
    event OwnerRotated(address indexed oldOwner, address indexed newOwner);

    /// @notice Emitted when ETH is received.
    event Received(address indexed from, uint256 amount);

    /// @notice Emitted when threshold or signer set changes.
    event ThresholdUpdated(uint256 oldThreshold, uint256 newThreshold);

    // ─────────────────────────────────────────────
    // Modifiers
    // ─────────────────────────────────────────────

    modifier onlyOwner() {
        require(msg.sender == owner, "ThresholdWallet: caller is not the TSS owner");
        _;
    }

    modifier onlyAuthorizedSigner() {
        require(_isAuthorizedSigner(msg.sender), "ThresholdWallet: caller is not an authorized signer");
        _;
    }

    modifier txExists(uint256 txId) {
        require(txId < txCount, "ThresholdWallet: transaction does not exist");
        _;
    }

    modifier notExecuted(uint256 txId) {
        require(!transactions[txId].executed, "ThresholdWallet: transaction already executed");
        _;
    }

    modifier notConfirmed(uint256 txId) {
        require(!confirmations[txId][msg.sender], "ThresholdWallet: already confirmed");
        _;
    }

    modifier noReentrant() {
        require(!_locked, "ThresholdWallet: reentrant call");
        _locked = true;
        _;
        _locked = false;
    }

    // ─────────────────────────────────────────────
    // Constructor
    // ─────────────────────────────────────────────

    /**
     * @notice Deploys the ThresholdWallet.
     *
     * @param _owner           TSS group Ethereum address (from DKG group public key)
     * @param _threshold       M — minimum confirmations to execute
     * @param _totalSigners    N — total authorized nodes
     * @param _signerNodeIds   Array of node IDs (e.g. [1,2,3,4,5])
     * @param _signerAddresses Array of Ethereum addresses for each node (for ecrecover)
     *
     * @dev The owner address is the primary signer for direct calls.
     *      Individual node addresses allow per-node ecrecover verification.
     *      In the demo, _owner == TSS group address, and _signerAddresses
     *      are individual node addresses derived from each node's own key.
     */
    constructor(
        address _owner,
        uint256 _threshold,
        uint256 _totalSigners,
        uint256[] memory _signerNodeIds,
        address[] memory _signerAddresses
    ) {
        require(_owner != address(0), "ThresholdWallet: invalid owner");
        require(_threshold > 0, "ThresholdWallet: threshold must be > 0");
        require(_threshold <= _totalSigners, "ThresholdWallet: threshold > totalSigners");
        require(_signerNodeIds.length == _signerAddresses.length, "ThresholdWallet: nodeIds/addresses length mismatch");
        require(_signerAddresses.length == _totalSigners, "ThresholdWallet: wrong number of signer addresses");

        owner         = _owner;
        threshold     = _threshold;
        totalSigners  = _totalSigners;

        for (uint256 i = 0; i < _signerNodeIds.length; i++) {
            require(_signerAddresses[i] != address(0), "ThresholdWallet: zero signer address");
            uint256 nodeId = _signerNodeIds[i];
            signerAddresses[nodeId] = _signerAddresses[i];
            signerNodeIds.push(nodeId);
        }
    }

    // ─────────────────────────────────────────────
    // Receive ETH
    // ─────────────────────────────────────────────

    /// @notice Accepts ETH deposits. Anyone can fund this wallet.
    receive() external payable {
        emit Received(msg.sender, msg.value);
    }

    // ─────────────────────────────────────────────
    // Core Transaction Flow
    // ─────────────────────────────────────────────

    /**
     * @notice Proposes a new transaction for multi-sig approval.
     *
     * @dev Any authorized signer (node address) or the owner can propose.
     *      The tx is stored with a unique txId and awaits M confirmations.
     *
     * @param to    Recipient address
     * @param value ETH to send in wei (0 for contract calls)
     * @param data  Call data (empty bytes for plain ETH transfers)
     *
     * @return txId The unique ID of the proposed transaction
     */
    function proposeTransaction(
        address to,
        uint256 value,
        bytes calldata data
    ) external returns (uint256 txId) {
        require(
            msg.sender == owner || _isAuthorizedSigner(msg.sender),
            "ThresholdWallet: not authorized to propose"
        );
        require(to != address(0), "ThresholdWallet: invalid recipient");

        txId = txCount;
        transactions[txId] = Transaction({
            to:           to,
            value:        value,
            data:         data,
            executed:     false,
            confirmCount: 0,
            proposedBy:   msg.sender,
            proposedAt:   block.timestamp
        });
        txCount++;

        emit TransactionProposed(txId, msg.sender, to, value, data);
    }

    /**
     * @notice Confirms a proposed transaction using an ECDSA signature.
     *
     * @dev The signature must be over the transaction hash:
     *        keccak256(abi.encodePacked(txId, to, value, data, chainId, address(this)))
     *
     *      ecrecover(hash, v, r, s) must return an authorized signer address.
     *      Each address can only confirm once.
     *      If confirmations reach threshold, executeTransaction is called.
     *
     * @param txId  ID of the transaction to confirm
     * @param v     ECDSA signature component (27 or 28)
     * @param r     ECDSA signature component
     * @param s     ECDSA signature component
     */
    function confirmTransaction(
        uint256 txId,
        uint8 v,
        bytes32 r,
        bytes32 s
    ) external txExists(txId) notExecuted(txId) {
        Transaction storage txn = transactions[txId];

        // Compute the message that the signer should have signed
        bytes32 txHash = getTxHash(txId);

        // ecrecover — who signed this hash?
        address recovered = ecrecover(txHash, v, r, s);
        require(recovered != address(0), "ThresholdWallet: invalid signature");
        require(_isAuthorizedSigner(recovered), "ThresholdWallet: signer not authorized");
        require(!confirmations[txId][recovered], "ThresholdWallet: signer already confirmed");

        // Record confirmation
        confirmations[txId][recovered] = true;
        txn.confirmCount++;

        emit TransactionConfirmed(txId, recovered, txn.confirmCount);

        // Auto-execute when threshold is reached
        if (txn.confirmCount >= threshold) {
            _executeTransaction(txId);
        }
    }

    /**
     * @notice Revokes a previously submitted confirmation (before execution).
     *
     * @param txId  ID of the transaction to revoke confirmation for
     * @param v     The same v used when confirming (to identify which signer)
     * @param r     The same r used when confirming
     * @param s     The same s used when confirming
     */
    function revokeConfirmation(
        uint256 txId,
        uint8 v,
        bytes32 r,
        bytes32 s
    ) external txExists(txId) notExecuted(txId) {
        bytes32 txHash = getTxHash(txId);
        address recovered = ecrecover(txHash, v, r, s);
        require(recovered != address(0), "ThresholdWallet: invalid signature");
        require(confirmations[txId][recovered], "ThresholdWallet: not confirmed");

        confirmations[txId][recovered] = false;
        transactions[txId].confirmCount--;

        emit ConfirmationRevoked(txId, recovered);
    }

    /**
     * @notice Manually triggers execution if threshold is met.
     *         Normally called automatically from confirmTransaction().
     *
     * @param txId  ID of the transaction to execute
     */
    function executeTransaction(
        uint256 txId
    ) external txExists(txId) notExecuted(txId) noReentrant {
        require(
            transactions[txId].confirmCount >= threshold,
            "ThresholdWallet: insufficient confirmations"
        );
        _executeTransaction(txId);
    }

    // ─────────────────────────────────────────────
    // Owner Rotation (Key Migration)
    // ─────────────────────────────────────────────

    /**
     * @notice Rotates the TSS group owner address.
     *
     * @dev Called by the CURRENT owner (the TSS network) to migrate to a
     *      new group public key (e.g. after node replacement or resharing).
     *      Requires a valid TSS signature from the current group.
     *
     *      In the demo: the coordinator calls this after a re-DKG,
     *      sending the TSS-signed transaction that calls rotateOwner().
     *
     * @param newOwner New TSS group Ethereum address
     */
    function rotateOwner(address newOwner) external onlyOwner {
        require(newOwner != address(0), "ThresholdWallet: invalid new owner");
        require(newOwner != owner, "ThresholdWallet: same owner");

        address oldOwner = owner;
        owner = newOwner;

        emit OwnerRotated(oldOwner, newOwner);
    }

    /**
     * @notice Updates the set of authorized signer addresses.
     *         Called by the owner after node resharing or replacement.
     *
     * @param _signerNodeIds   New node ID list
     * @param _signerAddresses New address list (parallel to nodeIds)
     */
    function updateSigners(
        uint256[] calldata _signerNodeIds,
        address[] calldata _signerAddresses
    ) external onlyOwner {
        require(_signerNodeIds.length == _signerAddresses.length, "length mismatch");

        // Clear old signer mapping
        for (uint256 i = 0; i < signerNodeIds.length; i++) {
            delete signerAddresses[signerNodeIds[i]];
        }
        delete signerNodeIds;

        // Write new signers
        for (uint256 i = 0; i < _signerNodeIds.length; i++) {
            require(_signerAddresses[i] != address(0), "zero address");
            signerAddresses[_signerNodeIds[i]] = _signerAddresses[i];
            signerNodeIds.push(_signerNodeIds[i]);
        }

        totalSigners = _signerNodeIds.length;
    }

    /**
     * @notice Updates the confirmation threshold.
     * @param newThreshold New M value
     */
    function updateThreshold(uint256 newThreshold) external onlyOwner {
        require(newThreshold > 0, "ThresholdWallet: threshold must be > 0");
        require(newThreshold <= totalSigners, "ThresholdWallet: threshold > totalSigners");
        uint256 old = threshold;
        threshold = newThreshold;
        emit ThresholdUpdated(old, newThreshold);
    }

    // ─────────────────────────────────────────────
    // View / Query Functions
    // ─────────────────────────────────────────────

    /**
     * @notice Returns the hash that signers must sign to confirm a transaction.
     *
     * @dev Hash includes: txId, to, value, data, chainId, contract address.
     *      Including chainId and address(this) prevents replay across chains
     *      or across different wallet deployments.
     *
     * @param txId  ID of the transaction
     * @return      keccak256 hash — feed this to eth_sign or personal_sign
     */
    function getTxHash(uint256 txId) public view txExists(txId) returns (bytes32) {
        Transaction storage txn = transactions[txId];
        return keccak256(abi.encodePacked(
            "\x19Ethereum Signed Message:\n32",
            keccak256(abi.encodePacked(
                txId,
                txn.to,
                txn.value,
                txn.data,
                block.chainid,
                address(this)
            ))
        ));
    }

    /**
     * @notice Returns whether a specific address has confirmed a transaction.
     * @param txId    Transaction ID
     * @param signer  Address to check
     */
    function hasConfirmed(uint256 txId, address signer) external view returns (bool) {
        return confirmations[txId][signer];
    }

    /**
     * @notice Returns full transaction details.
     */
    function getTransaction(uint256 txId) external view txExists(txId) returns (
        address to,
        uint256 value,
        bytes memory data,
        bool executed,
        uint256 confirmCount,
        address proposedBy,
        uint256 proposedAt
    ) {
        Transaction storage txn = transactions[txId];
        return (
            txn.to,
            txn.value,
            txn.data,
            txn.executed,
            txn.confirmCount,
            txn.proposedBy,
            txn.proposedAt
        );
    }

    /**
     * @notice Returns this wallet's current ETH balance.
     */
    function getBalance() external view returns (uint256) {
        return address(this).balance;
    }

    /**
     * @notice Returns all authorized signer node IDs.
     */
    function getSignerNodeIds() external view returns (uint256[] memory) {
        return signerNodeIds;
    }

    /**
     * @notice Returns a list of all pending (unexecuted) transaction IDs.
     */
    function getPendingTransactions() external view returns (uint256[] memory) {
        uint256 pendingCount = 0;
        for (uint256 i = 0; i < txCount; i++) {
            if (!transactions[i].executed) pendingCount++;
        }
        uint256[] memory pending = new uint256[](pendingCount);
        uint256 idx = 0;
        for (uint256 i = 0; i < txCount; i++) {
            if (!transactions[i].executed) pending[idx++] = i;
        }
        return pending;
    }

    // ─────────────────────────────────────────────
    // Internal Functions
    // ─────────────────────────────────────────────

    /**
     * @dev Executes a transaction after threshold confirmations are met.
     *      Protected against reentrancy via _locked flag.
     */
    function _executeTransaction(uint256 txId) internal noReentrant {
        Transaction storage txn = transactions[txId];
        require(!txn.executed, "ThresholdWallet: already executed");
        require(txn.confirmCount >= threshold, "ThresholdWallet: not enough confirmations");
        require(address(this).balance >= txn.value, "ThresholdWallet: insufficient balance");

        txn.executed = true;

        (bool success, ) = txn.to.call{value: txn.value}(txn.data);

        emit TransactionExecuted(txId, txn.to, txn.value, success);

        // If execution failed, revert the executed flag so it can be retried
        if (!success) {
            txn.executed = false;
            revert("ThresholdWallet: execution failed");
        }
    }

    /**
     * @dev Returns true if addr is in the authorized signer set.
     */
    function _isAuthorizedSigner(address addr) internal view returns (bool) {
        for (uint256 i = 0; i < signerNodeIds.length; i++) {
            if (signerAddresses[signerNodeIds[i]] == addr) return true;
        }
        return false;
    // ─────────────────────────────────────────────
    // TSS Direct Execution
    // ─────────────────────────────────────────────

    /**
     * @notice Executes a transaction directly using a threshold signature (TSS) from the owner.
     * @dev The TSS network generates a single ECDSA signature off-chain.
     */
    function executeByTSS(
        address _to,
        uint256 _value,
        bytes calldata _data,
        uint8 v,
        bytes32 r,
        bytes32 s
    ) external noReentrant {
        bytes32 txHash = keccak256(abi.encodePacked(
            "\x19Ethereum Signed Message:\n32",
            keccak256(abi.encodePacked(txCount, _to, _value, _data, block.chainid, address(this)))
        ));
        
        address recovered = ecrecover(txHash, v, r, s);
        require(recovered == owner, "ThresholdWallet: invalid TSS signature");
        
        txCount++;
        
        (bool success, ) = _to.call{value: _value}(_data);
        require(success, "ThresholdWallet: execution failed");
        
        emit TransactionExecuted(txCount - 1, _to, _value, success);
    }
}
