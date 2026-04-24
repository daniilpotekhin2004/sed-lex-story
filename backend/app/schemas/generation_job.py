from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field, conint, field_serializer

from app.schemas.generation_overrides import GenerationOverrides


class GenerationJobCreate(BaseModel):
    """Scene generation payload (PromptEngine-based)."""

    prompt: Optional[str] = None
    negative_prompt: Optional[str] = None
    style_profile_id: Optional[str] = None
    num_variants: conint(ge=1, le=8) = Field(4, description="Number of variants")
    # IMPORTANT: keep these as None by default so prompt-engine / style-profile defaults can apply.
    width: Optional[int] = Field(None, ge=256, le=2048)
    height: Optional[int] = Field(None, ge=256, le=2048)
    cfg_scale: Optional[float] = Field(None, ge=1.0, le=20.0)
    steps: Optional[int] = Field(None, ge=5, le=100)
    seed: Optional[int] = None
    seed_policy: Optional[str] = Field(None, description="fixed | random | derived")
    pipeline_profile_id: Optional[str] = None
    pipeline_profile_version: Optional[int] = None
    use_prompt_engine: bool = Field(True, description="If true, build prompt from scene/style/characters")
    pipeline: Optional[dict] = None
    slide_id: Optional[str] = None
    auto_approve: bool = Field(
        False,
        description="If true, auto-approve the first generated variant for this job.",
    )


class ImageVariantRead(BaseModel):
    id: str
    job_id: str
    project_id: str
    scene_id: str
    url: str
    thumbnail_url: Optional[str]
    image_metadata: Optional[dict]
    is_approved: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GenerationJobRead(BaseModel):
    """Unified job read model.

    For historical reasons this schema is also used for scene generation.
    For non-scene jobs `scene_id` will be null and `variants` will be an empty list.
    """

    id: str
    task_id: Optional[str]

    # Context
    user_id: Optional[str] = None
    project_id: Optional[str] = None
    scene_id: Optional[str] = None
    style_profile_id: Optional[str] = None

    # Routing / state
    task_type: str
    entity_type: str
    entity_id: str
    status: str
    progress: int = 0
    stage: Optional[str] = None

    # Debug/params
    prompt: Optional[str] = None
    negative_prompt: Optional[str] = None
    config: Optional[dict] = None
    results: Optional[Any] = None
    error: Optional[str] = None

    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]

    variants: List[ImageVariantRead] = Field(default_factory=list)

    model_config = {"from_attributes": True}

    @field_serializer("config")
    def _serialize_config(self, config: Optional[dict], _info):  # type: ignore[override]
        if not isinstance(config, dict):
            return config
        redacted_keys = {"sd_comfy_api_key", "comfy_api_key", "sd_api_key"}
        return {key: value for key, value in config.items() if key not in redacted_keys}


class SceneImagesResponse(BaseModel):
    items: List[ImageVariantRead] = Field(default_factory=list)


class AssetGenerationJobCreate(BaseModel):
    """Unified asset job create payload.

    Used by POST /api/v1/generation/jobs.
    """

    task_type: str = Field(..., description="See GenerationTaskType constants")
    entity_type: str = Field(..., description="character | location | artifact | scene")
    entity_id: str

    # Optional context
    project_id: Optional[str] = None
    style_profile_id: Optional[str] = None

    # Optional advanced controls
    overrides: Optional[GenerationOverrides] = None

    # Common generation controls
    num_variants: int = Field(
        1,
        ge=1,
        le=16,
        description="Number of variants/images to generate (if supported by the task)",
    )

    # Task-specific fields
    kind: Optional[str] = Field(
        None,
        description="For task_type=character_reference: which reference kind to regenerate",
    )
    payload: Optional[dict] = Field(
        None,
        description="Optional task-specific payload (e.g., render request)",
    )
