from __future__ import annotations

from pydantic import BaseModel, Field, conint


class GenerationRequest(BaseModel):
    prompt: str
    negative_prompt: str | None = None
    style: str | None = None
    num_variants: conint(ge=1, le=8) = Field(4, description="Number of image variants")
    width: conint(ge=256, le=1024) | None = Field(None, description="Image width")
    height: conint(ge=256, le=1024) | None = Field(None, description="Image height")
    cfg_scale: float | None = Field(None, ge=1.0, le=20.0, description="CFG scale")
    steps: conint(ge=4, le=50) | None = Field(None, description="Number of steps (Qwen: 4-9, SD: 10-50)")
    seed: int | None = None
    sampler: str | None = None
    scheduler: str | None = None
    model_id: str | None = None
    vae_id: str | None = None
    loras: list[dict] | None = None
    pipeline_profile_id: str | None = None
    pipeline_profile_version: int | None = None


class GenerationResponse(BaseModel):
    task_id: str


class PipelineCheckStatus(BaseModel):
    task_id: str
    state: str
    ready: bool
    success: bool | None = None
    details: dict | None = None
    error: str | None = None


class TaskStatus(BaseModel):
    task_id: str
    state: str
    ready: bool
    success: bool | None = None
    result: dict | None = None
    error: str | None = None
    # Параметры генерации
    prompt: str | None = None
    negative_prompt: str | None = None
    cfg_scale: float | None = None
    steps: int | None = None
    # Публичные URL изображений
    image_urls: list[str] | None = None


class TaskListItem(BaseModel):
    """Элемент списка задач."""
    task_id: str
    state: str
    ready: bool
    created_at: str | None = None
    prompt: str | None = None
    image_urls: list[str] | None = None


class TaskListResponse(BaseModel):
    """Список задач с пагинацией."""
    items: list[TaskListItem]
    total: int
    page: int = 1
    page_size: int = 20
