"""
SQLAlchemy async database configuration for TSS Vault.

Uses PostgreSQL with asyncpg driver and SQLAlchemy 2.0 async ORM patterns.
All models use UUID primary keys and timezone-aware timestamps.
"""

import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/tss_vault",
)

# Create async engine
def get_engine():
    """Returns the async SQLAlchemy engine."""
    return create_async_engine(
        DATABASE_URL,
        echo=False,
        poolclass=NullPool,  # Recommended for async/FastAPI
        future=True,
    )


# Async session factory
AsyncSessionLocal = async_sessionmaker(
    bind=get_engine(),
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# Declarative base for all models
Base = declarative_base()


async def get_db():
    """FastAPI dependency that yields an async DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Create all tables (used for dev/testing; prefer Alembic in production)."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
