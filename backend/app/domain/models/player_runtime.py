from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import relationship

from app.domain.models.base import Base, TimestampMixin


class PlayerRun(Base, TimestampMixin):
    __tablename__ = "player_runs"

    id = Column(String(64), primary_key=True)
    project_id = Column(String(32), ForeignKey("projects.id"), nullable=False, index=True)
    graph_id = Column(String(32), ForeignKey("scenario_graphs.id"), nullable=False, index=True)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    package_version = Column(String(64), nullable=True)
    status = Column(String(32), nullable=False, default="active", index=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_synced_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    last_node_id = Column(String(32), nullable=True)
    run_metadata = Column(JSON, nullable=True)

    project = relationship("Project")
    graph = relationship("ScenarioGraph")
    user = relationship("User")
    events = relationship("PlayerRunEvent", back_populates="run", cascade="all, delete-orphan")


class PlayerRunEvent(Base):
    __tablename__ = "player_run_events"

    id = Column(String(64), primary_key=True)
    run_id = Column(String(64), ForeignKey("player_runs.id"), nullable=False, index=True)
    project_id = Column(String(32), ForeignKey("projects.id"), nullable=False, index=True)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    event_type = Column(String(64), nullable=False, index=True)
    event_timestamp = Column(DateTime, nullable=False, index=True)
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    run = relationship("PlayerRun", back_populates="events")
