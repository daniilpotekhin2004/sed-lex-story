from __future__ import annotations

from uuid import uuid4

from sqlalchemy import Column, JSON, String

from app.domain.models.base import Base, TimestampMixin


class TelemetryEvent(Base, TimestampMixin):
    """Persisted telemetry events from UI/backend actions."""

    __tablename__ = "telemetry_events"

    id = Column(String(32), primary_key=True, default=lambda: uuid4().hex)
    user_id = Column(String(32), nullable=True, index=True)
    event_name = Column(String(255), nullable=False, index=True)
    payload = Column(JSON, nullable=True)
