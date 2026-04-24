"""API routes for SD WebUI options and configuration."""
from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel

from app.api.deps import get_sd_overrides
from app.infra.sd_request_layer import get_sd_layer, sd_provider_context
from app.core.config import get_settings
from app.utils.sd_provider import SDProviderOverrides

router = APIRouter(prefix="/sd", tags=["sd-options"])


def _sd_layer_for_request(overrides: SDProviderOverrides):
    if overrides and overrides.has_overrides():
        with sd_provider_context(
            overrides.provider,
            comfy_api_key=overrides.comfy_api_key,
            comfy_url=overrides.comfy_url,
            poe_api_key=overrides.poe_api_key,
            poe_url=overrides.poe_url,
            poe_model=overrides.poe_model,
        ):
            return get_sd_layer()
    return get_sd_layer()


class SDModelInfo(BaseModel):
    """SD checkpoint model info."""
    title: str
    model_name: str
    hash: Optional[str] = None
    sha256: Optional[str] = None
    filename: Optional[str] = None


class SamplerInfo(BaseModel):
    """Sampler info."""
    name: str
    aliases: List[str] = []


class SchedulerInfo(BaseModel):
    """Scheduler info."""
    name: str
    label: str


class UpscalerInfo(BaseModel):
    """Upscaler info."""
    name: str
    model_name: Optional[str] = None
    model_path: Optional[str] = None
    model_url: Optional[str] = None
    scale: Optional[float] = None


class LoraInfo(BaseModel):
    """LoRA model info."""
    name: str
    alias: Optional[str] = None
    path: Optional[str] = None


class StyleInfo(BaseModel):
    """Prompt style info."""
    name: str
    prompt: Optional[str] = None
    negative_prompt: Optional[str] = None


class AllOptionsResponse(BaseModel):
    """All available SD options for dropdowns."""
    sd_models: List[SDModelInfo]
    vae_models: List[str]
    samplers: List[SamplerInfo]
    schedulers: List[SchedulerInfo]
    upscalers: List[UpscalerInfo]
    loras: List[LoraInfo]
    styles: List[StyleInfo]
    controlnet_models: List[str]
    controlnet_modules: List[str]
    current_model: Optional[str] = None
    current_vae: Optional[str] = None
    current_sampler: Optional[str] = None
    current_scheduler: Optional[str] = None


class CurrentOptionsResponse(BaseModel):
    """Current SD settings."""
    provider: Optional[str] = None
    sd_model_checkpoint: Optional[str] = None
    sd_vae: Optional[str] = None
    CLIP_stop_at_last_layers: Optional[int] = None
    eta_noise_seed_delta: Optional[int] = None
    sampler_name: Optional[str] = None
    scheduler: Optional[str] = None


class SetOptionsRequest(BaseModel):
    """Request to set SD options."""
    sd_model_checkpoint: Optional[str] = None
    sd_vae: Optional[str] = None
    CLIP_stop_at_last_layers: Optional[int] = None
    sampler_name: Optional[str] = None
    scheduler: Optional[str] = None


@router.get("/options/all", response_model=AllOptionsResponse)
async def get_all_options(sd_overrides: SDProviderOverrides = Depends(get_sd_overrides)):
    """Get all available SD options for dropdown menus."""
    try:
        sd_layer = _sd_layer_for_request(sd_overrides)
        client = sd_layer.client
        
        # Get all options
        sd_models_raw = client.get_sd_models()
        vae_models = client.get_vae_models()
        samplers_raw = client.get_samplers()
        schedulers_raw = client.get_schedulers()
        upscalers_raw = client.get_upscalers()
        loras_raw = client.get_loras()
        styles_raw = client.get_styles()
        cn_models = client.get_controlnet_models()
        cn_modules = client.get_controlnet_modules()
        
        # Get current settings
        current = client.get_options()
        
        # Convert to response models
        sd_models = [SDModelInfo(**m) for m in sd_models_raw]
        samplers = [SamplerInfo(**s) for s in samplers_raw]
        schedulers = [SchedulerInfo(**s) for s in schedulers_raw]
        upscalers = [UpscalerInfo(**u) for u in upscalers_raw]
        loras = [LoraInfo(**l) for l in loras_raw]
        styles = [StyleInfo(**s) for s in styles_raw]
        
        return AllOptionsResponse(
            sd_models=sd_models,
            vae_models=vae_models,
            samplers=samplers,
            schedulers=schedulers,
            upscalers=upscalers,
            loras=loras,
            styles=styles,
            controlnet_models=cn_models,
            controlnet_modules=cn_modules,
            current_model=current.get("sd_model_checkpoint"),
            current_vae=current.get("sd_vae"),
            current_sampler=current.get("sampler_name"),
            current_scheduler=current.get("scheduler") or current.get("scheduler_name"),
        )
    except HTTPException:
        # Re-raise HTTP exceptions (like 503 from ComfyUI client)
        raise
    except Exception as e:
        # Root cause: Unexpected error in SD options processing
        # Solution: Return proper 503 with clear error message
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"ComfyUI service unavailable: {str(e)}. Please check if ComfyUI server is running."
        )


@router.get("/options/models")
async def get_sd_models(sd_overrides: SDProviderOverrides = Depends(get_sd_overrides)):
    """Get available SD checkpoint models."""
    sd_layer = _sd_layer_for_request(sd_overrides)
    models = sd_layer.client.get_sd_models()
    return {"models": models, "count": len(models)}


@router.get("/options/vae")
async def get_vae_models(sd_overrides: SDProviderOverrides = Depends(get_sd_overrides)):
    """Get available VAE models."""
    sd_layer = _sd_layer_for_request(sd_overrides)
    vae = sd_layer.client.get_vae_models()
    return {"vae_models": vae, "count": len(vae)}


@router.get("/options/samplers")
async def get_samplers(sd_overrides: SDProviderOverrides = Depends(get_sd_overrides)):
    """Get available samplers."""
    sd_layer = _sd_layer_for_request(sd_overrides)
    samplers = sd_layer.client.get_samplers()
    return {"samplers": samplers, "count": len(samplers)}


@router.get("/options/schedulers")
async def get_schedulers(sd_overrides: SDProviderOverrides = Depends(get_sd_overrides)):
    """Get available schedulers."""
    sd_layer = _sd_layer_for_request(sd_overrides)
    schedulers = sd_layer.client.get_schedulers()
    return {"schedulers": schedulers, "count": len(schedulers)}


@router.get("/options/upscalers")
async def get_upscalers(sd_overrides: SDProviderOverrides = Depends(get_sd_overrides)):
    """Get available upscalers."""
    sd_layer = _sd_layer_for_request(sd_overrides)
    upscalers = sd_layer.client.get_upscalers()
    return {"upscalers": upscalers, "count": len(upscalers)}


@router.get("/options/loras")
async def get_loras(sd_overrides: SDProviderOverrides = Depends(get_sd_overrides)):
    """Get available LoRA models."""
    sd_layer = _sd_layer_for_request(sd_overrides)
    loras = sd_layer.client.get_loras()
    return {"loras": loras, "count": len(loras)}


@router.get("/options/styles")
async def get_styles(sd_overrides: SDProviderOverrides = Depends(get_sd_overrides)):
    """Get available prompt styles."""
    sd_layer = _sd_layer_for_request(sd_overrides)
    styles = sd_layer.client.get_styles()
    return {"styles": styles, "count": len(styles)}


@router.get("/options/current")
async def get_current_options(sd_overrides: SDProviderOverrides = Depends(get_sd_overrides)):
    """Get current SD settings."""
    settings = get_settings()
    sd_layer = _sd_layer_for_request(sd_overrides)
    options = sd_layer.client.get_options()
    return {
        "provider": sd_overrides.provider or settings.sd_provider,
        "sd_model_checkpoint": options.get("sd_model_checkpoint"),
        "sd_vae": options.get("sd_vae"),
        "CLIP_stop_at_last_layers": options.get("CLIP_stop_at_last_layers"),
        "sampler_name": options.get("sampler_name"),
        "scheduler": options.get("scheduler"),
    }


@router.post("/options/set")
async def set_options(request: SetOptionsRequest, sd_overrides: SDProviderOverrides = Depends(get_sd_overrides)):
    """Set SD options."""
    sd_layer = _sd_layer_for_request(sd_overrides)
    
    options = {}
    if request.sd_model_checkpoint:
        options["sd_model_checkpoint"] = request.sd_model_checkpoint
    if request.sd_vae:
        options["sd_vae"] = request.sd_vae
    if request.CLIP_stop_at_last_layers is not None:
        options["CLIP_stop_at_last_layers"] = request.CLIP_stop_at_last_layers
    if request.sampler_name:
        options["sampler_name"] = request.sampler_name
    if request.scheduler:
        options["scheduler"] = request.scheduler
    
    if not options:
        return {"success": True, "message": "No options to set"}
    
    success = sd_layer.client.set_options(options)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to set SD options"
        )
    
    return {"success": True, "options_set": list(options.keys())}


@router.post("/refresh/models")
async def refresh_models(sd_overrides: SDProviderOverrides = Depends(get_sd_overrides)):
    """Refresh SD checkpoint models list."""
    sd_layer = _sd_layer_for_request(sd_overrides)
    success = sd_layer.client.refresh_models()
    return {"success": success}


@router.post("/refresh/vae")
async def refresh_vae(sd_overrides: SDProviderOverrides = Depends(get_sd_overrides)):
    """Refresh VAE models list."""
    sd_layer = _sd_layer_for_request(sd_overrides)
    success = sd_layer.client.refresh_vae()
    return {"success": success}


@router.post("/refresh/loras")
async def refresh_loras(sd_overrides: SDProviderOverrides = Depends(get_sd_overrides)):
    """Refresh LoRA models list."""
    sd_layer = _sd_layer_for_request(sd_overrides)
    success = sd_layer.client.refresh_loras()
    return {"success": success}


@router.post("/refresh/controlnet")
async def refresh_controlnet(sd_overrides: SDProviderOverrides = Depends(get_sd_overrides)):
    """Refresh ControlNet models list (clears cache)."""
    sd_layer = _sd_layer_for_request(sd_overrides)
    models = sd_layer.client.refresh_controlnet_models()
    return {"success": True, "models": models, "count": len(models)}


@router.get("/controlnet/models")
async def get_controlnet_models(sd_overrides: SDProviderOverrides = Depends(get_sd_overrides)):
    """Get available ControlNet models."""
    sd_layer = _sd_layer_for_request(sd_overrides)
    models = sd_layer.client.get_controlnet_models()
    return {"models": models, "count": len(models)}


@router.get("/controlnet/modules")
async def get_controlnet_modules(sd_overrides: SDProviderOverrides = Depends(get_sd_overrides)):
    """Get available ControlNet preprocessor modules."""
    sd_layer = _sd_layer_for_request(sd_overrides)
    modules = sd_layer.client.get_controlnet_modules()
    return {"modules": modules, "count": len(modules)}


@router.get("/health")
async def check_comfyui_health(sd_overrides: SDProviderOverrides = Depends(get_sd_overrides)):
    """Check ComfyUI server health status."""
    try:
        sd_layer = _sd_layer_for_request(sd_overrides)
        client = sd_layer.client
        
        # Try to get basic info from ComfyUI
        if hasattr(client, '_check_comfyui_connection'):
            is_connected = client._check_comfyui_connection()
        else:
            # Fallback check
            try:
                client.get_options()
                is_connected = True
            except:
                is_connected = False
        
        if is_connected:
            return {"status": "healthy", "message": "ComfyUI server is accessible"}
        else:
            return {"status": "unhealthy", "message": "ComfyUI server is not accessible"}
            
    except Exception as e:
        return {"status": "error", "message": f"Health check failed: {str(e)}"}
