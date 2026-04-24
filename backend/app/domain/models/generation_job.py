from __future__ import annotations

from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.domain.models.base import Base, TimestampMixin


class GenerationStatus:
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELED = "canceled"


class GenerationTaskType:
    """Logical task kinds for GenerationJob.

    We use plain strings (instead of a database enum) to keep migrations simple
    and allow adding new task types without DB changes.
    """

    SCENE_GENERATE = "scene_generate"
    CHARACTER_SHEET = "character_sheet"
    CHARACTER_REFERENCE = "character_reference"
    CHARACTER_RENDER = "character_render"
    LOCATION_SHEET = "location_sheet"
    LOCATION_SKETCH = "location_sketch"
    CHARACTER_SKETCH = "character_sketch"
    ARTIFACT_SKETCH = "artifact_sketch"
    CHARACTER_MULTIVIEW = "character_multiview"

    @classmethod
    def all(cls) -> list[str]:
        """Return all supported task type strings."""
        return [
            cls.SCENE_GENERATE,
            cls.CHARACTER_SHEET,
            cls.CHARACTER_REFERENCE,
            cls.CHARACTER_RENDER,
            cls.LOCATION_SHEET,
            cls.LOCATION_SKETCH,
            cls.CHARACTER_SKETCH,
            cls.ARTIFACT_SKETCH,
            cls.CHARACTER_MULTIVIEW,
        ]


class GenerationJob(Base, TimestampMixin):
    """Async generation job for any visual asset.

    Historically this table was scene-only. It is now generalized:
    - Scene jobs: `scene_id` is set, `task_type == scene_generate`, and `variants` are created.
    - Asset jobs (characters/locations): `scene_id` is NULL; results are written into the
      corresponding entity and can additionally be mirrored into `results` for UI.

    NOTE: We keep the original columns (prompt/config/etc.) because they are useful
    for debugging and telemetry.
    """

    __tablename__ = "generation_jobs"

    id = Column(String(32), primary_key=True, default=lambda: uuid4().hex)
    task_id = Column(String(255), nullable=True, index=True)

    # Optional initiator (used for filtering/permissions)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=True, index=True)

    # Optional project context (studio assets may have project_id NULL)
    project_id = Column(String(32), ForeignKey("projects.id"), nullable=True, index=True)

    # Scene context (NULL for non-scene tasks)
    scene_id = Column(String(32), ForeignKey("scene_nodes.id"), nullable=True, index=True)

    # Optional style profile (applies to scenes and some asset tasks)
    style_profile_id = Column(String(32), ForeignKey("style_profiles.id"), nullable=True)

    # Generic task routing
    task_type = Column(String(64), nullable=False, default=GenerationTaskType.SCENE_GENERATE, index=True)
    entity_type = Column(String(64), nullable=False, default="scene", index=True)
    # Stored as a string to support different entity ID formats.
    entity_id = Column(String(32), nullable=False, index=True)

    status = Column(String(32), nullable=False, default=GenerationStatus.QUEUED, index=True)
    progress = Column(Integer, nullable=False, default=0)
    stage = Column(String(64), nullable=True)

    prompt = Column(Text, nullable=True)
    negative_prompt = Column(Text, nullable=True)
    config = Column(JSON, nullable=True)
    results = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)

    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    scene = relationship("SceneNode")
    variants = relationship("ImageVariant", back_populates="job", cascade="all, delete-orphan")


class ImageVariant(Base, TimestampMixin):
    """Single generated variant for a scene job."""

    __tablename__ = "image_variants"

    id = Column(String(32), primary_key=True, default=lambda: uuid4().hex)
    job_id = Column(String(32), ForeignKey("generation_jobs.id"), nullable=False, index=True)
    project_id = Column(String(32), ForeignKey("projects.id"), nullable=False, index=True)
    scene_id = Column(String(32), ForeignKey("scene_nodes.id"), nullable=False, index=True)
    url = Column(String(512), nullable=False)
    thumbnail_url = Column(String(512), nullable=True)
    image_metadata = Column(JSON, nullable=True)  # Renamed from 'metadata' to avoid SQLAlchemy conflict
    is_approved = Column(Boolean, default=False, nullable=False)

    job = relationship("GenerationJob", back_populates="variants")
