from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class SceneNodeCharacterCreate(BaseModel):
    character_preset_id: str
    scene_context: Optional[str] = None
    position: Optional[str] = Field(None, max_length=50)
    importance: float = Field(1.0, ge=0.0, le=1.0)
    seed_override: Optional[str] = None
    in_frame: bool = Field(True, description="Whether this character should be included in image generation")
    material_set_id: Optional[str] = None


class SceneNodeCharacterUpdate(BaseModel):
    scene_context: Optional[str] = None
    position: Optional[str] = Field(None, max_length=50)
    importance: Optional[float] = Field(None, ge=0.0, le=1.0)
    seed_override: Optional[str] = None
    in_frame: Optional[bool] = None
    material_set_id: Optional[str] = None


class SceneNodeCharacterRead(BaseModel):
    id: str
    scene_id: str
    character_preset_id: str
    scene_context: Optional[str]
    position: Optional[str]
    importance: float
    seed_override: Optional[str]
    in_frame: bool
    material_set_id: Optional[str]

    model_config = {'from_attributes': True}
