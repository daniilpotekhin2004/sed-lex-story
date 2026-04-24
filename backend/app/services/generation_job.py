from __future__ import annotations

from datetime import datetime
import logging
from pathlib import Path
from typing import Optional, Iterable

from celery import Celery
from sqlalchemy import desc, select, update
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.core.telemetry import track_event
from app.domain.models import (
    Artifact,
    CharacterPreset,
    GenerationJob,
    GenerationStatus,
    GenerationTaskType,
    ImageVariant,
    Location,
    SceneNode,
)
from app.schemas.generation_job import AssetGenerationJobCreate, GenerationJobCreate
from app.schemas.prompting import PromptBundle
from app.services.prompt_engine import PromptEngine
from app.services.pipeline_profiles import (
    get_pipeline_resolver,
    PipelineSeedContext,
    peek_pipeline_profile,
    is_qwen_profile,
)
from app.infra.sd_request_layer import get_sd_layer, sd_provider_context
from app.utils.sd_provider import SDProviderOverrides
from app.utils.sd_options import extract_sd_option_overrides
from app.infra.translator import get_translator


class GenerationJobService:
    def __init__(self, session: AsyncSession, celery: Celery = celery_app):
        self.session = session
        self.celery = celery
        self.settings = get_settings()
        self.prompt_engine = PromptEngine(session)
        self.logger = logging.getLogger(__name__)

    def _dispatch_generation_task(self, job_id: str) -> Optional[str]:
        """Dispatch generation task.

        In eager mode we execute inline so tests and local runs see deterministic results,
        especially when using a shared in-memory SQLite database.
        """
        task_name = "app.workers.generation.process_generation_job"
        task = self.celery.tasks.get(task_name)
        task_always_eager = bool(getattr(self.celery.conf, "task_always_eager", False))

        if task_always_eager:
            try:
                if task is not None:
                    task.apply(args=[job_id], throw=False)
                else:
                    # Fallback: import the task directly when registry is not initialized yet.
                    from app.workers.generation import process_generation_job

                    process_generation_job.apply(args=[job_id], throw=False)
            except Exception:
                self.logger.exception("Failed to process eager generation job %s", job_id)
            return f"eager-{job_id}"

        if task is None:
            result = self.celery.send_task(task_name, args=[job_id])
        else:
            result = task.apply_async(args=[job_id])
        return getattr(result, "id", None)

    @staticmethod
    def _normalize_kind_list(value: object) -> tuple[str, ...]:
        if not isinstance(value, Iterable) or isinstance(value, (str, bytes, dict)):
            return ()
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            kind = str(item).strip().lower()
            if not kind or kind in seen:
                continue
            seen.add(kind)
            normalized.append(kind)
        return tuple(sorted(normalized))

    async def _find_active_asset_job(
        self,
        *,
        user_id: str,
        payload: AssetGenerationJobCreate,
    ) -> Optional[GenerationJob]:
        """Return an existing queued/running asset job for same target to avoid duplicate cloud calls."""
        stmt = (
            select(GenerationJob)
            .options(selectinload(GenerationJob.variants))
            .where(
                GenerationJob.user_id == user_id,
                GenerationJob.task_type == payload.task_type,
                GenerationJob.entity_type == payload.entity_type,
                GenerationJob.entity_id == payload.entity_id,
                GenerationJob.status.in_([GenerationStatus.QUEUED, GenerationStatus.RUNNING]),
            )
            .order_by(desc(GenerationJob.created_at))
            .limit(10)
        )
        result = await self.session.execute(stmt)
        candidates = list(result.scalars().all())
        if not candidates:
            return None

        target_kind = (payload.kind or "").strip().lower()
        target_kinds = self._normalize_kind_list(
            payload.payload.get("kinds") if isinstance(payload.payload, dict) else None
        )
        for job in candidates:
            config = job.config if isinstance(job.config, dict) else {}
            config_kind = str(config.get("kind") or "").strip().lower()
            config_kinds = self._normalize_kind_list(
                (config.get("payload") or {}).get("kinds")
                if isinstance(config.get("payload"), dict)
                else None
            )
            if payload.task_type == GenerationTaskType.CHARACTER_REFERENCE and target_kind and config_kind != target_kind:
                continue
            if payload.task_type == GenerationTaskType.CHARACTER_SHEET and target_kinds and config_kinds and config_kinds != target_kinds:
                continue
            return job
        return None

    async def create_job(
        self,
        scene_id: str,
        payload: GenerationJobCreate,
        *,
        user_id: str | None = None,
        sd_overrides: SDProviderOverrides | None = None,
    ) -> Optional[GenerationJob]:
        scene = await self._load_scene(scene_id)
        if scene is None or scene.graph is None:
            return None

        if payload.use_prompt_engine or not payload.prompt:
            bundle = await self.prompt_engine.build_for_scene(scene.id, payload.style_profile_id)
            if bundle is None:
                return None
            prompt = bundle.prompt
            negative_prompt = bundle.negative_prompt
            cfg = bundle.config
        else:
            prompt = payload.prompt or scene.content
            negative_prompt = payload.negative_prompt
            cfg = {}

        translator = get_translator()
        prompt, negative_prompt = translator.translate_prompt_and_negative(prompt, negative_prompt)

        sd_overrides = (sd_overrides or SDProviderOverrides()).normalized()
        with sd_provider_context(
            sd_overrides.provider,
            comfy_api_key=sd_overrides.comfy_api_key,
            comfy_url=sd_overrides.comfy_url,
            poe_api_key=sd_overrides.poe_api_key,
            poe_url=sd_overrides.poe_url,
            poe_model=sd_overrides.poe_model,
        ):
            resolver = get_pipeline_resolver()
            sd_layer = get_sd_layer()
            option_overrides = extract_sd_option_overrides(sd_layer.client.get_options())
        seed_policy = payload.seed_policy or cfg.get("seed_policy")
        if seed_policy == "character-consistent":
            seed_policy = "derived"

        seed_override = None
        if payload.seed is not None:
            if payload.seed == -1:
                seed_policy = "random"
                seed_override = None
            else:
                seed_override = payload.seed
        else:
            seed_override = cfg.get("seed")

        if payload.seed is None and payload.num_variants > 1 and seed_policy in {"derived", "fixed"}:
            seed_policy = "random"
            seed_override = None

        profile_id = payload.pipeline_profile_id or cfg.get("pipeline_profile_id")
        profile_version = payload.pipeline_profile_version or cfg.get("pipeline_profile_version")
        profile_hint = peek_pipeline_profile(
            resolver,
            kind="scene",
            profile_id=profile_id,
            profile_version=profile_version,
        )
        use_qwen_defaults = is_qwen_profile(profile_hint)

        cfg_scale = payload.cfg_scale if payload.cfg_scale is not None else (None if use_qwen_defaults else cfg.get("cfg_scale"))
        steps = payload.steps if payload.steps is not None else (None if use_qwen_defaults else cfg.get("steps"))
        sampler = (None if use_qwen_defaults else cfg.get("sampler")) or option_overrides.get("sampler")
        scheduler = (None if use_qwen_defaults else cfg.get("scheduler")) or option_overrides.get("scheduler")
        model_checkpoint = None if use_qwen_defaults else cfg.get("model_checkpoint")
        vae = None if use_qwen_defaults else cfg.get("vae")
        loras = None if use_qwen_defaults else (cfg.get("loras") or cfg.get("lora_refs"))

        overrides = {
            "width": payload.width or cfg.get("width"),
            "height": payload.height or cfg.get("height"),
            "cfg_scale": cfg_scale,
            "steps": steps,
            "seed": seed_override,
            "sampler": sampler,
            "scheduler": scheduler,
            "model_checkpoint": model_checkpoint,
            "vae": vae,
            "loras": loras,
            "seed_policy": seed_policy,
        }
        seed_context = PipelineSeedContext(
            kind="scene",
            project_id=scene.graph.project_id,
            scene_id=scene.id,
            character_ids=cfg.get("character_ids") if isinstance(cfg.get("character_ids"), list) else None,
        )
        resolved = resolver.resolve(
            kind="scene",
            profile_id=profile_id,
            profile_version=profile_version,
            overrides=overrides,
            seed_context=seed_context,
        )

        config = {
            "num_variants": payload.num_variants,
            "width": resolved.width,
            "height": resolved.height,
            "cfg_scale": resolved.cfg_scale,
            "steps": resolved.steps,
            "seed": resolved.seed,
            "sampler": resolved.sampler,
            "scheduler": resolved.scheduler,
            "model_id": resolved.model_id,
            "vae_id": resolved.vae_id,
            "loras": [lora.model_dump() for lora in resolved.loras],
            "seed_policy": resolved.seed_policy,
            "pipeline_profile_id": resolved.profile_id,
            "pipeline_profile_version": resolved.profile_version,
        }
        if sd_overrides.has_overrides():
            config.update(sd_overrides.to_config())
        if payload.pipeline is not None:
            config["pipeline"] = payload.pipeline
        if payload.slide_id is not None:
            config["slide_id"] = payload.slide_id
        if payload.auto_approve:
            config["auto_approve"] = True

        job = GenerationJob(
            # Scene context
            project_id=scene.graph.project_id,
            scene_id=scene.id,
            style_profile_id=payload.style_profile_id,

            # Optional user linkage
            user_id=user_id,

            # Generic routing fields
            task_type="scene_generate",
            entity_type="scene",
            entity_id=scene.id,

            status=GenerationStatus.QUEUED,
            progress=0,
            stage="queued",

            prompt=prompt,
            negative_prompt=negative_prompt,
            config=config,
        )
        self.session.add(job)
        await self.session.commit()
        # Eager load relationships to avoid lazy load issues (style_profile is optional, loaded separately if needed)
        try:
            await self.session.refresh(job, ["scene", "variants"])
        except InvalidRequestError:
            job = await self.session.get(
                GenerationJob,
                job.id,
                options=[selectinload(GenerationJob.scene), selectinload(GenerationJob.variants)],
            ) or job
        track_event(
            "generation_job_created",
            metadata={
                "job_id": job.id,
                "scene_id": scene.id,
                "project_id": scene.graph.project_id,
                "use_prompt_engine": payload.use_prompt_engine,
            },
        )

        task_id = self._dispatch_generation_task(job.id)
        if task_id:
            await self.session.execute(
                update(GenerationJob)
                .where(GenerationJob.id == job.id)
                .values(task_id=task_id)
            )
            await self.session.commit()
        # Eager load relationships to avoid lazy load issues (style_profile is optional, loaded separately if needed)
        try:
            await self.session.refresh(job, ["scene", "variants"])
        except InvalidRequestError:
            job = await self.session.get(
                GenerationJob,
                job.id,
                options=[selectinload(GenerationJob.scene), selectinload(GenerationJob.variants)],
            ) or job
        return job

    async def create_asset_job(
        self,
        payload: AssetGenerationJobCreate,
        user_id: str,
        *,
        sd_overrides: SDProviderOverrides | None = None,
    ) -> Optional[GenerationJob]:
        """Create a unified async generation job for non-scene assets (characters, locations, artifacts, ...).

        The heavy work is executed by the Celery worker (app.workers.generation.process_generation_job).
        """

        resolved_project_id = payload.project_id
        prompt_hint = f"[{payload.task_type}] {payload.entity_type}:{payload.entity_id}"

        # Validate entity exists and infer project_id when possible.
        if payload.entity_type == "character":
            preset = await self.session.get(CharacterPreset, payload.entity_id)
            if preset is None:
                return None
            resolved_project_id = resolved_project_id or preset.project_id
            if preset.name:
                prompt_hint = f"[{payload.task_type}] {preset.name}"
        elif payload.entity_type == "location":
            location = await self.session.get(Location, payload.entity_id)
            if location is None:
                return None
            resolved_project_id = resolved_project_id or location.project_id
            if location.name:
                prompt_hint = f"[{payload.task_type}] {location.name}"
        elif payload.entity_type == "artifact":
            artifact = await self.session.get(Artifact, payload.entity_id)
            if artifact is None:
                return None
            resolved_project_id = resolved_project_id or artifact.project_id
            if artifact.name:
                prompt_hint = f"[{payload.task_type}] {artifact.name}"

        # Basic validation for known task types.
        if payload.task_type == GenerationTaskType.CHARACTER_REFERENCE and not payload.kind:
            raise ValueError("kind is required for character_reference")

        existing_job = await self._find_active_asset_job(user_id=user_id, payload=payload)
        if existing_job is not None:
            track_event(
                "generation_job_deduplicated",
                metadata={
                    "job_id": existing_job.id,
                    "task_type": existing_job.task_type,
                    "entity_type": existing_job.entity_type,
                    "entity_id": existing_job.entity_id,
                },
            )
            return existing_job

        config: dict = {
            "overrides": payload.overrides.model_dump() if payload.overrides else None,
            "num_variants": payload.num_variants,
            "kind": payload.kind,
            "payload": payload.payload,
        }
        sd_overrides = (sd_overrides or SDProviderOverrides()).normalized()
        if sd_overrides.has_overrides():
            config.update(sd_overrides.to_config())

        job = GenerationJob(
            user_id=user_id,
            project_id=resolved_project_id,
            scene_id=None,
            style_profile_id=payload.style_profile_id,
            task_type=payload.task_type,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            status=GenerationStatus.QUEUED,
            progress=0,
            stage="queued",
            prompt=prompt_hint,
            negative_prompt=None,
            config=config,
        )
        self.session.add(job)
        await self.session.commit()
        try:
            await self.session.refresh(job, ["variants"])
        except InvalidRequestError:
            # In rare cases the instance is detached after commit; re-fetch instead.
            job = await self.session.get(GenerationJob, job.id, options=[selectinload(GenerationJob.variants)]) or job

        track_event(
            "generation_job_created",
            metadata={
                "job_id": job.id,
                "task_type": job.task_type,
                "entity_type": job.entity_type,
                "entity_id": job.entity_id,
                "project_id": job.project_id,
            },
        )

        task_id = self._dispatch_generation_task(job.id)
        if task_id:
            await self.session.execute(
                update(GenerationJob)
                .where(GenerationJob.id == job.id)
                .values(task_id=task_id)
            )
            await self.session.commit()

        try:
            await self.session.refresh(job, ["variants"])
        except InvalidRequestError:
            job = await self.session.get(GenerationJob, job.id, options=[selectinload(GenerationJob.variants)]) or job
        return job

    async def get_job(self, job_id: str, *, user_id: str | None = None) -> Optional[GenerationJob]:
        stmt = (
            select(GenerationJob)
            .options(selectinload(GenerationJob.variants))
            .where(GenerationJob.id == job_id)
        )
        if user_id is not None:
            stmt = stmt.where(GenerationJob.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_jobs_for_entity(
        self,
        *,
        user_id: str,
        entity_type: str,
        entity_id: str,
        limit: int = 20,
    ) -> list[GenerationJob]:
        """List recent jobs for a specific entity (used by UI to show history / resume polling)."""
        stmt = (
            select(GenerationJob)
            .options(selectinload(GenerationJob.variants))
            .where(
                GenerationJob.user_id == user_id,
                GenerationJob.entity_type == entity_type,
                GenerationJob.entity_id == entity_id,
            )
            .order_by(desc(GenerationJob.created_at))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_scene_images(self, scene_id: str) -> list[ImageVariant]:
        result = await self.session.execute(
            select(ImageVariant).where(ImageVariant.scene_id == scene_id)
        )
        return list(result.scalars().all())

    async def approve_variant(self, scene_id: str, variant_id: str) -> ImageVariant | None:
        variant = await self.session.get(ImageVariant, variant_id)
        if variant is None or variant.scene_id != scene_id:
            return None

        # Unapprove others for the scene
        await self.session.execute(
            ImageVariant.__table__.update()
            .where(ImageVariant.scene_id == scene_id)
            .values(is_approved=False)
        )

        variant.is_approved = True
        await self.session.commit()
        # Eager load relationships to avoid lazy load issues
        # ImageVariant model has only `job` relationship (no `scene` relationship).
        await self.session.refresh(variant, ["job"])
        track_event("variant_approved", metadata={"scene_id": scene_id, "variant_id": variant_id})
        return variant

    async def delete_variant(self, scene_id: str, variant_id: str) -> bool:
        variant = await self.session.get(ImageVariant, variant_id)
        if variant is None or variant.scene_id != scene_id:
            return False

        self._delete_variant_files(variant)
        await self.session.delete(variant)
        await self.session.commit()
        return True

    def _delete_variant_files(self, variant: ImageVariant) -> None:
        assets_root = self.settings.assets_root_path.resolve()
        candidates: list[Path] = []
        metadata = variant.image_metadata or {}
        raw_path = metadata.get("path")
        if isinstance(raw_path, str):
            candidates.append(Path(raw_path))
        if isinstance(variant.url, str) and variant.url.startswith("/api/assets/"):
            rel = variant.url[len("/api/assets/") :]
            candidates.append(self.settings.assets_root_path / rel)
        if isinstance(variant.thumbnail_url, str) and variant.thumbnail_url.startswith("/api/assets/"):
            rel = variant.thumbnail_url[len("/api/assets/") :]
            candidates.append(self.settings.assets_root_path / rel)

        for path in candidates:
            try:
                resolved = path.resolve()
            except OSError:
                continue
            if assets_root not in resolved.parents and resolved != assets_root:
                continue
            try:
                resolved.unlink(missing_ok=True)
            except OSError:
                continue

    async def _load_scene(self, scene_id: str) -> Optional[SceneNode]:
        result = await self.session.execute(
            select(SceneNode)
            .options(selectinload(SceneNode.graph))
            .where(SceneNode.id == scene_id)
        )
        return result.scalar_one_or_none()
