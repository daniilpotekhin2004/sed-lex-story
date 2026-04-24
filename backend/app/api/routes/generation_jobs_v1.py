from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_generation_service_v2, get_sd_overrides
from app.core.deps import require_author
from app.domain.models.generation_job import GenerationTaskType
from app.schemas.generation_job import AssetGenerationJobCreate, GenerationJobCreate, GenerationJobRead
from app.services.generation_job import GenerationJobService
from app.utils.sd_provider import SDProviderOverrides

router = APIRouter(prefix="/v1/generation", tags=["generation-jobs-v1"])


@router.post(
    "/jobs",
    response_model=GenerationJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_generation_job(
    payload: AssetGenerationJobCreate,
    user=Depends(require_author),
    service: GenerationJobService = Depends(get_generation_service_v2),
    sd_overrides: SDProviderOverrides = Depends(get_sd_overrides),
) -> GenerationJobRead:
    """Unified job enqueue endpoint for *all* generation task types.

    - Scene jobs: use `task_type = scene_generate`, `entity_type = scene`, `entity_id = <scene_id>`,
      and pass GenerationJobCreate-compatible data into `payload.payload`.
    - Asset jobs (character/location/artifact/...): set `task_type/entity_type/entity_id`
      plus optional `overrides/payload`.
    """

    if payload.task_type not in GenerationTaskType.all():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown task_type")

    # Scene jobs reuse existing scene pipeline
    if payload.task_type == GenerationTaskType.SCENE_GENERATE:
        data = dict(payload.payload or {})
        if payload.style_profile_id and "style_profile_id" not in data:
            data["style_profile_id"] = payload.style_profile_id
        # Reasonable default to keep UX simple
        data.setdefault("use_prompt_engine", True)

        try:
            scene_payload = GenerationJobCreate(**data)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid scene payload: {exc}",
            ) from exc

        job = await service.create_job(
            payload.entity_id,
            scene_payload,
            user_id=user.id,
            sd_overrides=sd_overrides,
        )
        if job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")
        return job

    # Asset jobs (character/location/artifact/...) use the asset job pipeline
    job = await service.create_asset_job(payload, user_id=user.id, sd_overrides=sd_overrides)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target entity not found")
    return job


@router.get(
    "/jobs/{job_id}",
    response_model=GenerationJobRead,
)
async def get_generation_job(
    job_id: str,
    user=Depends(require_author),
    service: GenerationJobService = Depends(get_generation_service_v2),
) -> GenerationJobRead:
    job = await service.get_job(job_id, user_id=user.id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@router.get(
    "/jobs",
    response_model=list[GenerationJobRead],
)
async def list_generation_jobs_for_entity(
    entity_type: str = Query(..., description="character | location | artifact | scene | ..."),
    entity_id: str = Query(..., description="Entity id"),
    limit: int = Query(20, ge=1, le=200),
    user=Depends(require_author),
    service: GenerationJobService = Depends(get_generation_service_v2),
) -> list[GenerationJobRead]:
    return await service.list_jobs_for_entity(
        user_id=user.id,
        entity_type=entity_type,
        entity_id=entity_id,
        limit=limit,
    )
