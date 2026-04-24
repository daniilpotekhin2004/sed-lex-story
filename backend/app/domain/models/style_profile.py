from __future__ import annotations

from uuid import uuid4

from sqlalchemy import Column, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.domain.models.base import Base, TimestampMixin


class StyleProfile(Base, TimestampMixin):
    """Visual style defaults for a project."""

    __tablename__ = "style_profiles"

    id = Column(String(32), primary_key=True, default=lambda: uuid4().hex)
    project_id = Column(String(32), ForeignKey("projects.id"), nullable=False, index=True)

    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    base_prompt = Column(Text, nullable=True)
    negative_prompt = Column(Text, nullable=True)
    model_checkpoint = Column(String(255), nullable=True)
    lora_refs = Column(JSON, nullable=True)
    aspect_ratio = Column(String(32), nullable=True)
    resolution = Column(JSON, nullable=True)  # {"width": int, "height": int}
    sampler = Column(String(64), nullable=True)
    steps = Column(Integer, nullable=True)
    cfg_scale = Column(Float, nullable=True)
    seed_policy = Column(String(32), nullable=True)
    palette = Column(JSON, nullable=True)
    forbidden = Column(JSON, nullable=True)
    style_metadata = Column(JSON, nullable=True)  # Renamed from 'metadata' to avoid SQLAlchemy conflict

    project = relationship(
        "Project",
        back_populates="style_profiles",
        foreign_keys=[project_id],
        overlaps="style_profile",
    )
