from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class StyleProfileBase(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    base_prompt: Optional[str] = None
    negative_prompt: Optional[str] = None
    model_checkpoint: Optional[str] = None
    lora_refs: Optional[list] = None
    aspect_ratio: Optional[str] = None
    resolution: Optional[dict] = None
    sampler: Optional[str] = None
    steps: Optional[int] = None
    cfg_scale: Optional[float] = None
    seed_policy: Optional[str] = None
    palette: Optional[list] = None
    forbidden: Optional[list] = None
    style_metadata: Optional[dict] = None


class StyleProfileCreate(StyleProfileBase):
    project_id: str


class StyleProfileBootstrapRequest(BaseModel):
    project_id: str
    overwrite: bool = False


class StyleProfileUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    base_prompt: Optional[str] = None
    negative_prompt: Optional[str] = None
    model_checkpoint: Optional[str] = None
    lora_refs: Optional[list] = None
    aspect_ratio: Optional[str] = None
    resolution: Optional[dict] = None
    sampler: Optional[str] = None
    steps: Optional[int] = None
    cfg_scale: Optional[float] = None
    seed_policy: Optional[str] = None
    palette: Optional[list] = None
    forbidden: Optional[list] = None
    style_metadata: Optional[dict] = None


class StyleProfileRead(BaseModel):
    id: str
    project_id: str
    name: str
    description: Optional[str]
    base_prompt: Optional[str]
    negative_prompt: Optional[str]
    model_checkpoint: Optional[str]
    lora_refs: Optional[list]
    aspect_ratio: Optional[str]
    resolution: Optional[dict]
    sampler: Optional[str]
    steps: Optional[int]
    cfg_scale: Optional[float]
    seed_policy: Optional[str]
    palette: Optional[list]
    forbidden: Optional[list]
    style_metadata: Optional[dict]

    model_config = {'from_attributes': True}
