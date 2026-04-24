"""API routes for multipass slide generation."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from app.schemas.multipass import (
    MultipassRequest,
    MultipassResult,
    MultipassStatus,
    ControlNetModule,
)
from app.services.multipass import MultipassGenerationService
from app.infra.sd_request_layer import get_sd_layer
from app.core.config import get_settings

router = APIRouter(prefix="/multipass", tags=["multipass"])


@router.post("/generate", response_model=MultipassResult)
async def generate_multipass(request: MultipassRequest):
    """Generate image using multipass pipeline with ControlNet."""
    settings = get_settings()
    if not settings.multipass_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Multipass generation is disabled"
        )
    
    service = MultipassGenerationService()
    try:
        result = service.generate_multipass(request)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/modules")
async def list_controlnet_modules():
    """List available ControlNet modules."""
    return {
        "modules": [m.value for m in ControlNetModule],
        "enabled": get_settings().controlnet_enabled,
    }


@router.get("/controlnet/models")
async def list_controlnet_models():
    """List ControlNet models available in SD WebUI."""
    settings = get_settings()
    if not settings.controlnet_enabled:
        return {
            "enabled": False,
            "models": [],
            "modules": [],
            "message": "ControlNet is disabled in settings"
        }
    
    try:
        sd_layer = get_sd_layer()
        models = sd_layer.client.get_controlnet_models()
        modules = sd_layer.client.get_controlnet_modules()
        return {
            "enabled": True,
            "models": models,
            "modules": modules,
            "model_count": len(models),
            "module_count": len(modules),
        }
    except Exception as e:
        return {
            "enabled": True,
            "models": [],
            "modules": [],
            "error": str(e),
            "message": "Failed to connect to SD WebUI"
        }


@router.get("/controlnet/check/{module}")
async def check_controlnet_module(module: str):
    """Check if a specific ControlNet module/model is available."""
    settings = get_settings()
    if not settings.controlnet_enabled:
        return {
            "available": False,
            "module": module,
            "model": None,
            "message": "ControlNet is disabled"
        }
    
    try:
        sd_layer = get_sd_layer()
        model = sd_layer.client.find_controlnet_model(module)
        return {
            "available": model is not None,
            "module": module,
            "model": model,
        }
    except Exception as e:
        return {
            "available": False,
            "module": module,
            "model": None,
            "error": str(e)
        }


@router.get("/config")
async def get_multipass_config():
    """Get multipass generation configuration."""
    settings = get_settings()
    return {
        "enabled": settings.multipass_enabled,
        "max_passes": settings.multipass_max_passes,
        "default_passes": settings.multipass_default_passes,
        "controlnet_enabled": settings.controlnet_enabled,
        "controlnet_models": settings.controlnet_models_list,
    }
