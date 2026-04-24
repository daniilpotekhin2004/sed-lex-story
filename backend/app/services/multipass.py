"""Multipass slide generation service with ControlNet support."""
from __future__ import annotations

import base64
import logging
import time
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from uuid import uuid4

from app.core.config import get_settings
from app.infra.sd_request_layer import get_sd_layer, SDRequest
from app.infra.storage import LocalImageStorage
from app.schemas.multipass import (
    ControlNetModule,
    ControlNetUnit,
    GenerationPass,
    MultipassRequest,
    MultipassResult,
    PassResult,
    PassType,
)
from app.services.pipeline_profiles import get_pipeline_resolver, PipelineSeedContext
from app.utils.sd_options import extract_sd_option_overrides

logger = logging.getLogger(__name__)


# Default pass configurations for auto-generation
DEFAULT_PASSES: Dict[str, List[GenerationPass]] = {
    "standard": [
        GenerationPass(
            pass_type=PassType.SKETCH,
            prompt_suffix="rough sketch, concept art, loose lines",
            denoising_strength=0.9,
            steps=15,
        ),
        GenerationPass(
            pass_type=PassType.BASE_COLOR,
            prompt_suffix="flat colors, clean coloring, base colors",
            denoising_strength=0.6,
            steps=20,
        ),
        GenerationPass(
            pass_type=PassType.FINAL,
            prompt_suffix="detailed, refined, high quality, sharp details",
            denoising_strength=0.4,
            steps=25,
        ),
    ],
    "detailed": [
        GenerationPass(
            pass_type=PassType.SKETCH,
            prompt_suffix="rough sketch, concept art",
            denoising_strength=0.95,
            steps=12,
        ),
        GenerationPass(
            pass_type=PassType.LINEART,
            prompt_suffix="clean lineart, precise lines, detailed outlines",
            denoising_strength=0.7,
            controlnet_units=[
                ControlNetUnit(module=ControlNetModule.LINEART, weight=0.8)
            ],
            steps=18,
        ),
        GenerationPass(
            pass_type=PassType.BASE_COLOR,
            prompt_suffix="flat colors, clean coloring",
            denoising_strength=0.55,
            steps=20,
        ),
        GenerationPass(
            pass_type=PassType.SHADING,
            prompt_suffix="shading, lighting, shadows, highlights",
            denoising_strength=0.45,
            steps=22,
        ),
        GenerationPass(
            pass_type=PassType.FINAL,
            prompt_suffix="detailed, refined, high quality",
            denoising_strength=0.35,
            steps=25,
        ),
    ],
}


class MultipassGenerationService:
    """Service for multipass image generation with ControlNet."""
    
    def __init__(self):
        self.settings = get_settings()
        self.storage = LocalImageStorage(self.settings.generated_assets_path / "multipass")
        self._character_cache: Dict[str, Any] = {}
    
    def generate_multipass(
        self,
        request: MultipassRequest,
        progress_callback: Optional[callable] = None,
    ) -> MultipassResult:
        """Execute multipass generation pipeline."""
        start_time = time.time()
        task_id = uuid4().hex
        
        # Determine passes to use
        passes = self._resolve_passes(request)
        total_passes = len(passes)
        
        logger.info(f"Starting multipass generation {task_id} with {total_passes} passes")
        
        # Load character references if specified
        character_prompts, character_refs = self._load_characters(
            request.character_ids,
            request.character_weights,
        )
        
        # Build base prompt with character info
        base_prompt = self._build_prompt(request.prompt, character_prompts)
        base_negative = request.negative_prompt or ""
        
        # Initialize with input image or None
        current_image: Optional[bytes] = None
        if request.init_image:
            current_image = self._load_image(request.init_image)
        
        resolver = get_pipeline_resolver()
        seed_override = None if request.seed == -1 else request.seed
        sd_layer = get_sd_layer()
        option_overrides = extract_sd_option_overrides(sd_layer.client.get_options())
        sampler = request.sampler or option_overrides.get("sampler")
        scheduler = request.scheduler or option_overrides.get("scheduler")
        model_override = request.model_id
        vae_override = request.vae_id
        resolved = resolver.resolve(
            kind="scene",
            profile_id=request.pipeline_profile_id,
            profile_version=request.pipeline_profile_version,
            overrides={
                "width": request.width,
                "height": request.height,
                "cfg_scale": request.cfg_scale,
                "steps": request.steps,
                "seed": seed_override,
                "sampler": sampler,
                "scheduler": scheduler,
                "model_checkpoint": model_override,
                "vae": vae_override,
                "loras": request.loras,
            },
            seed_context=PipelineSeedContext(kind="scene"),
        )

        pass_results: List[PassResult] = []
        current_seed = resolved.seed
        
        for idx, gen_pass in enumerate(passes):
            pass_start = time.time()
            
            if progress_callback:
                progress_callback(idx, total_passes, gen_pass.pass_type)
            
            # Build pass-specific prompt
            pass_prompt = base_prompt
            if gen_pass.prompt_suffix:
                pass_prompt = f"{base_prompt}, {gen_pass.prompt_suffix}"
            
            pass_negative = base_negative
            if gen_pass.negative_suffix:
                pass_negative = f"{base_negative}, {gen_pass.negative_suffix}"
            
            # Determine generation parameters
            cfg = gen_pass.cfg_scale or resolved.cfg_scale
            steps = gen_pass.steps or resolved.steps
            sampler = gen_pass.sampler or resolved.sampler
            
            # Build ControlNet configuration
            alwayson_scripts = self._build_controlnet_config(
                gen_pass.controlnet_units,
                current_image,
                character_refs,
            )
            
            # Determine init images
            init_images: Optional[List[bytes]] = None
            denoising = gen_pass.denoising_strength
            
            if gen_pass.use_previous_output and current_image:
                init_images = [current_image]
            elif idx == 0 and request.init_image:
                init_images = [current_image] if current_image else None
                denoising = request.init_denoising
            
            # Generate
            sd_layer = get_sd_layer()
            images = sd_layer.generate_simple(
                prompt=pass_prompt,
                negative_prompt=pass_negative if pass_negative else None,
                num_images=1,
                width=resolved.width,
                height=resolved.height,
                cfg_scale=cfg,
                steps=steps,
                seed=current_seed,
                sampler=sampler,
                scheduler=resolved.scheduler,
                model_id=resolved.model_id,
                vae_id=resolved.vae_id,
                loras=[lora.model_dump() for lora in resolved.loras],
                init_images=init_images,
                denoising_strength=denoising if init_images else None,
                alwayson_scripts=alwayson_scripts if alwayson_scripts else None,
                workflow_set=resolved.workflow_set,
                workflow_task="scene",
            )
            
            if not images:
                raise RuntimeError(f"Pass {idx} failed to generate images")
            
            current_image = images[0]
            
            # Save intermediate if requested
            image_url = ""
            if request.save_intermediate or idx == len(passes) - 1:
                folder = request.output_folder or f"slides/{task_id}"
                paths = self.storage.save_images(folder, [current_image])
                rel = Path(paths[0]).relative_to(self.settings.assets_root_path).as_posix()
                image_url = f"/api/assets/{rel}"
            
            pass_duration = int((time.time() - pass_start) * 1000)
            
            pass_results.append(PassResult(
                pass_index=idx,
                pass_type=gen_pass.pass_type,
                image_url=image_url,
                prompt_used=pass_prompt,
                negative_used=pass_negative if pass_negative else None,
                seed_used=current_seed,
                duration_ms=pass_duration,
                controlnet_applied=[u.module.value for u in gen_pass.controlnet_units],
            ))
            
            logger.info(f"Pass {idx} ({gen_pass.pass_type.value}) completed in {pass_duration}ms")
        
        # Save final image
        folder = request.output_folder or f"slides/{task_id}"
        paths = self.storage.save_images(folder, [current_image])
        rel = Path(paths[0]).relative_to(self.settings.assets_root_path).as_posix()
        final_url = f"/api/assets/{rel}"
        
        total_duration = int((time.time() - start_time) * 1000)
        
        return MultipassResult(
            task_id=task_id,
            final_image_url=final_url,
            passes=pass_results,
            total_duration_ms=total_duration,
            characters_used=request.character_ids,
            seed=current_seed,
            width=resolved.width,
            height=resolved.height,
        )
    
    def _resolve_passes(self, request: MultipassRequest) -> List[GenerationPass]:
        """Resolve which passes to use."""
        if request.passes:
            return request.passes
        
        if not request.auto_passes:
            # Single pass generation
            return [GenerationPass(
                pass_type=PassType.FINAL,
                denoising_strength=0.7 if request.init_image else 1.0,
            )]
        
        # Auto-generate passes based on count
        num_passes = min(request.num_auto_passes, self.settings.multipass_max_passes)
        
        if num_passes <= 3:
            return DEFAULT_PASSES["standard"][:num_passes]
        else:
            return DEFAULT_PASSES["detailed"][:num_passes]
    
    def _load_characters(
        self,
        character_ids: List[str],
        weights: Dict[str, float],
    ) -> Tuple[List[str], List[bytes]]:
        """Load character prompts and reference images."""
        prompts: List[str] = []
        refs: List[bytes] = []
        
        # This would integrate with CharacterLibraryService
        # For now, return empty - will be connected later
        
        return prompts, refs
    
    def _build_prompt(self, base: str, character_prompts: List[str]) -> str:
        """Build combined prompt with character descriptions."""
        parts = [base]
        parts.extend(character_prompts)
        return ", ".join(p for p in parts if p)
    
    def _load_image(self, source: str) -> bytes:
        """Load image from base64 or URL."""
        if source.startswith("data:"):
            # Base64 data URL
            _, data = source.split(",", 1)
            return base64.b64decode(data)
        elif source.startswith("/api/assets/"):
            # Local asset URL
            rel = source[len("/api/assets/"):]
            path = self.settings.assets_root_path / rel
            return path.read_bytes()
        elif source.startswith("http"):
            # Remote URL - would need httpx
            import httpx
            resp = httpx.get(source, timeout=30)
            resp.raise_for_status()
            return resp.content
        else:
            # Assume raw base64
            return base64.b64decode(source)
    
    def _build_controlnet_config(
        self,
        units: List[ControlNetUnit],
        current_image: Optional[bytes],
        character_refs: List[bytes],
    ) -> Optional[Dict[str, Any]]:
        """Build ControlNet alwayson_scripts configuration for SD Forge."""
        if not self.settings.controlnet_enabled:
            logger.info("ControlNet disabled in settings, skipping")
            return None
        
        if not units and not character_refs:
            return None
        
        sd_layer = get_sd_layer()
        available_models = sd_layer.client.get_controlnet_models()
        
        if not available_models:
            logger.warning("No ControlNet models available, skipping ControlNet")
            return None
        
        cn_args: List[Dict[str, Any]] = []
        
        for unit in units:
            # Determine input image for this unit
            input_img = None
            if unit.input_image:
                input_img = self._load_image(unit.input_image)
            elif current_image:
                input_img = current_image
            
            if not input_img:
                continue
            
            # Find matching model dynamically
            model_name = unit.model
            if not model_name or model_name not in available_models:
                model_name = sd_layer.client.find_controlnet_model(unit.module.value)
            
            if not model_name:
                logger.warning(f"No ControlNet model found for {unit.module.value}, skipping unit")
                continue
            
            # SD Forge ControlNet format - minimal required fields
            # Do NOT include resize_mode for txt2img - causes AttributeError
            cn_unit = {
                "enabled": True,
                "module": unit.module.value,
                "model": model_name,
                "weight": unit.weight,
                "guidance_start": unit.guidance_start,
                "guidance_end": unit.guidance_end,
                "processor_res": unit.processor_res,
                "threshold_a": unit.threshold_a,
                "threshold_b": unit.threshold_b,
                "low_vram": unit.low_vram,
                "pixel_perfect": unit.pixel_perfect,
                "image": base64.b64encode(input_img).decode(),  # Forge uses "image" not "input_image"
            }
            cn_args.append(cn_unit)
            logger.info(f"Added ControlNet unit: {unit.module.value} -> {model_name}")
        
        # Add character reference units (IP-Adapter style)
        for idx, ref in enumerate(character_refs[:2]):  # Max 2 character refs
            # Find IP-Adapter model
            ip_model = sd_layer.client.find_controlnet_model("ip-adapter-face" if idx == 0 else "ip-adapter")
            if not ip_model:
                logger.warning(f"No IP-Adapter model found for character ref {idx}, skipping")
                continue
            
            cn_args.append({
                "enabled": True,
                "module": "ip-adapter-face" if idx == 0 else "ip-adapter",
                "model": ip_model,
                "weight": 0.7,
                "guidance_start": 0.0,
                "guidance_end": 1.0,
                "image": base64.b64encode(ref).decode(),
            })
        
        if not cn_args:
            logger.info("No valid ControlNet units configured")
            return None
        
        return {
            "controlnet": {
                "args": cn_args
            }
        }
    
    def _get_default_model(self, module: ControlNetModule) -> str:
        """Get default ControlNet model for a module."""
        defaults = {
            ControlNetModule.OPENPOSE: "control_v11p_sd15_openpose",
            ControlNetModule.OPENPOSE_FULL: "control_v11p_sd15_openpose",
            ControlNetModule.CANNY: "control_v11p_sd15_canny",
            ControlNetModule.DEPTH: "control_v11f1p_sd15_depth",
            ControlNetModule.DEPTH_MIDAS: "control_v11f1p_sd15_depth",
            ControlNetModule.LINEART: "control_v11p_sd15_lineart",
            ControlNetModule.LINEART_ANIME: "control_v11p_sd15s2_lineart_anime",
            ControlNetModule.SOFTEDGE: "control_v11p_sd15_softedge",
            ControlNetModule.SCRIBBLE: "control_v11p_sd15_scribble",
            ControlNetModule.SEGMENTATION: "control_v11p_sd15_seg",
            ControlNetModule.REFERENCE_ONLY: "None",
            ControlNetModule.IP_ADAPTER: "ip-adapter-plus_sd15",
            ControlNetModule.IP_ADAPTER_FACE: "ip-adapter-plus-face_sd15",
        }
        return defaults.get(module, "None")
