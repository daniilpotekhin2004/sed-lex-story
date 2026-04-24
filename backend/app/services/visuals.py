from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import anyio

from app.core.config import get_settings
from app.infra.sd_request_layer import get_sd_layer
from app.infra.storage import LocalImageStorage
from app.services.pipeline_profiles import get_pipeline_resolver, PipelineSeedContext
from app.utils.sd_options import extract_sd_option_overrides


class VisualGenerationService:
    """Service for generating visual previews (sketches) for world library entities."""
    
    def __init__(self) -> None:
        self.settings = get_settings()
        self.storage = LocalImageStorage(self.settings.generated_assets_path / "world")

    async def generate_preview(
        self,
        folder: str,
        prompt: str,
        *,
        negative_prompt: Optional[str] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        style: Optional[str] = None,
        cfg_scale: Optional[float] = None,
        steps: Optional[int] = None,
        seed: Optional[int] = None,
        sampler: Optional[str] = None,
        scheduler: Optional[str] = None,
        model_id: Optional[str] = None,
        vae_id: Optional[str] = None,
        loras: Optional[List[dict]] = None,
        pipeline_profile_id: Optional[str] = None,
        pipeline_profile_version: Optional[int] = None,
        workflow_set: Optional[str] = None,
        workflow_task: Optional[str] = None,
        seed_policy: Optional[str] = None,
        seed_context: Optional[PipelineSeedContext] = None,
        init_images: Optional[List[bytes]] = None,
        reference_images: Optional[List[str]] = None,
        denoising_strength: Optional[float] = None,
        alwayson_scripts: Optional[dict] = None,
        use_option_overrides: bool = True,
        force_img2img: bool = False,
    ) -> str:
        """
        Generate a preview image for a world library entity.
        
        Uses SD Request Layer for automatic prompt translation and generation.
        """
        def _run() -> List[str]:
            resolver = get_pipeline_resolver()
            context = seed_context or PipelineSeedContext(kind="world_preview")
            seed_override = None if seed == -1 else seed
            sd_layer = get_sd_layer()
            option_overrides = (
                extract_sd_option_overrides(sd_layer.client.get_options()) if use_option_overrides else {}
            )
            model_override = model_id
            vae_override = vae_id
            sampler_override = sampler or option_overrides.get("sampler")
            scheduler_override = scheduler or option_overrides.get("scheduler")
            resolved = resolver.resolve(
                kind=context.kind,
                profile_id=pipeline_profile_id,
                profile_version=pipeline_profile_version,
                overrides={
                    "width": width,
                    "height": height,
                    "cfg_scale": cfg_scale,
                    "steps": steps,
                    "seed": seed_override,
                    "sampler": sampler_override,
                    "scheduler": scheduler_override,
                    "model_checkpoint": model_override,
                    "vae": vae_override,
                    "loras": loras,
                    "seed_policy": seed_policy,
                    "workflow_set": workflow_set,
                },
                seed_context=context,
            )
            init_batch = init_images
            # Root cause: Always used img2img when reference_images exist, even for preview display
            # Fix: Only use img2img when explicitly requested for style transfer/modification
            if init_batch is None and reference_images and (force_img2img or denoising_strength is not None):
                init_batch = self._load_reference_images(reference_images)
            images = sd_layer.generate_simple(
                prompt=prompt,
                negative_prompt=negative_prompt,
                num_images=1,
                width=resolved.width,
                height=resolved.height,
                style=style,
                cfg_scale=resolved.cfg_scale,
                steps=resolved.steps,
                seed=resolved.seed,
                sampler=resolved.sampler,
                scheduler=resolved.scheduler,
                model_id=resolved.model_id,
                vae_id=resolved.vae_id,
                loras=[lora.model_dump() for lora in resolved.loras],
                init_images=init_batch if init_batch else None,
                denoising_strength=denoising_strength,
                alwayson_scripts=alwayson_scripts,
                workflow_set=resolved.workflow_set,
                workflow_task=workflow_task or "scene",
            )
            return self.storage.save_images(folder, images)

        paths = await anyio.to_thread.run_sync(_run)
        path = paths[0]
        rel = Path(path).relative_to(self.settings.assets_root_path).as_posix()
        return f"/api/assets/{rel}"

    def _resolve_asset_path(self, url: str) -> Optional[Path]:
        if not url.startswith("/api/assets/"):
            return None
        rel = url[len("/api/assets/") :]
        return self.settings.assets_root_path / rel

    def _load_reference_images(self, urls: List[str]) -> List[bytes]:
        images: List[bytes] = []
        for url in urls[:2]:
            path = self._resolve_asset_path(url)
            if not path or not path.exists():
                continue
            try:
                images.append(path.read_bytes())
            except OSError:
                continue
        return images
