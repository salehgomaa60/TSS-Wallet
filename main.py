"""
TSS Vault - Corporate Treasury Management System
Main FastAPI Application

This is the upgraded coordinator that serves as the API gateway
for the enterprise TSS Vault platform.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import routers
from routers import auth, companies, transactions, nodes, admin, vault, wallet


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    print("=" * 70)
    print("TSS VAULT STARTING")
    print("=" * 70)
    
    # Check environment
    required_vars = [
        "INFURA_URL",
        "RELAYER_PRIVATE_KEY",
        "RELAYER_ADDRESS",
        "JWT_SECRET",
        "DATABASE_URL"
    ]
    
    missing = [v for v in required_vars if not os.getenv(v)]
    if missing:
        print(f"WARNING: Missing environment variables: {missing}")
    else:
        print("All required environment variables set.")
    
    # Check contract compilation
    contracts_dir = os.path.dirname(__file__) + "/contracts"
    abi_file = f"{contracts_dir}/VaultContract.abi"
    if os.path.exists(abi_file):
        print("Vault contract ABI found.")
    else:
        print("WARNING: Vault contract ABI not found. Run deployer.compile_contract()")
    
    print("=" * 70)
    
    yield
    
    # Shutdown
    print("TSS VAULT SHUTTING DOWN")


# Create FastAPI app
app = FastAPI(
    title="TSS Vault API",
    description="Enterprise Corporate Treasury Management with TSS",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_URL", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(companies.router)
app.include_router(transactions.router)
app.include_router(nodes.router)
app.include_router(admin.router)
app.include_router(vault.router)
app.include_router(wallet.router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "online",
        "service": "tss-vault-api",
        "version": "1.0.0"
    }


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "name": "TSS Vault API",
        "version": "1.0.0",
        "description": "Enterprise Corporate Treasury Management with TSS",
        "docs": "/docs",
        "health": "/health"
    }


if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.getenv("PORT", "8006"))
    uvicorn.run(app, host="0.0.0.0", port=port)
