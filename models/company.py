"""
Company (Vault Tenant) model.

Each company gets its own isolated vault with a deployed Solidity contract,
a TSS-generated Ethereum address, and a unique DKG session.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Boolean, DateTime, JSON
from sqlalchemy.dialects.postgresql import UUID
from models import Base


class Company(Base):
    __tablename__ = "companies"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    plan = Column(String(50), default="starter")
    threshold = Column(Integer, nullable=False, default=2)
    total_signers = Column(Integer, nullable=False, default=3)
    contract_address = Column(String(42))   # set after vault deployment
    eth_address = Column(String(42))        # TSS wallet address from DKG
    group_public_key = Column(JSON)         # {x: hex, y: hex}
    dkg_session_id = Column(String(64))     # links to node DKG session
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
