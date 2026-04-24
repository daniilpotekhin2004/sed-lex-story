"""Модель пресетов генерации пользователя."""
from __future__ import annotations

from sqlalchemy import Column, String, Text, Integer, Float, ForeignKey, JSON, Boolean
from sqlalchemy.orm import relationship

from app.domain.models.base import Base, TimestampMixin


class UserGenerationPreset(Base, TimestampMixin):
    """
    Сохранённые настройки генерации пользователя.
    Позволяет сохранять избранные комбинации параметров.
    """
    __tablename__ = "user_generation_presets"

    id = Column(String(32), primary_key=True)
    user_id = Column(String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    # Параметры генерации
    negative_prompt = Column(Text, nullable=True)
    cfg_scale = Column(Float, default=7.0, nullable=False)
    steps = Column(Integer, default=20, nullable=False)
    width = Column(Integer, default=512, nullable=False)
    height = Column(Integer, default=512, nullable=False)
    
    # Дополнительные настройки
    style = Column(String(100), nullable=True)
    sampler = Column(String(100), nullable=True)
    scheduler = Column(String(100), nullable=True)
    model_id = Column(String(255), nullable=True)
    vae_id = Column(String(255), nullable=True)
    seed = Column(Integer, nullable=True)
    pipeline_profile_id = Column(String(64), nullable=True)
    pipeline_profile_version = Column(Integer, nullable=True)
    lora_models = Column(JSON, nullable=True)  # [{name, weight}]
    
    is_favorite = Column(Boolean, default=False, nullable=False)
    usage_count = Column(Integer, default=0, nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="generation_presets")
