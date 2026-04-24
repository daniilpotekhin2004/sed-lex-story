from __future__ import annotations

from datetime import datetime
from typing import Optional

from celery import Celery
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.celery_app import celery_app
from app.domain.models import GenerationJob, GenerationStatus, GenerationTaskType
from app.schemas.generation_job import AssetGenerationJobCreate
from app.services.character import CharacterService
from app.services.world import WorldService


class AssetGenerationJobService:
    """Create and read generation jobs for non-scene assets.

    This service only *enqueues* work (Celery task). The worker performs the
    actual generation and writes results back into the target entity.
    """

    def __init__(self, session: AsyncSession, celery: Celery = celery_app):
        self.session = session
        self.celery = celery

    async def create_job(self, payload: AssetGenerationJobCreate, user_id: str) -> GenerationJob:
        # Basic validation + existence checks to fail fast.
        task_type = (payload.task_type or "").strip()
        entity_type = (payload.entity_type or "").strip()
        entity_id = (payload.entity_id or "").strip()

        if not task_type or not entity_type or not entity_id:
            raise ValueError("task_type/entity_type/entity_id are required")

        # Validate known task types (keep extensible: allow custom strings).
        known = {
            GenerationTaskType.CHARACTER_SKETCH,
            GenerationTaskType.CHARACTER_SHEET,
            GenerationTaskType.CHARACTER_REFERENCE,
            GenerationTaskType.CHARACTER_RENDER,
            GenerationTaskType.LOCATION_SKETCH,
            GenerationTaskType.LOCATION_SHEET,
            GenerationTaskType.ARTIFACT_SKETCH,
        }
        if task_type not in known:
            raise ValueError(f"Unsupported task_type: {task_type}")

        # Existence checks (permissions are enforced by the called services too).
        if entity_type == "character":
            cs = CharacterService(self.session)
            await cs.get_preset(entity_id, user_id=user_id)
        elif entity_type in {"location", "artifact"}:
            ws = WorldService(self.session)
            if entity_type == "location":
                await ws.get_location(entity_id)
            else:
                await ws.get_artifact(entity_id)
        else:
            raise ValueError(f"Unsupported entity_type: {entity_type}")

        config: dict = {}
        if payload.overrides is not None:
            config["overrides"] = payload.overrides.model_dump(exclude_none=True)
        if payload.project_id:
            config["project_id"] = payload.project_id
        if payload.style_profile_id:
            config["style_profile_id"] = payload.style_profile_id
        if payload.kind:
            config["kind"] = payload.kind
        if payload.payload is not None:
            config["payload"] = payload.payload

        job = GenerationJob(
            user_id=user_id,
            project_id=payload.project_id,
            scene_id=None,
            style_profile_id=payload.style_profile_id,
            task_type=task_type,
            entity_type=entity_type,
            entity_id=entity_id,
            status=GenerationStatus.QUEUED,
            progress=0,
            stage="queued",
            prompt=None,
            negative_prompt=None,
            config=config or None,
            results=None,
            error=None,
            started_at=None,
            finished_at=None,
        )

        self.session.add(job)
        await self.session.commit()
        await self.session.refresh(job)

        # Enqueue
        # Unified worker entrypoint (handles both SCENE_GENERATE and asset tasks)
        task_name = "app.workers.generation.process_generation_job"
        task = self.celery.tasks.get(task_name)
        if task is None:
            result = self.celery.send_task(task_name, args=[job.id])
        else:
            result = task.apply_async(args=[job.id])

        task_id = getattr(result, "id", None)
        if task_id:
            await self.session.execute(
                update(GenerationJob)
                .where(GenerationJob.id == job.id)
                .values(task_id=task_id)
            )
            await self.session.commit()
            await self.session.refresh(job)

        return job

    async def get_job(self, job_id: str, user_id: Optional[str] = None) -> Optional[GenerationJob]:
        result = await self.session.execute(select(GenerationJob).where(GenerationJob.id == job_id))
        job = result.scalar_one_or_none()
        if job is None:
            return None

        # If job has an owner, enforce it.
        if user_id and job.user_id and job.user_id != user_id:
            return None
        return job
