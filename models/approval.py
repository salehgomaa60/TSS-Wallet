"""
Approval model.

Records each executive's approval of a transaction, including the partial
signature produced by their assigned TSS node. Partial signatures are public
verifiable values that reveal nothing about the underlying Shamir share.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, UniqueConstraint, JSON
from sqlalchemy.dialects.postgresql import UUID
from models import Base


class Approval(Base):
    __tablename__ = "approvals"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    transaction_id = Column(
        UUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    node_id = Column(Integer)  # which node produced partial sig
    partial_signature = Column(JSON)  # {r: hex, s: hex}
    signed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    ip_address = Column(String(45))

    __table_args__ = (
        UniqueConstraint("transaction_id", "user_id", name="uq_approval_tx_user"),
    )
