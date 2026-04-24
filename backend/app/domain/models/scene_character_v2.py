from __future__ import annotations

from uuid import uuid4

from sqlalchemy import Boolean, Column, Float, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from app.domain.models.base import Base, TimestampMixin


class SceneNodeCharacter(Base, TimestampMixin):
    """Binding a character preset to a scene node with local context."""

    __tablename__ = "scene_node_characters"

    id = Column(String(32), primary_key=True, default=lambda: uuid4().hex)
    scene_id = Column(String(32), ForeignKey("scene_nodes.id"), nullable=False, index=True)
    character_preset_id = Column(String(32), ForeignKey("character_presets.id"), nullable=False, index=True)
    scene_context = Column(Text, nullable=True)
    position = Column(String(50), nullable=True)
    importance = Column(Float, default=1.0, nullable=False)
    # Whether this character should be visually present in the generated frame.
    # (Characters can still be attached for dialogue/logic, but excluded from image prompting.)
    in_frame = Column(Boolean, default=True, nullable=False)
    seed_override = Column(String(32), nullable=True)
    material_set_id = Column(String(32), ForeignKey("material_sets.id"), nullable=True, index=True)

    scene = relationship("SceneNode", back_populates="scene_characters_v2", foreign_keys=[scene_id])
    character_preset = relationship("CharacterPreset", back_populates="scene_nodes_v2")
    material_set = relationship("MaterialSet")
