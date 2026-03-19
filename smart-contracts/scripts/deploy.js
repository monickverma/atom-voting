const hre = require("hardhat");

async function main() {
  const [deployer] = await hre.ethers.getSigners();
  
  if (!deployer) {
    console.error("❌ No private key found! Check your .env setup.");
    process.exit(1);
  }

  console.log("========================================");
  console.log("🌐 Deploying VoteLedger to Base Sepolia");
  console.log("👤 Deployer Account:", deployer.address);
  
  const balance = await hre.ethers.provider.getBalance(deployer.address);
  console.log("💰 Account Balance:", hre.ethers.formatEther(balance), "ETH");
  console.log("========================================");

  if (balance === 0n) {
    console.error("\n❌ INSUFFICIENT ETH: You need some Base Sepolia ETH to deploy.");
    console.log("Get free testnet ETH at: https://faucets.chain.link/base-sepolia");
    process.exit(1);
  }

  const Contract = await hre.ethers.getContractFactory("VoteLedger");
  console.log("\n🚀 Compiling and deploying...");
  const ledger = await Contract.deploy();

  await ledger.waitForDeployment();
  const address = await ledger.getAddress();

  console.log("========================================");
  console.log(`✅ SUCCESS! VoteLedger anchored to Base Sepolia`);
  console.log(`📝 Contract Address: ${address}`);
  console.log(`🔍 View on Blockscout: https://base-sepolia.blockscout.com/address/${address}`);
  console.log("========================================");
  console.log("\nNext Steps:");
  console.log("Copy the Contract Address above and we will add it to the Python backend.");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
