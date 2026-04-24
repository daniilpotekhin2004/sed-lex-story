from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class TextualInversionRequest(BaseModel):
    token: str = Field(..., min_length=1)
    character_id: Optional[str] = None
    init_text: Optional[str] = None
    num_vectors: int = Field(1, ge=1, le=64)
    overwrite: bool = False


class TextualInversionResponse(BaseModel):
    token: str
    created: bool
    info: Optional[dict] = None


class LoraTrainingRequest(BaseModel):
    material_set_id: str
    token: str = Field(..., min_length=1)
    label: Optional[str] = None
    caption: Optional[str] = None
    character_id: Optional[str] = None


class LoraTrainingResponse(BaseModel):
    dataset_path: str
    image_count: int
    token: str
    label: str
    material_set_id: str
