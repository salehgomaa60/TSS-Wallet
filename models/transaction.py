"""
Transaction model.

Represents a proposed treasury transaction that requires M-of-N approvals.
Shares are NEVER stored here — only public metadata and on-chain identifiers.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, BigInteger, Text, DateTime, ForeignKey, Numeric, ARRAY
from sqlalchemy.dialects.postgresql import UUID
from models import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    proposed_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    to_address = Column(String(42), nullable=False)
    value_wei = Column(BigInteger, nullable=False)
    value_eth = Column(Numeric(20, 8))
    description = Column(Text)
    status = Column(
        String(20),
        default="PENDING",
    )  # PENDING, APPROVED, EXECUTING, EXECUTED, REJECTED, EXPIRED
    tx_hash = Column(String(66))
    raw_transaction = Column(Text)   # RLP encoded signed tx
    signing_session = Column(String(64))  # MPC session ID
    participating_nodes = Column(ARRAY(Integer))
    proposed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True))
    executed_at = Column(DateTime(timezone=True))
    etherscan_url = Column(String(255))
