"""
Audit Log model.

Immutable record of every significant action taken in the system.
This is the database-layer equivalent of the on-chain audit trail.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from models import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True,  # null for platform-level admin actions
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    action = Column(
        String(100),
        nullable=False,
    )  # COMPANY_CREATED, USER_INVITED, TX_PROPOSED, TX_APPROVED,
      # TX_EXECUTED, TX_REJECTED, LOGIN, LOGOUT,
      # THRESHOLD_CHANGED, VAULT_DEPLOYED, DKG_COMPLETED
    details = Column(JSON)  # action-specific data
    ip_address = Column(String(45))
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
