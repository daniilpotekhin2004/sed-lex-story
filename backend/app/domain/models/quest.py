from __future__ import annotations

from uuid import uuid4

from sqlalchemy import String, Text, Column
from sqlalchemy.orm import relationship

from app.domain.models.base import Base, TimestampMixin


class Quest(Base, TimestampMixin):
    __tablename__ = "quests"

    id = Column(String(32), primary_key=True, default=lambda: uuid4().hex)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    audience = Column(String(128), nullable=True)

    scenes = relationship(
        "Scene",
        back_populates="quest",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
