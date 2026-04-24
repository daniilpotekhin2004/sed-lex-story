from __future__ import annotations

from uuid import uuid4

from sqlalchemy import Column, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.domain.models.base import Base, TimestampMixin


class LegalConcept(Base, TimestampMixin):
    """Legal topic/concept attached to scenes."""

    __tablename__ = "legal_concepts"

    id = Column(String(32), primary_key=True, default=lambda: uuid4().hex)
    code = Column(String(64), nullable=False, unique=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    difficulty = Column(Integer, nullable=True)
    tags = Column(JSON, nullable=True)

    scenes = relationship(
        "SceneNode",
        secondary="scene_legal_concepts",
        back_populates="legal_concepts",
        overlaps="legal_links",
    )


class SceneLegalConcept(Base, TimestampMixin):
    """Association between scene nodes and legal concepts."""

    __tablename__ = "scene_legal_concepts"

    id = Column(String(32), primary_key=True, default=lambda: uuid4().hex)
    scene_id = Column(String(32), ForeignKey("scene_nodes.id"), nullable=False, index=True)
    concept_id = Column(String(32), ForeignKey("legal_concepts.id"), nullable=False, index=True)

    scene = relationship("SceneNode", back_populates="legal_links", overlaps="legal_concepts,scenes")
    concept = relationship("LegalConcept", overlaps="legal_concepts,scenes")
