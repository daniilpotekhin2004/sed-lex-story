from __future__ import annotations

from fastapi import APIRouter, Response

from app.schemas.ai import (
    AIDescriptionRequest,
    AIDescriptionResponse,
    AIFormFillRequest,
    AIFormFillResponse,
    AIVoicePreviewRequest,
)
from app.services.ai_description import AIDescriptionService
from app.services.ai_form_fill import AIFormFillService
from app.services.voice_preview import VoicePreviewService

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/description", response_model=AIDescriptionResponse)
async def generate_description(payload: AIDescriptionRequest) -> AIDescriptionResponse:
    service = AIDescriptionService()
    return await service.generate_description(payload)


@router.post("/form-fill", response_model=AIFormFillResponse)
async def generate_form_fill(payload: AIFormFillRequest) -> AIFormFillResponse:
    service = AIFormFillService()
    return await service.generate_form_fill(payload)


@router.post("/voice-preview")
async def generate_voice_preview(payload: AIVoicePreviewRequest) -> Response:
    service = VoicePreviewService()
    audio, content_type = await service.generate_preview(payload)
    return Response(content=audio, media_type=content_type)
