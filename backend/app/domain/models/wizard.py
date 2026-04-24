from __future__ import annotations

from uuid import uuid4

from sqlalchemy import Column, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.domain.models.base import Base, TimestampMixin


class WizardSession(Base, TimestampMixin):
    """Wizard session that stores multi-step AI drafting state."""

    __tablename__ = "wizard_sessions"

    id = Column(String(32), primary_key=True, default=lambda: uuid4().hex)
    project_id = Column(String(32), ForeignKey("projects.id"), nullable=True, index=True)
    owner_id = Column(String(32), ForeignKey("users.id"), nullable=True, index=True)

    status = Column(String(32), nullable=False, default="active")
    current_step = Column(Integer, nullable=False, default=1)

    # Raw story input provided by the author.
    input_payload = Column(JSON, nullable=True)

    # Per-step drafts/results and approvals.
    drafts = Column(JSON, nullable=True)
    approvals = Column(JSON, nullable=True)

    # Optional meta (warnings/errors/usage) aggregated per step.
    meta = Column(JSON, nullable=True)

    # Human-readable error if something failed during generation.
    last_error = Column(Text, nullable=True)

    project = relationship("Project")
    owner = relationship("User")
