from __future__ import annotations

from uuid import uuid4

from sqlalchemy import Column, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from app.domain.models.base import Base, TimestampMixin


class RoleAuditEvent(Base, TimestampMixin):
    """Audit trail for user role changes."""

    __tablename__ = "role_audit_events"

    id = Column(String(32), primary_key=True, default=lambda: uuid4().hex)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    actor_user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    from_role = Column(String(32), nullable=False)
    to_role = Column(String(32), nullable=False)
    reason = Column(Text, nullable=True)
    batch_id = Column(String(32), nullable=True, index=True)

    user = relationship("User", foreign_keys=[user_id], backref="role_audit_subject_events")
    actor = relationship("User", foreign_keys=[actor_user_id], backref="role_audit_actor_events")
