require("@nomicfoundation/hardhat-toolbox");
require("dotenv").config();

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: {
    version: "0.8.20",
    settings: {
      optimizer: {
        enabled: true,
        runs: 200,
      },
    },
  },

  networks: {
    // Local Hardhat node for fast testing
    hardhat: {
      chainId: 31337,
    },

    // Sepolia testnet — deploy with:
    //   npx hardhat run scripts/deploy.js --network sepolia
    sepolia: {
      url: process.env.INFURA_URL || "https://sepolia.infura.io/v3/959d08b688b3498a962aee11daf55d38",
      accounts: process.env.FUNDER_PRIVATE_KEY
        ? [`0x${process.env.FUNDER_PRIVATE_KEY.replace("0x", "")}`]
        : [],
      chainId: 11155111,
      gasPrice: "auto",
    },
  },

  // Etherscan verification — set ETHERSCAN_API_KEY in .env for --verify
  etherscan: {
    apiKey: {
      sepolia: process.env.ETHERSCAN_API_KEY || "",
    },
  },

  // Gas reporter — npm install hardhat-gas-reporter for reporting
  gasReporter: {
    enabled: process.env.REPORT_GAS === "true",
    currency: "USD",
  },

  // Output paths
  paths: {
    sources:   "./contracts",
    tests:     "./tests",
    cache:     "./cache",
    artifacts: "./artifacts",
  },
};
