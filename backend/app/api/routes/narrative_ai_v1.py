from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.core.config import get_settings
from app.schemas.narrative_ai import (
    AISceneDraftRequest,
    AISceneDraftResponse,
    AIScenarioDraftRequest,
    AIScenarioDraftResponse,
    CharacterVoiceSampleRequest,
    CharacterVoiceSampleResponse,
    SceneTTSSynthesizeRequest,
    SceneTTSSynthesizeResponse,
)
from app.services.narrative_ai import NarrativeAIService
from app.services.scene_tts import SceneTTSService
from app.services.character_voice import CharacterVoiceService


router = APIRouter(prefix="/v1/narrative", tags=["narrative-ai"])


def _require_creative_enabled() -> None:
    settings = get_settings()
    if not settings.ai_masters_creative_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="AI masters creative mode is disabled. Set AI_MASTERS_CREATIVE_ENABLED=true to enable.",
        )



@router.post(
    "/projects/{project_id}/scenario-draft",
    response_model=AIScenarioDraftResponse,
)
async def draft_scenario(
    project_id: str,
    payload: AIScenarioDraftRequest,
    session: AsyncSession = Depends(get_db_session),
) -> AIScenarioDraftResponse:
    _require_creative_enabled()
    service = NarrativeAIService(session)
    return await service.draft_scenario(project_id, payload)


@router.post(
    "/graphs/{graph_id}/scene-draft",
    response_model=AISceneDraftResponse,
)
async def draft_scene(
    graph_id: str,
    payload: AISceneDraftRequest,
    session: AsyncSession = Depends(get_db_session),
) -> AISceneDraftResponse:
    _require_creative_enabled()
    service = NarrativeAIService(session)
    return await service.draft_scene(graph_id, payload)


@router.post(
    "/scenes/{scene_id}/tts",
    response_model=SceneTTSSynthesizeResponse,
)
async def synthesize_scene_tts(
    scene_id: str,
    payload: SceneTTSSynthesizeRequest,
    session: AsyncSession = Depends(get_db_session),
) -> SceneTTSSynthesizeResponse:
    _require_creative_enabled()
    service = SceneTTSService(session)
    result = await service.synthesize_scene_script(
        scene_id,
        language=payload.language,
        overwrite=payload.overwrite,
        fallback_mode=payload.fallback_mode,
    )
    return SceneTTSSynthesizeResponse(**result)


@router.post(
    "/characters/{preset_id}/voice-sample",
    response_model=CharacterVoiceSampleResponse,
)
async def generate_character_voice_sample(
    preset_id: str,
    payload: CharacterVoiceSampleRequest,
    session: AsyncSession = Depends(get_db_session),
) -> CharacterVoiceSampleResponse:
    _require_creative_enabled()
    service = CharacterVoiceService(session)
    result = await service.generate_voice_sample(
        preset_id,
        language=payload.language,
        sample_text=payload.sample_text,
        overwrite=payload.overwrite,
    )
    return CharacterVoiceSampleResponse(**result)
