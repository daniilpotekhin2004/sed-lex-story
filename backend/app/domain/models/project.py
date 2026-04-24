from __future__ import annotations

from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from app.domain.models.base import Base, TimestampMixin


class Project(Base, TimestampMixin):
    """Top-level container for a narrative universe."""

    __tablename__ = "projects"

    id = Column(String(32), primary_key=True, default=lambda: uuid4().hex)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    # Long-form story synopsis / plot outline.
    # Used as a global context for AI-assisted narrative generation.
    story_outline = Column(Text, nullable=True)
    owner_id = Column(String(32), ForeignKey("users.id"), nullable=True, index=True)
    # use_alter=True to break circular dependency with style_profiles
    style_profile_id = Column(
        String(32),
        ForeignKey("style_profiles.id", use_alter=True, name="fk_projects_style_profile_id"),
        nullable=True,
    )
    archived_at = Column(DateTime, nullable=True, index=True)

    owner = relationship("User", backref="projects")
    style_profile = relationship(
        "StyleProfile",
        foreign_keys=[style_profile_id],
        uselist=False,
        post_update=True,
        overlaps="style_profiles,project",
    )
    style_profiles = relationship(
        "StyleProfile",
        foreign_keys="StyleProfile.project_id",
        back_populates="project",
        cascade="all, delete-orphan",
        overlaps="style_profile",
    )
    style_bible = relationship(
        "StyleBible",
        back_populates="project",
        uselist=False,
        cascade="all, delete-orphan",
    )
    project_characters = relationship(
        "CharacterPreset",
        back_populates="project",
        cascade="all, delete-orphan",
        foreign_keys="CharacterPreset.project_id",
    )
    locations = relationship("Location", back_populates="project", cascade="all, delete-orphan")
    artifacts = relationship("Artifact", back_populates="project", cascade="all, delete-orphan")
    document_templates = relationship(
        "DocumentTemplate",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    graphs = relationship("ScenarioGraph", back_populates="project", cascade="all, delete-orphan")
    releases = relationship("ProjectRelease", back_populates="project", cascade="all, delete-orphan")
