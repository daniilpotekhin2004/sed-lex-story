from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import SceneNode
from app.schemas.generation import GenerationRequest
from app.schemas.multipass import MultipassRequest
from app.schemas.render_spec import RenderSpecCompileRequest, RenderSpecCompileResponse
from app.services.prompt_engine import PromptEngine


class RenderSpecMasterService:
    """Compile a scene into a spec consumable by existing generation endpoints.

    This master does *not* change generation logic. It only produces a structured
    request payload that the frontend (or orchestration layer) can send to:
    - POST /api/v1/generate (GenerationRequest) or
    - POST /api/v1/multipass (MultipassRequest)
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def compile_for_scene(self, scene_id: str, req: RenderSpecCompileRequest) -> RenderSpecCompileResponse:
        engine = PromptEngine(self.session)
        bundle = await engine.build_for_scene(scene_id)
        if bundle is None:
            raise HTTPException(status_code=404, detail="Scene not found")

        cfg = bundle.config or {}
        width = req.width or cfg.get("width") or 768
        height = req.height or cfg.get("height") or 512

        spec: Dict[str, Any]
        warnings: list[str] = []

        if req.mode == "generation":
            num_variants = req.num_variants or 4
            gen = GenerationRequest(
                prompt=bundle.prompt,
                negative_prompt=bundle.negative_prompt,
                num_variants=num_variants,
                width=int(width),
                height=int(height),
                cfg_scale=cfg.get("cfg_scale"),
                steps=cfg.get("steps"),
                sampler=cfg.get("sampler"),
                scheduler=cfg.get("scheduler"),
                model_id=cfg.get("model_checkpoint"),
                vae_id=cfg.get("vae"),
                loras=cfg.get("loras"),
                pipeline_profile_id=req.pipeline_profile_id or cfg.get("pipeline_profile_id"),
                pipeline_profile_version=req.pipeline_profile_version or cfg.get("pipeline_profile_version"),
            )
            spec = gen.model_dump(exclude_none=True)
        else:
            mp = MultipassRequest(
                prompt=bundle.prompt,
                negative_prompt=bundle.negative_prompt,
                width=int(width),
                height=int(height),
                seed=None,
                cfg_scale=float(cfg.get("cfg_scale") or 7.0),
                steps=int(cfg.get("steps") or 20),
                sampler=str(cfg.get("sampler") or "Euler a"),
                scheduler=cfg.get("scheduler"),
                model_id=cfg.get("model_checkpoint"),
                vae_id=cfg.get("vae"),
                loras=cfg.get("loras"),
                pipeline_profile_id=req.pipeline_profile_id or cfg.get("pipeline_profile_id"),
                pipeline_profile_version=req.pipeline_profile_version or cfg.get("pipeline_profile_version"),
                auto_passes=True,
                num_auto_passes=3,
                character_ids=list(cfg.get("character_ids") or []),
                character_weights={},
                init_image=None,
                init_denoising=0.7,
                save_intermediate=False,
                output_folder=None,
            )
            spec = mp.model_dump(exclude_none=True)

        stored = False
        if req.persist:
            scene = await self.session.get(SceneNode, scene_id)
            if scene is None:
                raise HTTPException(status_code=404, detail="Scene not found")
            ctx = scene.context if isinstance(scene.context, dict) else {}
            ctx["render_spec"] = {
                "mode": req.mode,
                "spec": spec,
                "compiled_at": datetime.utcnow().isoformat() + "Z",
            }
            scene.context = ctx
            await self.session.commit()
            stored = True

        return RenderSpecCompileResponse(mode=req.mode, spec=spec, stored=stored, warnings=warnings)
