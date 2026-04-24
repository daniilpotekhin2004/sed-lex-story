"""
Voice Generator API Routes - Standalone TTS Tool
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import logging
from pathlib import Path
from app.core.asset_paths import asset_paths

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/voice", tags=["voice-generator"])


def get_voice_generator_service():
    try:
        from app.services.voice_generator import voice_generator
        return voice_generator
    except BaseException as exc:
        logger.error(f"Voice generator service unavailable: {exc}")
        raise HTTPException(status_code=503, detail="Voice generator is unavailable on this machine")

class VoiceGenerationRequest(BaseModel):
    text: str
    voice_prompt: Optional[str] = None
    model_id: Optional[str] = None
    preset: Optional[str] = None
    custom_settings: Optional[Dict[str, Any]] = None

class VoiceDesignRequest(BaseModel):
    text: str
    instruct: str
    language: str = "English"
    model_id: str = "voice_design_1.7b"

class BatchVoiceDesignRequest(BaseModel):
    texts: List[str]
    instructs: List[str]
    languages: List[str]
    model_id: str = "voice_design_1.7b"
    
class VoiceGenerationResponse(BaseModel):
    success: bool
    audio_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    message: Optional[str] = None

class BatchVoiceGenerationResponse(BaseModel):
    success: bool
    results: Optional[List[Dict[str, Any]]] = None
    batch_metadata: Optional[Dict[str, Any]] = None
    message: Optional[str] = None

@router.get("/status")
async def get_voice_generator_status():
    """Get voice generator status and capabilities"""
    try:
        voice_generator = get_voice_generator_service()
        status = voice_generator.get_service_status()
        return status
    except Exception as e:
        logger.error(f"Error getting voice generator status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get status")

@router.get("/models")
async def get_available_models():
    """Get available TTS models"""
    try:
        voice_generator = get_voice_generator_service()
        models = voice_generator.get_available_models()
        return {"models": models}
    except Exception as e:
        logger.error(f"Error getting models: {e}")
        raise HTTPException(status_code=500, detail="Failed to get models")

@router.get("/presets")
async def get_voice_presets():
    """Get available voice presets"""
    try:
        voice_generator = get_voice_generator_service()
        presets = voice_generator.get_voice_presets()
        return {"presets": presets}
    except Exception as e:
        logger.error(f"Error getting presets: {e}")
        raise HTTPException(status_code=500, detail="Failed to get presets")

@router.post("/generate", response_model=VoiceGenerationResponse)
async def generate_voice(request: VoiceGenerationRequest):
    """Generate voice from text"""
    try:
        voice_generator = get_voice_generator_service()
        if not request.text or not request.text.strip():
            raise HTTPException(status_code=400, detail="Text is required")
        
        # Generate voice
        result = voice_generator.generate_voice(
            text=request.text,
            voice_prompt=request.voice_prompt,
            model_id=request.model_id,
            preset=request.preset,
            custom_settings=request.custom_settings
        )
        
        if result and result.get('success'):
            return VoiceGenerationResponse(**result)
        else:
            error_msg = result.get('message', 'Voice generation failed') if result else 'Unknown error'
            raise HTTPException(status_code=500, detail=error_msg)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in voice generation: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/voice-design", response_model=VoiceGenerationResponse)
async def generate_voice_design(request: VoiceDesignRequest):
    """Generate voice using Qwen TTS voice design"""
    try:
        voice_generator = get_voice_generator_service()
        if not request.text or not request.text.strip():
            raise HTTPException(status_code=400, detail="Text is required")
        
        if not request.instruct or not request.instruct.strip():
            raise HTTPException(status_code=400, detail="Voice instruction is required")
        
        # Generate voice using voice design
        result = voice_generator.generate_voice_design(
            text=request.text,
            instruct=request.instruct,
            language=request.language,
            model_id=request.model_id
        )
        
        if result and result.get('success'):
            return VoiceGenerationResponse(**result)
        else:
            # Enhanced error handling with fallback information
            error_msg = result.get('message', 'Voice design generation failed') if result else 'Unknown error'
            error_type = result.get('error_type', 'unknown') if result else 'unknown'
            
            # Provide different status codes based on error type
            if error_type in ['service_unavailable', 'models_unavailable']:
                status_code = 503  # Service Unavailable
            elif error_type == 'config_error':
                status_code = 500  # Internal Server Error
            else:
                status_code = 500  # Internal Server Error
            
            # Include fallback suggestion in error details
            if result and 'fallback_suggestion' in result:
                error_msg += f" Suggestion: {result['fallback_suggestion']}"
            
            raise HTTPException(status_code=status_code, detail=error_msg)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in voice design generation: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/batch-voice-design", response_model=BatchVoiceGenerationResponse)
async def generate_batch_voice_design(request: BatchVoiceDesignRequest):
    """Generate multiple voices in batch using voice design"""
    try:
        voice_generator = get_voice_generator_service()
        if not request.texts or not all(text.strip() for text in request.texts):
            raise HTTPException(status_code=400, detail="All texts are required")
        
        if not request.instructs or not all(instruct.strip() for instruct in request.instructs):
            raise HTTPException(status_code=400, detail="All voice instructions are required")
        
        if len(request.texts) != len(request.instructs) or len(request.texts) != len(request.languages):
            raise HTTPException(status_code=400, detail="texts, instructs, and languages must have the same length")
        
        # Generate batch voices
        result = voice_generator.generate_batch_voice_design(
            texts=request.texts,
            instructs=request.instructs,
            languages=request.languages,
            model_id=request.model_id
        )
        
        if result and result.get('success'):
            return BatchVoiceGenerationResponse(**result)
        else:
            error_msg = result.get('message', 'Batch voice generation failed') if result else 'Unknown error'
            raise HTTPException(status_code=500, detail=error_msg)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in batch voice generation: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/history")
async def get_generation_history(limit: int = Query(20, ge=1, le=100)):
    """Get voice generation history"""
    try:
        voice_generator = get_voice_generator_service()
        history = voice_generator.get_generation_history(limit)
        return {"history": history}
    except Exception as e:
        logger.error(f"Error getting history: {e}")
        raise HTTPException(status_code=500, detail="Failed to get history")

@router.delete("/history/{filename}")
async def delete_generation(filename: str):
    """Delete a generated voice file"""
    try:
        voice_generator = get_voice_generator_service()
        success = voice_generator.delete_generation(filename)
        if success:
            return {"message": "Generation deleted successfully"}
        else:
            raise HTTPException(status_code=404, detail="Generation not found")
    except Exception as e:
        logger.error(f"Error deleting generation: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete generation")

@router.get("/audio/{filename}")
async def get_audio_file(filename: str):
    """Serve generated audio files"""
    try:
        audio_path = Path("assets/generated/audio/voice") / filename
        
        if not audio_path.exists():
            raise HTTPException(status_code=404, detail="Audio file not found")
        
        return FileResponse(
            path=str(audio_path),
            media_type="audio/wav",
            filename=filename
        )
    except Exception as e:
        logger.error(f"Error serving audio file: {e}")
        raise HTTPException(status_code=500, detail="Failed to serve audio file")
