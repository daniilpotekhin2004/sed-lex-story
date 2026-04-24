from __future__ import annotations

from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.domain.models.base import Base, TimestampMixin


class StyleBible(Base, TimestampMixin):
    """Narrative and UI style guidelines for a project."""

    __tablename__ = "style_bibles"

    id = Column(String(32), primary_key=True, default=lambda: uuid4().hex)
    project_id = Column(String(32), ForeignKey("projects.id"), nullable=False, unique=True, index=True)
    tone = Column(String(255), nullable=True)
    glossary = Column(JSON, nullable=True)
    constraints = Column(JSON, nullable=True)
    dialogue_format = Column(JSON, nullable=True)
    document_format = Column(JSON, nullable=True)
    ui_theme = Column(JSON, nullable=True)
    narrative_rules = Column(Text, nullable=True)

    project = relationship("Project", back_populates="style_bible")


class Location(Base, TimestampMixin):
    """Persistent location entity with visual/style anchors."""

    __tablename__ = "locations"

    id = Column(String(32), primary_key=True, default=lambda: uuid4().hex)
    project_id = Column(String(32), ForeignKey("projects.id"), nullable=True, index=True)
    owner_id = Column(String(32), ForeignKey("users.id"), nullable=True, index=True)
    is_public = Column(Boolean, default=False, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    source_location_id = Column(String(32), ForeignKey("locations.id"), nullable=True, index=True)
    source_version = Column(Integer, nullable=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    visual_reference = Column(Text, nullable=True)
    # Якорный тег/токен для локации (может использоваться как embedding/LoRA token)
    anchor_token = Column(String(64), nullable=True, index=True)

    # Дополнительный negative prompt для устойчивости (опционально)
    negative_prompt = Column(Text, nullable=True)

    # Дополнительные референсы (establishing, interior, details и т.п.)
    reference_images = Column(JSON, nullable=True)  # [{kind, url, thumb_url, meta}, ...]
    preview_image_url = Column(String(512), nullable=True)
    preview_thumbnail_url = Column(String(512), nullable=True)
    atmosphere_rules = Column(JSON, nullable=True)
    tags = Column(JSON, nullable=True)
    location_metadata = Column(JSON, nullable=True)
    archived_at = Column(DateTime, nullable=True, index=True)

    project = relationship("Project", back_populates="locations")
    owner = relationship("User")
    source_location = relationship("Location", remote_side=[id], foreign_keys=[source_location_id])
    scenes = relationship("SceneNode", back_populates="location")


class Artifact(Base, TimestampMixin):
    """Reusable artifacts/evidence/documents."""

    __tablename__ = "artifacts"

    id = Column(String(32), primary_key=True, default=lambda: uuid4().hex)
    project_id = Column(String(32), ForeignKey("projects.id"), nullable=True, index=True)
    owner_id = Column(String(32), ForeignKey("users.id"), nullable=True, index=True)
    is_public = Column(Boolean, default=False, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    source_artifact_id = Column(String(32), ForeignKey("artifacts.id"), nullable=True, index=True)
    source_version = Column(Integer, nullable=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    artifact_type = Column(String(64), nullable=True)
    legal_significance = Column(Text, nullable=True)
    status = Column(String(64), nullable=True)
    preview_image_url = Column(String(512), nullable=True)
    preview_thumbnail_url = Column(String(512), nullable=True)
    artifact_metadata = Column(JSON, nullable=True)
    tags = Column(JSON, nullable=True)
    archived_at = Column(DateTime, nullable=True, index=True)

    project = relationship("Project", back_populates="artifacts")
    owner = relationship("User")
    source_artifact = relationship("Artifact", remote_side=[id], foreign_keys=[source_artifact_id])
    scene_links = relationship("SceneArtifact", back_populates="artifact", cascade="all, delete-orphan")


class DocumentTemplate(Base, TimestampMixin):
    """Templates for legal documents and inserts."""

    __tablename__ = "document_templates"

    id = Column(String(32), primary_key=True, default=lambda: uuid4().hex)
    project_id = Column(String(32), ForeignKey("projects.id"), nullable=True, index=True)
    owner_id = Column(String(32), ForeignKey("users.id"), nullable=True, index=True)
    is_public = Column(Boolean, default=False, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    source_template_id = Column(String(32), ForeignKey("document_templates.id"), nullable=True, index=True)
    source_version = Column(Integer, nullable=True)
    name = Column(String(255), nullable=False)
    template_type = Column(String(64), nullable=True)
    template_body = Column(Text, nullable=True)
    placeholders = Column(JSON, nullable=True)
    formatting = Column(JSON, nullable=True)
    tags = Column(JSON, nullable=True)
    archived_at = Column(DateTime, nullable=True, index=True)

    project = relationship("Project", back_populates="document_templates")
    owner = relationship("User")
    source_template = relationship("DocumentTemplate", remote_side=[id], foreign_keys=[source_template_id])


class SceneArtifact(Base, TimestampMixin):
    """Artifact usage inside a scene with local context."""

    __tablename__ = "scene_artifacts"

    id = Column(String(32), primary_key=True, default=lambda: uuid4().hex)
    scene_id = Column(String(32), ForeignKey("scene_nodes.id"), nullable=False, index=True)
    artifact_id = Column(String(32), ForeignKey("artifacts.id"), nullable=False, index=True)
    state = Column(String(64), nullable=True)
    notes = Column(Text, nullable=True)
    importance = Column(Float, default=1.0, nullable=False)

    scene = relationship("SceneNode", back_populates="scene_artifacts", foreign_keys=[scene_id])
    artifact = relationship("Artifact", back_populates="scene_links")
