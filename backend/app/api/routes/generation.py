from fastapi import APIRouter, Depends, status

from app.api.deps import get_generation_service, get_sd_overrides
from app.schemas.generation import (
    GenerationRequest,
    GenerationResponse,
    PipelineCheckStatus,
    TaskListResponse,
    TaskStatus,
)
from app.services.generation import ImageGenerationService
from app.utils.sd_provider import SDProviderOverrides

router = APIRouter(prefix="/generation", tags=["generation"])


@router.post(
    "/generate",
    response_model=GenerationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Поставить задачу генерации изображений",
)
async def generate(
    payload: GenerationRequest,
    generation_service: ImageGenerationService = Depends(get_generation_service),
    sd_overrides: SDProviderOverrides = Depends(get_sd_overrides),
) -> GenerationResponse:
    task_id = generation_service.generate(payload, sd_overrides=sd_overrides)
    return GenerationResponse(task_id=task_id)


@router.get(
    "/tasks",
    response_model=TaskListResponse,
    summary="Получить список задач генерации",
)
async def get_tasks(
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    generation_service: ImageGenerationService = Depends(get_generation_service),
) -> TaskListResponse:
    """Получить список задач с фильтрацией и пагинацией."""
    return generation_service.get_tasks(page=page, page_size=page_size, status=status)


@router.get(
    "/tasks/{task_id}",
    response_model=TaskStatus,
    summary="Получить статус задачи генерации",
)
async def get_task_status(
    task_id: str, generation_service: ImageGenerationService = Depends(get_generation_service)
) -> TaskStatus:
    return generation_service.get_task_status(task_id)


@router.post(
    "/pipeline-check",
    response_model=PipelineCheckStatus,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Проверка пайплайна генерации через Celery/SD",
)
async def trigger_pipeline_check(
    generation_service: ImageGenerationService = Depends(get_generation_service),
    sd_overrides: SDProviderOverrides = Depends(get_sd_overrides),
) -> PipelineCheckStatus:
    return generation_service.run_pipeline_check(sd_overrides=sd_overrides)


@router.get(
    "/pipeline-check/{task_id}",
    response_model=PipelineCheckStatus,
    summary="Получить статус проверки пайплайна генерации",
)
async def get_pipeline_check_status(
    task_id: str, generation_service: ImageGenerationService = Depends(get_generation_service)
) -> PipelineCheckStatus:
    return generation_service.get_pipeline_check_status(task_id)
