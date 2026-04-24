"""Схемы для пресетов генерации пользователя."""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class LoRAModel(BaseModel):
    """LoRA модель с весом."""
    name: str
    weight: float = Field(0.8, ge=0.0, le=2.0)


class UserPresetCreate(BaseModel):
    """Создание пресета."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    negative_prompt: Optional[str] = None
    cfg_scale: float = Field(7.0, ge=1.0, le=20.0)
    steps: int = Field(20, ge=10, le=50)
    width: int = Field(512, ge=256, le=2048)
    height: int = Field(512, ge=256, le=2048)
    style: Optional[str] = None
    sampler: Optional[str] = None
    scheduler: Optional[str] = None
    model_id: Optional[str] = None
    vae_id: Optional[str] = None
    seed: Optional[int] = None
    pipeline_profile_id: Optional[str] = None
    pipeline_profile_version: Optional[int] = None
    lora_models: Optional[List[LoRAModel]] = None
    is_favorite: bool = False


class UserPresetUpdate(BaseModel):
    """Обновление пресета."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    negative_prompt: Optional[str] = None
    cfg_scale: Optional[float] = Field(None, ge=1.0, le=20.0)
    steps: Optional[int] = Field(None, ge=10, le=50)
    width: Optional[int] = Field(None, ge=256, le=2048)
    height: Optional[int] = Field(None, ge=256, le=2048)
    style: Optional[str] = None
    sampler: Optional[str] = None
    scheduler: Optional[str] = None
    model_id: Optional[str] = None
    vae_id: Optional[str] = None
    seed: Optional[int] = None
    pipeline_profile_id: Optional[str] = None
    pipeline_profile_version: Optional[int] = None
    lora_models: Optional[List[LoRAModel]] = None
    is_favorite: Optional[bool] = None


class UserPresetRead(BaseModel):
    """Чтение пресета."""
    id: str
    user_id: str
    name: str
    description: Optional[str]
    negative_prompt: Optional[str]
    cfg_scale: float
    steps: int
    width: int
    height: int
    style: Optional[str]
    sampler: Optional[str]
    scheduler: Optional[str]
    model_id: Optional[str]
    vae_id: Optional[str]
    seed: Optional[int]
    pipeline_profile_id: Optional[str]
    pipeline_profile_version: Optional[int]
    lora_models: Optional[List[dict]]
    is_favorite: bool
    usage_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {'from_attributes': True}


class UserPresetList(BaseModel):
    """Список пресетов."""
    items: List[UserPresetRead]
    total: int
