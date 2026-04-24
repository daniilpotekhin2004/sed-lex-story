"""
TTS API Routes for LexQuest Design Studio
"""

from pathlib import Path
import mimetypes
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import logging

from app.core.config import get_settings
from app.schemas.ai import AIVoicePreviewRequest
from app.services.tts import tts_service
from app.services.voice_preview import VoicePreviewService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tts", tags=["tts"])

class TTSRequest(BaseModel):
    text: str
    voice_id: Optional[str] = None
    
class TTSResponse(BaseModel):
    success: bool
    audio_url: Optional[str] = None
    message: Optional[str] = None

@router.get("/status")
async def get_tts_status():
    """Get TTS service status"""
    try:
        status = tts_service.get_service_status()
        settings = get_settings()
        remote_available = bool(
            (settings.tts_base_url or settings.openai_base_url)
            and (settings.tts_api_key or settings.openai_api_key)
            and (settings.tts_model or settings.openai_model)
        )
        provider = (settings.tts_provider or "auto").strip().lower()
        comfy_available = bool(
            (provider in {"comfy", "comfy_workflow", "workflow", "comfy_api"})
            or (provider == "auto" and (settings.tts_comfy_workflow_path or "").strip())
        )
        if not status.get("available") and remote_available:
            voice_name = settings.tts_voice or "default"
            status["available"] = True
            status["models"] = status.get("models") or [
                {"name": voice_name, "info": "remote", "type": "remote"}
            ]
            status["models_count"] = len(status["models"])
            status["models_dir"] = status.get("models_dir") or "remote"
        if not status.get("available") and comfy_available:
            workflow_name = (settings.tts_comfy_workflow_path or "Comfy workflow").strip()
            status["available"] = True
            status["models"] = status.get("models") or [
                {"name": workflow_name, "info": "comfy_workflow", "type": "comfy_workflow"}
            ]
            status["models_count"] = len(status["models"])
            status["models_dir"] = status.get("models_dir") or "comfy_workflow"
        return status
    except Exception as e:
        logger.error(f"Error getting TTS status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get TTS status")


def _guess_extension(content_type: str) -> str:
    if not content_type:
        return ".mp3"
    if "wav" in content_type:
        return ".wav"
    if "ogg" in content_type:
        return ".ogg"
    if "mpeg" in content_type:
        return ".mp3"
    ext = mimetypes.guess_extension(content_type.split(";")[0].strip())
    return ext or ".mp3"


@router.post("/synthesize", response_model=TTSResponse)
async def synthesize_speech(request: TTSRequest):
    """Synthesize speech from text"""
    try:
        if not request.text or not request.text.strip():
            raise HTTPException(status_code=400, detail="Text is required")

        audio_bytes: Optional[bytes] = None
        content_type: str = "audio/mpeg"

        if tts_service.is_available():
            audio_path = tts_service.synthesize_speech(request.text, request.voice_id)
            if audio_path and Path(audio_path).exists():
                audio_bytes = Path(audio_path).read_bytes()
                content_type = mimetypes.guess_type(audio_path)[0] or content_type

        if audio_bytes is None:
            preview_service = VoicePreviewService()
            audio_bytes, content_type = await preview_service.generate_preview(
                AIVoicePreviewRequest(text=request.text, voice_profile=request.voice_id)
            )

        settings = get_settings()
        tts_dir = settings.generated_assets_path / "tts"
        tts_dir.mkdir(parents=True, exist_ok=True)
        extension = _guess_extension(content_type)
        filename = f"tts_{uuid.uuid4().hex[:10]}{extension}"
        output_path = tts_dir / filename
        output_path.write_bytes(audio_bytes)

        rel = output_path.relative_to(settings.assets_root_path).as_posix()
        audio_url = f"/api/assets/{rel}"

        return TTSResponse(
            success=True,
            audio_url=audio_url,
            message="Speech synthesized successfully",
        )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in TTS synthesis: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/models")
async def get_available_models():
    """Get available TTS models"""
    try:
        models = tts_service.get_available_models()
        return {"models": models}
    except Exception as e:
        logger.error(f"Error getting TTS models: {e}")
        raise HTTPException(status_code=500, detail="Failed to get TTS models")
