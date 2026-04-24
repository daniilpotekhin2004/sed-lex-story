from __future__ import annotations

from typing import Optional, List

from pydantic import BaseModel, Field


class GenerationOverrides(BaseModel):
    """Reusable optional SD/Comfy generation overrides.

    This schema is intended for endpoints that already have a domain prompt
    (characters, locations, artifacts, etc.) but need controllable technical
    parameters (resolution, steps, sampler, LoRAs, model overrides, ...).
    """

    negative_prompt: Optional[str] = None
    width: Optional[int] = Field(None, ge=256, le=2048)
    height: Optional[int] = Field(None, ge=256, le=2048)
    steps: Optional[int] = Field(None, ge=4, le=80)
    cfg_scale: Optional[float] = Field(None, ge=1.0, le=20.0)
    seed: Optional[int] = None

    sampler: Optional[str] = None
    scheduler: Optional[str] = None
    model_id: Optional[str] = None
    vae_id: Optional[str] = None
    loras: Optional[List[dict]] = None
    generate_reference_images: Optional[bool] = Field(
        None, description="Generate multi-view reference images when supported"
    )

    pipeline_profile_id: Optional[str] = None
    pipeline_profile_version: Optional[int] = None
