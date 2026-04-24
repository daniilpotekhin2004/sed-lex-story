from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.domain.models.base import Base, TimestampMixin


class ProjectRelease(Base, TimestampMixin):
    __tablename__ = "project_releases"
    __table_args__ = (
        UniqueConstraint("project_id", "version", name="uq_project_releases_project_version"),
    )

    id = Column(String(32), primary_key=True, default=lambda: uuid4().hex)
    project_id = Column(String(32), ForeignKey("projects.id"), nullable=False, index=True)
    graph_id = Column(String(32), ForeignKey("scenario_graphs.id"), nullable=False, index=True)
    created_by_user_id = Column(String(32), ForeignKey("users.id"), nullable=True, index=True)
    version = Column(Integer, nullable=False)
    status = Column(String(32), nullable=False, default="published", index=True)
    package_version = Column(String(64), nullable=False, index=True)
    notes = Column(Text, nullable=True)
    published_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    archived_at = Column(DateTime, nullable=True, index=True)
    manifest_payload = Column(JSON, nullable=False)
    export_payload = Column(JSON, nullable=False)

    project = relationship("Project", back_populates="releases")
    graph = relationship("ScenarioGraph")
    created_by = relationship("User")
    access_entries = relationship(
        "ProjectReleaseAccess",
        back_populates="release",
        cascade="all, delete-orphan",
    )
    cohort_entries = relationship(
        "ProjectReleaseCohortAccess",
        back_populates="release",
        cascade="all, delete-orphan",
    )


class ProjectReleaseAccess(Base, TimestampMixin):
    __tablename__ = "project_release_access"
    __table_args__ = (
        UniqueConstraint("release_id", "user_id", name="uq_project_release_access_release_user"),
    )

    id = Column(String(32), primary_key=True, default=lambda: uuid4().hex)
    release_id = Column(String(32), ForeignKey("project_releases.id"), nullable=False, index=True)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    granted_by_user_id = Column(String(32), ForeignKey("users.id"), nullable=True, index=True)

    release = relationship("ProjectRelease", back_populates="access_entries")
    user = relationship("User", foreign_keys=[user_id])
    granted_by = relationship("User", foreign_keys=[granted_by_user_id])


class ProjectReleaseCohortAccess(Base, TimestampMixin):
    __tablename__ = "project_release_cohort_access"
    __table_args__ = (
        UniqueConstraint("release_id", "cohort_code", name="uq_project_release_cohort_access_release_cohort"),
    )

    id = Column(String(32), primary_key=True, default=lambda: uuid4().hex)
    release_id = Column(String(32), ForeignKey("project_releases.id"), nullable=False, index=True)
    cohort_code = Column(String(64), nullable=False, index=True)
    granted_by_user_id = Column(String(32), ForeignKey("users.id"), nullable=True, index=True)

    release = relationship("ProjectRelease", back_populates="cohort_entries")
    granted_by = relationship("User", foreign_keys=[granted_by_user_id])
