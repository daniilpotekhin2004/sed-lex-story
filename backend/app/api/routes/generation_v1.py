from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional

from app.api.deps import get_generation_service_v2, get_sd_overrides
from app.core.deps import require_author
from app.domain.models import User
from app.schemas.generation_job import (
    AssetGenerationJobCreate,
    GenerationJobCreate,
    GenerationJobRead,
    SceneImagesResponse,
    ImageVariantRead,
)
from app.services.generation_job import GenerationJobService
from app.infra.translator import get_translator, count_non_english_words, is_cyrillic
from app.utils.sd_provider import SDProviderOverrides

router = APIRouter(prefix="/v1", tags=["generation-v1"])


class PromptAnalysis(BaseModel):
    """Response for prompt analysis."""
    original: str
    translated: str
    non_english_count: int
    needs_translation: bool
    warning: Optional[str] = None
    translation_changed: bool


class TranslateRequest(BaseModel):
    """Request for prompt translation."""
    prompt: str
    negative_prompt: Optional[str] = None


class TranslateResponse(BaseModel):
    """Response for prompt translation."""
    prompt: PromptAnalysis
    negative_prompt: Optional[PromptAnalysis] = None


@router.post("/prompt/analyze", response_model=PromptAnalysis)
async def analyze_prompt(request: TranslateRequest) -> PromptAnalysis:
    """Analyze a prompt for non-English content and get translation preview."""
    translator = get_translator()
    
    original = request.prompt
    translated = translator.translate(original)
    analysis = translator.analyze_prompt(original)
    
    return PromptAnalysis(
        original=original,
        translated=translated,
        non_english_count=analysis["non_english_count"],
        needs_translation=analysis["needs_translation"],
        warning=analysis["warning"],
        translation_changed=original != translated,
    )


@router.post("/prompt/translate", response_model=TranslateResponse)
async def translate_prompt(request: TranslateRequest) -> TranslateResponse:
    """Translate prompt and negative prompt to English."""
    translator = get_translator()
    
    # Translate prompt
    prompt_translated = translator.translate(request.prompt)
    prompt_analysis = translator.analyze_prompt(request.prompt)
    
    prompt_result = PromptAnalysis(
        original=request.prompt,
        translated=prompt_translated,
        non_english_count=prompt_analysis["non_english_count"],
        needs_translation=prompt_analysis["needs_translation"],
        warning=prompt_analysis["warning"],
        translation_changed=request.prompt != prompt_translated,
    )
    
    # Translate negative prompt if provided
    negative_result = None
    if request.negative_prompt:
        neg_translated = translator.translate(request.negative_prompt)
        neg_analysis = translator.analyze_prompt(request.negative_prompt)
        negative_result = PromptAnalysis(
            original=request.negative_prompt,
            translated=neg_translated,
            non_english_count=neg_analysis["non_english_count"],
            needs_translation=neg_analysis["needs_translation"],
            warning=neg_analysis["warning"],
            translation_changed=request.negative_prompt != neg_translated,
        )
    
    return TranslateResponse(
        prompt=prompt_result,
        negative_prompt=negative_result,
    )


@router.post(
    "/scenes/{scene_id}/generate",
    response_model=GenerationJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_for_scene(
    scene_id: str,
    payload: GenerationJobCreate,
    service: GenerationJobService = Depends(get_generation_service_v2),
    current_user: User = Depends(require_author),
    sd_overrides: SDProviderOverrides = Depends(get_sd_overrides),
) -> GenerationJobRead:
    job = await service.create_job(scene_id, payload, user_id=current_user.id, sd_overrides=sd_overrides)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")
    # Re-fetch with eager-loaded relationships to avoid lazy-loading during response serialization.
    hydrated = await service.get_job(job.id, user_id=current_user.id)
    if hydrated is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to load created job")
    return hydrated


@router.post(
    "/generation/jobs",
    response_model=GenerationJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_asset_generation_job(
    payload: AssetGenerationJobCreate,
    service: GenerationJobService = Depends(get_generation_service_v2),
    current_user: User = Depends(require_author),
    sd_overrides: SDProviderOverrides = Depends(get_sd_overrides),
) -> GenerationJobRead:
    """Unified async generation entrypoint for characters/locations/artifacts.

    Returns a GenerationJob that can be polled via GET /v1/generation-jobs/{job_id}.
    """
    try:
        job = await service.create_asset_job(payload, user_id=current_user.id, sd_overrides=sd_overrides)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")
    hydrated = await service.get_job(job.id, user_id=current_user.id)
    if hydrated is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to load created job")
    return hydrated


@router.get(
    "/generation-jobs/{job_id}",
    response_model=GenerationJobRead,
)
async def get_generation_job(
    job_id: str,
    service: GenerationJobService = Depends(get_generation_service_v2),
) -> GenerationJobRead:
    job = await service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


# New preferred alias (kept alongside the legacy /generation-jobs/... route).
@router.get(
    "/generation/jobs/{job_id}",
    response_model=GenerationJobRead,
)
async def get_generation_job_v2(
    job_id: str,
    service: GenerationJobService = Depends(get_generation_service_v2),
) -> GenerationJobRead:
    job = await service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@router.get(
    "/scenes/{scene_id}/images",
    response_model=SceneImagesResponse,
)
async def list_scene_images(
    scene_id: str,
    service: GenerationJobService = Depends(get_generation_service_v2),
) -> SceneImagesResponse:
    variants = await service.list_scene_images(scene_id)
    return SceneImagesResponse(items=variants)


@router.post(
    "/scenes/{scene_id}/images/{variant_id}/approve",
    response_model=ImageVariantRead,
)
async def approve_scene_image(
    scene_id: str,
    variant_id: str,
    service: GenerationJobService = Depends(get_generation_service_v2),
) -> ImageVariantRead:
    variant = await service.approve_variant(scene_id, variant_id)
    if variant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found for scene")
    return variant


@router.delete(
    "/scenes/{scene_id}/images/{variant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_scene_image(
    scene_id: str,
    variant_id: str,
    service: GenerationJobService = Depends(get_generation_service_v2),
) -> None:
    ok = await service.delete_variant(scene_id, variant_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found for scene")
