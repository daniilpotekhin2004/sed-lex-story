from __future__ import annotations

from uuid import uuid4

from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.domain.models.base import Base, TimestampMixin


class Scene(Base, TimestampMixin):
    __tablename__ = "scenes"

    id = Column(String(32), primary_key=True, default=lambda: uuid4().hex)
    quest_id = Column(String(32), ForeignKey("quests.id"), nullable=False, index=True)
    title = Column(String(255), nullable=True)
    text = Column(Text, nullable=False)
    order = Column(Integer, nullable=True)
    image_path = Column(String(512), nullable=True)

    quest = relationship("Quest", back_populates="scenes")
    scene_characters = relationship("SceneCharacter", back_populates="scene", cascade="all, delete-orphan")
