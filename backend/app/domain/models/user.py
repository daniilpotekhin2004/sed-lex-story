from __future__ import annotations

from enum import Enum
from uuid import uuid4

from sqlalchemy import String, Column, Enum as SQLEnum, Boolean
from sqlalchemy.orm import relationship

from app.domain.models.base import Base, TimestampMixin


class UserRole(str, Enum):
    ADMIN = "admin"
    AUTHOR = "author"
    PLAYER = "player"


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id = Column(String(32), primary_key=True, default=lambda: uuid4().hex)
    username = Column(String(64), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(SQLEnum(UserRole), default=UserRole.PLAYER, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    full_name = Column(String(255), nullable=True)
    cohort_code = Column(String(64), nullable=True, index=True)
    
    # Relationships
    character_presets = relationship("CharacterPreset", back_populates="author")
    generation_presets = relationship("UserGenerationPreset", back_populates="user", cascade="all, delete-orphan")
