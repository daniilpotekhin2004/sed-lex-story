from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class LoRAModel(BaseModel):
    """LoRA модель с весом."""
    name: str = Field(..., description="Имя LoRA модели")
    weight: float = Field(0.8, ge=0.0, le=2.0, description="Вес LoRA (0.0-2.0)")


class CharacterPresetCreate(BaseModel):
    """Создание пресета персонажа."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    character_type: str = Field("supporting", description="protagonist, antagonist, supporting, background")
    appearance_prompt: str = Field(..., min_length=10, description="Базовый промпт внешности")
    negative_prompt: Optional[str] = None
    anchor_token: Optional[str] = Field(None, max_length=64, description="Уникальный токен/тег для консистентной генерации")
    appearance_profile: Optional[dict] = Field(None, description="Структурированное описание внешности (для UI-билдера)")
    reference_images: Optional[list] = Field(None, description="Список дополнительных визуальных референсов (sheet/poses/etc)")
    lora_models: Optional[List[LoRAModel]] = None
    embeddings: Optional[List[str]] = None
    style_tags: Optional[List[str]] = None
    default_pose: Optional[str] = None
    voice_profile: Optional[str] = None
    motivation: Optional[str] = None
    legal_status: Optional[str] = None
    competencies: Optional[List[str]] = None
    relationships: Optional[List[dict]] = None
    artifact_refs: Optional[List[str]] = None
    is_public: bool = False


class CharacterPresetUpdate(BaseModel):
    """Обновление пресета персонажа."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    character_type: Optional[str] = None
    appearance_prompt: Optional[str] = Field(None, min_length=10)
    negative_prompt: Optional[str] = None
    anchor_token: Optional[str] = Field(None, max_length=64)
    appearance_profile: Optional[dict] = None
    reference_images: Optional[list] = None
    lora_models: Optional[List[LoRAModel]] = None
    embeddings: Optional[List[str]] = None
    style_tags: Optional[List[str]] = None
    default_pose: Optional[str] = None
    voice_profile: Optional[str] = None
    motivation: Optional[str] = None
    legal_status: Optional[str] = None
    competencies: Optional[List[str]] = None
    relationships: Optional[List[dict]] = None
    artifact_refs: Optional[List[str]] = None
    is_public: Optional[bool] = None
    preview_image_url: Optional[str] = None
    preview_thumbnail_url: Optional[str] = None


class CharacterPresetRead(BaseModel):
    """Чтение пресета персонажа."""
    model_config = {'from_attributes': True}
    
    id: str
    name: str
    description: Optional[str]
    character_type: str
    appearance_prompt: str
    negative_prompt: Optional[str]
    anchor_token: Optional[str]
    appearance_profile: Optional[dict]
    reference_images: Optional[list]
    lora_models: Optional[List[dict]]
    embeddings: Optional[List[str]]
    style_tags: Optional[List[str]]
    default_pose: Optional[str]
    voice_profile: Optional[str]
    motivation: Optional[str]
    legal_status: Optional[str]
    competencies: Optional[List[str]]
    relationships: Optional[List[dict]]
    artifact_refs: Optional[List[str]]
    is_public: bool
    project_id: Optional[str] = None
    source_preset_id: Optional[str] = None
    source_version: Optional[int] = None
    version: int
    preview_image_url: Optional[str]
    preview_thumbnail_url: Optional[str]
    author_id: str
    usage_count: int
    created_at: datetime
    updated_at: datetime


class CharacterPresetList(BaseModel):
    """Список пресетов."""
    items: List[CharacterPresetRead]
    total: int
    page: int
    page_size: int


class SceneCharacterCreate(BaseModel):
    """Добавление персонажа к сцене."""
    character_preset_id: str
    scene_context: Optional[str] = Field(None, description="Контекст для сцены: 'angry', 'smiling', etc.")
    position: Optional[str] = Field(None, description="left, center, right, background")
    importance: float = Field(1.0, ge=0.0, le=1.0, description="Вес персонажа в сцене")


class SceneCharacterUpdate(BaseModel):
    """Обновление персонажа в сцене."""
    scene_context: Optional[str] = None
    position: Optional[str] = None
    importance: Optional[float] = Field(None, ge=0.0, le=1.0)


class SceneCharacterRead(BaseModel):
    """Чтение персонажа в сцене."""
    model_config = {'from_attributes': True}
    
    id: str
    scene_id: str
    character_preset_id: str
    scene_context: Optional[str]
    position: Optional[str]
    importance: float
    character_preset: CharacterPresetRead
    created_at: datetime


class GenerateWithCharactersRequest(BaseModel):
    """Запрос генерации с персонажами."""
    prompt: str = Field(..., description="Базовый промпт сцены")
    character_ids: List[str] = Field(..., description="ID персонажей для включения")
    style: str = Field("realistic", description="Стиль генерации")
    num_variants: int = Field(1, ge=1, le=4)
    
    # Дополнительные параметры SD
    width: int = Field(512, ge=256, le=1024)
    height: int = Field(512, ge=256, le=1024)
    steps: int = Field(20, ge=10, le=50)
    cfg_scale: float = Field(7.0, ge=1.0, le=20.0)
    seed: Optional[int] = None


class CharacterRenderRequest(BaseModel):
    """Generate a canonical/variant character representation."""
    kind: str = Field("variant", description="canonical, variant, expression, turnaround, face, body")
    label: Optional[str] = Field(None, max_length=120)
    count: int = Field(4, ge=1, le=6)
    prompt_override: Optional[str] = Field(None, description="Optional prompt override")
    negative_prompt: Optional[str] = None
    width: Optional[int] = Field(None, ge=256, le=2048)
    height: Optional[int] = Field(None, ge=256, le=2048)
    steps: Optional[int] = Field(None, ge=4, le=80)
    cfg_scale: Optional[float] = Field(None, ge=1.0, le=20.0)
    seed: Optional[int] = None
    sampler: Optional[str] = Field(None, description="Sampler override")
    scheduler: Optional[str] = Field(None, description="Scheduler override")
    model_id: Optional[str] = Field(None, description="Checkpoint / model override")
    vae_id: Optional[str] = Field(None, description="VAE override")
    loras: Optional[List[dict]] = Field(None, description="Extra LoRAs [{name, weight}]")
    pipeline_profile_id: Optional[str] = Field(None, description="Pipeline profile id override")
    pipeline_profile_version: Optional[int] = Field(None, description="Pipeline profile version override")


class SDPromptResponse(BaseModel):
    """Сгенерированный промпт для SD."""
    prompt: str
    negative_prompt: str
    lora_models: List[dict]
    embeddings: List[str]
    characters: List[str]
