from __future__ import annotations

from enum import Enum
from typing import Optional
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.domain.models.base import Base, TimestampMixin

from app.utils.sd_tokens import collect_lora_tokens, collect_embedding_tokens


class CharacterType(str, Enum):
    """Тип персонажа."""
    PROTAGONIST = "protagonist"  # Главный герой
    ANTAGONIST = "antagonist"    # Антагонист
    SUPPORTING = "supporting"    # Второстепенный
    BACKGROUND = "background"    # Фоновый персонаж


class CharacterPreset(Base, TimestampMixin):
    """
    Пресет персонажа с настройками для генерации изображений.
    Поддерживает LoRA модели и embeddings для Stable Diffusion.
    """
    __tablename__ = "character_presets"

    id = Column(String(32), primary_key=True, default=lambda: uuid4().hex)
    
    # Базовая информация
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    character_type = Column(String(50), nullable=False, default=CharacterType.SUPPORTING.value)
    version = Column(Integer, default=1, nullable=False)

    # Project-scoped copy metadata (null means studio asset)
    project_id = Column(String(32), ForeignKey("projects.id"), nullable=True, index=True)
    source_preset_id = Column(String(32), ForeignKey("character_presets.id"), nullable=True, index=True)
    source_version = Column(Integer, nullable=True)
    
    # Визуальные характеристики
    appearance_prompt = Column(Text, nullable=False)  # Базовый промпт внешности
    negative_prompt = Column(Text, nullable=True)     # Негативный промпт

    # Якорный тег/токен для консистентной генерации (может использоваться как embedding/LoRA token)
    anchor_token = Column(String(64), nullable=True, index=True)

    # Структурированное описание внешности (для UI-билдера, не обязательно для SD)
    appearance_profile = Column(JSON, nullable=True)  # {age, hair, eyes, outfit, ...}

    # Дополнительные референсы (лист превью, character sheet и т.п.)
    reference_images = Column(JSON, nullable=True)  # [{kind, url, thumb_url, meta}, ...]

    # Наративные характеристики
    voice_profile = Column(Text, nullable=True)  # Речевой портрет
    motivation = Column(Text, nullable=True)     # Мотивация/цели
    legal_status = Column(String(128), nullable=True)  # Процессуальный статус
    competencies = Column(JSON, nullable=True)  # ["legal knowledge", "empathy", ...]
    relationships = Column(JSON, nullable=True)  # [{"character_id": "...", "relation": "ally"}]
    artifact_refs = Column(JSON, nullable=True)  # ["artifact_id", ...]
    
    # LoRA настройки (может быть несколько LoRA)
    lora_models = Column(JSON, nullable=True)  # [{"name": "lora_name", "weight": 0.8}, ...]
    
    # Embeddings (текстовые инверсии)
    embeddings = Column(JSON, nullable=True)  # ["embedding1", "embedding2", ...]
    
    # Дополнительные параметры генерации
    style_tags = Column(JSON, nullable=True)  # ["realistic", "detailed", ...]
    default_pose = Column(String(255), nullable=True)  # "standing", "sitting", etc.

    # Сохранённые визуальные референсы
    preview_image_url = Column(String(512), nullable=True)
    preview_thumbnail_url = Column(String(512), nullable=True)
    
    # Метаданные
    is_public = Column(Boolean, default=False, nullable=False)  # Доступен всем
    author_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    
    # Статистика использования
    usage_count = Column(Integer, default=0, nullable=False)
    archived_at = Column(DateTime, nullable=True, index=True)
    
    # Связи
    author = relationship("User", back_populates="character_presets")
    project = relationship("Project", back_populates="project_characters", foreign_keys=[project_id])
    source_preset = relationship("CharacterPreset", remote_side=[id], foreign_keys=[source_preset_id])
    scene_characters = relationship("SceneCharacter", back_populates="character_preset", cascade="all, delete-orphan")
    scene_nodes_v2 = relationship("SceneNodeCharacter", back_populates="character_preset", cascade="all, delete-orphan")
    
    def to_sd_prompt(self, additional_context: Optional[str] = None) -> dict:
        """
        Генерирует промпт для Stable Diffusion с учетом LoRA и embeddings.
        
        Returns:
            dict: {
                "prompt": str,
                "negative_prompt": str,
                "lora_models": list,
                "embeddings": list
            }
        """
        prompt_parts: list[str] = []

        # Consistency anchor/token (can be trained as TI embedding or used as a macro)
        if self.anchor_token:
            prompt_parts.append(self.anchor_token)

        # SD special tokens
        prompt_parts.extend(collect_embedding_tokens(self.embeddings))
        prompt_parts.extend(collect_lora_tokens(self.lora_models))

        # Root cause: Character description was not included in regeneration prompts
        # Solution: Always include description field which contains the full character details
        if self.description:
            prompt_parts.append(self.description)

        # Base visual description
        prompt_parts.append(self.appearance_prompt)

        if additional_context:
            prompt_parts.append(additional_context)

        if self.style_tags:
            prompt_parts.extend(self.style_tags)

        if self.default_pose:
            prompt_parts.append(self.default_pose)

        return {
            "prompt": ", ".join([p for p in prompt_parts if p]),
            "negative_prompt": self.negative_prompt or "",
            "lora_models": self.lora_models or [],
            "embeddings": self.embeddings or [],
        }


class SceneCharacter(Base, TimestampMixin):
    """
    Связь между сценой и персонажем.
    Позволяет использовать несколько персонажей в одной сцене.
    """
    __tablename__ = "scene_characters"

    id = Column(String(32), primary_key=True, default=lambda: uuid4().hex)
    
    scene_id = Column(String(32), ForeignKey("scenes.id"), nullable=False, index=True)
    character_preset_id = Column(String(32), ForeignKey("character_presets.id"), nullable=False, index=True)
    
    # Контекст для этой конкретной сцены
    scene_context = Column(Text, nullable=True)  # "angry", "smiling", "in uniform", etc.
    position = Column(String(50), nullable=True)  # "left", "center", "right", "background"
    importance = Column(Float, default=1.0, nullable=False)  # Вес персонажа в сцене (0.0-1.0)
    
    # Связи
    scene = relationship("Scene", back_populates="scene_characters")
    character_preset = relationship("CharacterPreset", back_populates="scene_characters")
    
    def get_full_prompt(self) -> dict:
        """Получить полный промпт с учетом контекста сцены."""
        base_prompt = self.character_preset.to_sd_prompt(self.scene_context)
        
        # Добавить позицию если указана
        if self.position:
            base_prompt["prompt"] = f"{base_prompt['prompt']}, {self.position} of frame"
        
        return base_prompt
