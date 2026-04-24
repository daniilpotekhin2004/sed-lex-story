from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.core.config import get_settings
from app.schemas.ai_masters import AIMasterDispatchRequest, AIMasterDispatchResponse
from app.schemas.entity_ai import EntityDraftRequest
from app.schemas.render_spec import RenderSpecCompileRequest
from app.schemas.narrative_ai import (
    AISceneDraftRequest,
    AIScenarioDraftRequest,
    CharacterVoiceSampleRequest,
    SceneTTSSynthesizeRequest,
)
from app.services.narrative_ai import NarrativeAIService
from app.services.character_voice import CharacterVoiceService
from app.services.scene_tts import SceneTTSService
from app.services.entity_ai import EntityAIService
from app.services.render_spec_master import RenderSpecMasterService


router = APIRouter(prefix="/ai/masters", tags=["ai-masters"])


def _require_creative_enabled() -> None:
    settings = get_settings()
    if not settings.ai_masters_creative_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="AI masters creative mode is disabled. Set AI_MASTERS_CREATIVE_ENABLED=true to enable.",
        )


@router.get("/status")
async def masters_status() -> dict:
    """A tiny health/status endpoint for the optional masters layer."""
    settings = get_settings()
    return {
        "enabled": bool(settings.ai_masters_creative_enabled),
        "note": "Set AI_MASTERS_CREATIVE_ENABLED=true to enable creative mode endpoints.",
    }


@router.post("/dispatch", response_model=AIMasterDispatchResponse)
async def dispatch_master(
    req: AIMasterDispatchRequest,
    session: AsyncSession = Depends(get_db_session),
) -> AIMasterDispatchResponse:
    _require_creative_enabled()

    intent = req.intent

    if intent == "scenario_draft":
        if not req.project_id:
            raise HTTPException(status_code=400, detail="project_id is required for scenario_draft")
        payload = AIScenarioDraftRequest.model_validate(req.payload)
        service = NarrativeAIService(session)
        result = await service.draft_scenario(req.project_id, payload)
        return AIMasterDispatchResponse(intent=intent, result=result.model_dump())

    if intent == "scene_draft":
        if not req.graph_id:
            raise HTTPException(status_code=400, detail="graph_id is required for scene_draft")
        payload = AISceneDraftRequest.model_validate(req.payload)
        service = NarrativeAIService(session)
        result = await service.draft_scene(req.graph_id, payload)
        return AIMasterDispatchResponse(intent=intent, result=result.model_dump())

    if intent == "entity_draft":
        payload = EntityDraftRequest.model_validate(req.payload)
        # Allow routing project_id through the top-level field for convenience
        if req.project_id and not payload.project_id:
            payload.project_id = req.project_id
        service = EntityAIService(session)
        result = await service.draft_entity(payload)
        return AIMasterDispatchResponse(intent=intent, result=result.model_dump())

    if intent == "renderspec_compile":
        if not req.scene_id:
            raise HTTPException(status_code=400, detail="scene_id is required for renderspec_compile")
        payload = RenderSpecCompileRequest.model_validate(req.payload)
        service = RenderSpecMasterService(session)
        result = await service.compile_for_scene(req.scene_id, payload)
        return AIMasterDispatchResponse(intent=intent, result=result.model_dump())

    if intent == "character_voice_sample":
        if not req.preset_id:
            raise HTTPException(status_code=400, detail="preset_id is required for character_voice_sample")
        payload = CharacterVoiceSampleRequest.model_validate(req.payload)
        service = CharacterVoiceService(session)
        result = await service.generate_voice_sample(
            req.preset_id,
            language=payload.language,
            sample_text=payload.sample_text,
            overwrite=payload.overwrite,
        )
        return AIMasterDispatchResponse(intent=intent, result=result)

    if intent == "scene_tts":
        if not req.scene_id:
            raise HTTPException(status_code=400, detail="scene_id is required for scene_tts")
        payload = SceneTTSSynthesizeRequest.model_validate(req.payload)
        service = SceneTTSService(session)
        result = await service.synthesize_scene_script(
            req.scene_id,
            language=payload.language,
            overwrite=payload.overwrite,
            fallback_mode=payload.fallback_mode,
        )
        return AIMasterDispatchResponse(intent=intent, result=result)

    raise HTTPException(status_code=400, detail=f"Unsupported intent: {intent}")