from __future__ import annotations

from enum import Enum
from uuid import uuid4

from sqlalchemy import Column, String, Text, ForeignKey, Integer, Boolean, JSON
from sqlalchemy.orm import relationship

from app.domain.models.base import Base, TimestampMixin


class ImageStatus(str, Enum):
    """Статус сгенерированного изображения."""
    PENDING = "pending"          # Ожидает генерации
    GENERATING = "generating"    # В процессе генерации
    GENERATED = "generated"      # Сгенерировано, ожидает модерации
    APPROVED = "approved"        # Одобрено модератором
    REJECTED = "rejected"        # Отклонено модератором
    FAILED = "failed"           # Ошибка генерации


class GeneratedImage(Base, TimestampMixin):
    """
    Сгенерированное изображение для сцены.
    Поддерживает модерацию и версионирование.
    """
    __tablename__ = "generated_images"

    id = Column(String(32), primary_key=True, default=lambda: uuid4().hex)
    
    # Связи
    scene_id = Column(String(32), ForeignKey("scenes.id"), nullable=False, index=True)
    author_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    
    # Генерация
    task_id = Column(String(255), nullable=True, index=True)  # Celery task ID
    prompt = Column(Text, nullable=False)
    negative_prompt = Column(Text, nullable=True)
    generation_params = Column(JSON, nullable=True)  # SD параметры
    
    # Файлы
    image_path = Column(String(512), nullable=True)
    thumbnail_path = Column(String(512), nullable=True)
    
    # Статус и модерация
    status = Column(String(50), nullable=False, default=ImageStatus.PENDING.value, index=True)
    moderation_notes = Column(Text, nullable=True)
    moderated_by_id = Column(String(32), ForeignKey("users.id"), nullable=True)
    moderated_at = Column(String(50), nullable=True)  # ISO datetime string
    
    # Метаданные
    variant_number = Column(Integer, default=1, nullable=False)  # Номер варианта (1-4)
    is_selected = Column(Boolean, default=False, nullable=False)  # Выбран автором
    
    # Статистика
    generation_time_seconds = Column(Integer, nullable=True)
    file_size_bytes = Column(Integer, nullable=True)
    
    # Связи
    scene = relationship("Scene", backref="generated_images")
    author = relationship("User", foreign_keys=[author_id], backref="generated_images")
    moderator = relationship("User", foreign_keys=[moderated_by_id], backref="moderated_images")
    
    def can_moderate(self, user_id: str) -> bool:
        """Проверить, может ли пользователь модерировать это изображение."""
        # Автор не может модерировать свои изображения
        return self.author_id != user_id
    
    def approve(self, moderator_id: str, notes: str = None) -> None:
        """Одобрить изображение."""
        from datetime import datetime
        self.status = ImageStatus.APPROVED.value
        self.moderated_by_id = moderator_id
        self.moderated_at = datetime.utcnow().isoformat()
        if notes:
            self.moderation_notes = notes
    
    def reject(self, moderator_id: str, notes: str) -> None:
        """Отклонить изображение."""
        from datetime import datetime
        self.status = ImageStatus.REJECTED.value
        self.moderated_by_id = moderator_id
        self.moderated_at = datetime.utcnow().isoformat()
        self.moderation_notes = notes
    
    def select(self) -> None:
        """Выбрать это изображение как основное для сцены."""
        self.is_selected = True
