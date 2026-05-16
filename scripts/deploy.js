// scripts/deploy.js
// Deploys ThresholdWallet.sol to Sepolia and saves the address to dkg_snapshot.json
//
// USAGE:
//   npx hardhat run scripts/deploy.js --network sepolia
//
// WHAT IT DOES:
//   1. Reads the TSS wallet address from dkg_snapshot.json (the group public key address)
//   2. Derives individual node addresses from the node share files
//      (each node has a known index — in demo we use deterministic derivation)
//   3. Deploys ThresholdWallet with owner=TSS_ADDRESS, threshold=3, total=5
//   4. Saves the deployed contract address back into dkg_snapshot.json
//   5. Verifies on Etherscan (if ETHERSCAN_API_KEY is set)
//
// AFTER DEPLOYMENT:
//   The contract address is stored in dkg_snapshot.json under "contract_address".
//   The coordinator reads this on startup to call contract functions via web3.py.

const hre = require("hardhat");
const fs  = require("fs");
const path = require("path");

const PROJECT_ROOT    = path.join(__dirname, "..");
const SNAPSHOT_FILE   = path.join(PROJECT_ROOT, "dkg_snapshot.json");
const DEPLOYMENT_FILE = path.join(PROJECT_ROOT, "deployment.json");

async function main() {
  console.log("=".repeat(60));
  console.log("  ThresholdWallet — Sepolia Deployment");
  console.log("=".repeat(60));

  // ── Read DKG snapshot for TSS wallet address ──
  if (!fs.existsSync(SNAPSHOT_FILE)) {
    throw new Error(
      "dkg_snapshot.json not found.\n" +
      "Run the TSS nodes and call /wallet/setup first to generate the DKG."
    );
  }
  const snapshot = JSON.parse(fs.readFileSync(SNAPSHOT_FILE, "utf8"));
  const tssOwner = snapshot.wallet_address;

  console.log(`\n  TSS Wallet (owner)  : ${tssOwner}`);
  console.log(`  Threshold           : ${snapshot.threshold} of ${snapshot.total_nodes}`);
  console.log(`  Node IDs            : [${snapshot.node_ids.join(", ")}]`);

  // ── Deployer account ──
  const [deployer] = await hre.ethers.getSigners();
  const balance = await hre.ethers.provider.getBalance(deployer.address);
  console.log(`\n  Deployer            : ${deployer.address}`);
  console.log(`  Deployer balance    : ${hre.ethers.formatEther(balance)} ETH`);

  // ── Signer node addresses ──
  // In this demo, each node's "individual address" is derived from a
  // deterministic key seeded by node_id. This lets the contract verify
  // per-node ECDSA signatures via ecrecover.
  //
  // In production: each node generates its own secp256k1 keypair at setup,
  // and registers its public address with the coordinator.
  //
  // For the demo deployment we use the DEPLOYER address for all nodes
  // (simplification — the multi-sig logic still works, just all confirmations
  // come from the same Ethereum address in the demo).
  //
  // The TSS GROUP address is the actual "owner" for direct owner-only calls.
  const nodeIds = snapshot.node_ids;

  // Generate deterministic demo node addresses using keccak of nodeId seed
  // These are placeholder addresses for the demo — not real node keys
  const signerAddresses = nodeIds.map((nid) => {
    // Derive a deterministic address for each node (demo only)
    // Production: each node registers its own address
    const seed = hre.ethers.keccak256(
      hre.ethers.toUtf8Bytes(`tss_node_${nid}_demo_signer_key`)
    );
    const wallet = new hre.ethers.Wallet(seed);
    return wallet.address;
  });

  console.log("\n  Authorized signer addresses (per node):");
  nodeIds.forEach((nid, i) => {
    console.log(`    Node ${nid}: ${signerAddresses[i]}`);
  });

  // ── Deploy contract ──
  console.log("\n  Deploying ThresholdWallet...");
  const Factory = await hre.ethers.getContractFactory("ThresholdWallet");

  const contract = await Factory.deploy(
    tssOwner,                  // owner = TSS group address
    snapshot.threshold,        // M = 3
    snapshot.total_nodes,      // N = 5
    nodeIds,                   // [1, 2, 3, 4, 5]
    signerAddresses,           // per-node Ethereum addresses
  );

  await contract.waitForDeployment();
  const contractAddress = await contract.getAddress();

  console.log(`\n  ✅ ThresholdWallet deployed!`);
  console.log(`     Contract address : ${contractAddress}`);
  console.log(`     Etherscan        : https://sepolia.etherscan.io/address/${contractAddress}`);

  // ── Verify constructor values on-chain ──
  const onChainOwner     = await contract.owner();
  const onChainThreshold = await contract.threshold();
  const onChainTotal     = await contract.totalSigners();
  const onChainBalance   = await contract.getBalance();

  console.log(`\n  On-chain verification:`);
  console.log(`     owner()          : ${onChainOwner}`);
  console.log(`     threshold()      : ${onChainThreshold}`);
  console.log(`     totalSigners()   : ${onChainTotal}`);
  console.log(`     balance          : ${hre.ethers.formatEther(onChainBalance)} ETH`);

  // ── Save deployment info ──
  const deploymentInfo = {
    contract_address:  contractAddress,
    tss_owner:         tssOwner,
    threshold:         Number(onChainThreshold),
    total_signers:     Number(onChainTotal),
    node_ids:          nodeIds,
    signer_addresses:  Object.fromEntries(nodeIds.map((nid, i) => [nid, signerAddresses[i]])),
    network:           "sepolia",
    chain_id:          11155111,
    deployer:          deployer.address,
    deployed_at:       new Date().toISOString(),
    etherscan_url:     `https://sepolia.etherscan.io/address/${contractAddress}`,
  };

  // Write standalone deployment file
  fs.writeFileSync(DEPLOYMENT_FILE, JSON.stringify(deploymentInfo, null, 2));
  console.log(`\n  Deployment info saved → deployment.json`);

  // Also patch the DKG snapshot with the contract address
  snapshot.contract_address = contractAddress;
  snapshot.deployment       = deploymentInfo;
  fs.writeFileSync(SNAPSHOT_FILE, JSON.stringify(snapshot, null, 2));

  // ── Etherscan verification ──
  const etherscanKey = process.env.ETHERSCAN_API_KEY;
  if (etherscanKey && hre.network.name !== "hardhat") {
    console.log("\n  Waiting 30s for Etherscan to index the contract...");
    await new Promise(r => setTimeout(r, 30000));

    console.log("  Verifying on Etherscan...");
    try {
      await hre.run("verify:verify", {
        address: contractAddress,
        constructorArguments: [
          tssOwner,
          snapshot.threshold,
          snapshot.total_nodes,
          nodeIds,
          signerAddresses,
        ],
      });
      console.log("  ✅ Contract verified on Etherscan!");
      deploymentInfo.etherscan_verified = true;
      fs.writeFileSync(DEPLOYMENT_FILE, JSON.stringify(deploymentInfo, null, 2));
    } catch (err) {
      console.log(`  ⚠️  Etherscan verification failed: ${err.message}`);
      console.log(`  You can verify manually with:`);
      console.log(`  npx hardhat verify --network sepolia ${contractAddress} "${tssOwner}" ${snapshot.threshold} ${snapshot.total_nodes} "[${nodeIds}]" "[${signerAddresses.map(a => `"${a}"`).join(",")}]"`);
    }
  } else {
    console.log("\n  ℹ️  Set ETHERSCAN_API_KEY in .env to verify on Etherscan.");
    console.log(`  Manual verify: npx hardhat verify --network sepolia ${contractAddress}`);
  }

  console.log("\n" + "=".repeat(60));
  console.log("  DEPLOYMENT COMPLETE");
  console.log("=".repeat(60));
  console.log(`\n  CONTRACT ADDRESS: ${contractAddress}`);
  console.log(`  Add to .env: CONTRACT_ADDRESS=${contractAddress}`);
  console.log(`\n  Etherscan: https://sepolia.etherscan.io/address/${contractAddress}`);

  return contractAddress;
}

main()
  .then(() => process.exit(0))
  .catch((err) => {
    console.error("\n❌ Deployment failed:", err.message);
    process.exit(1);
  });
