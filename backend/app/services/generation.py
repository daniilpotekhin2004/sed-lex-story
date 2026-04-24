from uuid import uuid4
from pathlib import Path

from celery.result import AsyncResult

from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.schemas.generation import (
    GenerationRequest,
    PipelineCheckStatus,
    TaskListItem,
    TaskListResponse,
    TaskStatus,
)
from app.services.pipeline_profiles import get_pipeline_resolver, PipelineSeedContext
from app.infra.sd_request_layer import get_sd_layer, sd_provider_context
from app.utils.sd_provider import SDProviderOverrides
from app.utils.sd_options import extract_sd_option_overrides


class ImageGenerationService:
    def __init__(self):
        self.celery = celery_app
        self.settings = get_settings()

    def enqueue_generation(
        self,
        scene_id: str,
        payload: GenerationRequest,
        *,
        sd_overrides: SDProviderOverrides | None = None,
    ) -> str:
        sd_overrides = (sd_overrides or SDProviderOverrides()).normalized()
        resolver = get_pipeline_resolver()
        seed_override = None if payload.seed == -1 else payload.seed
        with sd_provider_context(
            sd_overrides.provider,
            comfy_api_key=sd_overrides.comfy_api_key,
            comfy_url=sd_overrides.comfy_url,
            poe_api_key=sd_overrides.poe_api_key,
            poe_url=sd_overrides.poe_url,
            poe_model=sd_overrides.poe_model,
        ):
            sd_layer = get_sd_layer()
            option_overrides = extract_sd_option_overrides(sd_layer.client.get_options())
        sampler = payload.sampler or option_overrides.get("sampler")
        scheduler = payload.scheduler or option_overrides.get("scheduler")
        model_override = payload.model_id
        vae_override = payload.vae_id
        resolved = resolver.resolve(
            kind="scene",
            profile_id=payload.pipeline_profile_id,
            profile_version=payload.pipeline_profile_version,
            overrides={
                "width": payload.width,
                "height": payload.height,
                "cfg_scale": payload.cfg_scale,
                "steps": payload.steps,
                "seed": seed_override,
                "sampler": sampler,
                "scheduler": scheduler,
                "model_checkpoint": model_override,
                "vae": vae_override,
                "loras": payload.loras,
            },
            seed_context=PipelineSeedContext(kind="scene"),
        )
        task = self.celery.send_task(
            "app.workers.generation.generate_images",
            args=[
                scene_id,
                payload.prompt,
                payload.negative_prompt,
                payload.style,
                payload.num_variants,
                resolved.width,
                resolved.height,
                resolved.cfg_scale,
                resolved.steps,
                resolved.seed,
                resolved.sampler,
                resolved.scheduler,
                resolved.model_id,
                resolved.vae_id,
                [lora.model_dump() for lora in resolved.loras],
                resolved.workflow_set,
                "scene",
                sd_overrides.provider,
                sd_overrides.comfy_api_key,
                sd_overrides.comfy_url,
            ],
        )
        return task.id

    def generate(self, payload: GenerationRequest, *, sd_overrides: SDProviderOverrides | None = None) -> str:
        """Generic generation without strict scene binding (uses pseudo scene id)."""
        sd_overrides = (sd_overrides or SDProviderOverrides()).normalized()
        pseudo_scene = f"adhoc-{uuid4().hex}"
        resolver = get_pipeline_resolver()
        seed_override = None if payload.seed == -1 else payload.seed
        with sd_provider_context(
            sd_overrides.provider,
            comfy_api_key=sd_overrides.comfy_api_key,
            comfy_url=sd_overrides.comfy_url,
            poe_api_key=sd_overrides.poe_api_key,
            poe_url=sd_overrides.poe_url,
            poe_model=sd_overrides.poe_model,
        ):
            sd_layer = get_sd_layer()
            option_overrides = extract_sd_option_overrides(sd_layer.client.get_options())
        sampler = payload.sampler or option_overrides.get("sampler")
        scheduler = payload.scheduler or option_overrides.get("scheduler")
        model_override = payload.model_id
        vae_override = payload.vae_id
        resolved = resolver.resolve(
            kind="scene",
            profile_id=payload.pipeline_profile_id,
            profile_version=payload.pipeline_profile_version,
            overrides={
                "width": payload.width,
                "height": payload.height,
                "cfg_scale": payload.cfg_scale,
                "steps": payload.steps,
                "seed": seed_override,
                "sampler": sampler,
                "scheduler": scheduler,
                "model_checkpoint": model_override,
                "vae": vae_override,
                "loras": payload.loras,
            },
            seed_context=PipelineSeedContext(kind="scene"),
        )
        task = self.celery.send_task(
            "app.workers.generation.generate_images",
            args=[
                pseudo_scene,
                payload.prompt,
                payload.negative_prompt,
                payload.style,
                payload.num_variants,
                resolved.width,
                resolved.height,
                resolved.cfg_scale,
                resolved.steps,
                resolved.seed,
                resolved.sampler,
                resolved.scheduler,
                resolved.model_id,
                resolved.vae_id,
                [lora.model_dump() for lora in resolved.loras],
                resolved.workflow_set,
                "scene",
                sd_overrides.provider,
                sd_overrides.comfy_api_key,
                sd_overrides.comfy_url,
            ],
        )
        return task.id

    def run_pipeline_check(self, *, sd_overrides: SDProviderOverrides | None = None) -> PipelineCheckStatus:
        sd_overrides = (sd_overrides or SDProviderOverrides()).normalized()
        task = self.celery.send_task(
            "app.workers.generation.pipeline_check",
            args=[
                sd_overrides.provider,
                sd_overrides.comfy_api_key,
                sd_overrides.comfy_url,
            ],
        )
        return self._build_status(task)

    def get_pipeline_check_status(self, task_id: str) -> PipelineCheckStatus:
        async_result = AsyncResult(task_id, app=self.celery)
        return self._build_status(async_result)

    def get_tasks(
        self, page: int = 1, page_size: int = 20, status: str | None = None
    ) -> TaskListResponse:
        """Получить список задач из backend хранилища Celery (Redis)."""
        if self.settings.celery_task_always_eager:
            return TaskListResponse(items=[], total=0, page=page, page_size=page_size)

        backend = getattr(self.celery, "backend", None)
        items: list[TaskListItem] = []
        total = 0

        if backend and hasattr(backend, "client"):
            client = backend.client
            prefix: str = getattr(backend, "keyprefix", "celery-task-meta-")
            cursor = 0
            keys: list[str] = []
            # Собираем все task-ключи (упрощённо, можно оптимизировать)
            try:
                while True:
                    cursor, batch = client.scan(cursor=cursor, match=f"{prefix}*", count=100)
                    keys.extend(k.decode() if isinstance(k, bytes) else str(k) for k in batch)
                    if cursor == 0:
                        break
            except Exception:
                # Если Redis недоступен, возвращаем пустой список без падения API
                return TaskListResponse(items=[], total=0, page=page, page_size=page_size)
            total = len(keys)
            start = max(0, (page - 1) * page_size)
            end = start + page_size
            for key in keys[start:end]:
                task_id = key.replace(prefix, "")
                meta = backend.get_task_meta(task_id)
                state = meta.get("status") or meta.get("state")
                if status and state and state.lower() != status.lower():
                    continue
                ready = state in {"SUCCESS", "FAILURE"}
                result = meta.get("result")
                prompt = None
                image_urls = None
                if isinstance(result, dict):
                    prompt = result.get("prompt")
                    paths = result.get("paths") or result.get("images")
                    if paths:
                        image_urls = []
                        for p in paths:
                            try:
                                rel = Path(p).relative_to(self.settings.assets_root_path).as_posix()
                            except ValueError:
                                rel = str(p).lstrip("/")
                            image_urls.append(f"/api/assets/{rel}")
                items.append(
                    TaskListItem(
                        task_id=task_id,
                        state=state,
                        ready=ready,
                        created_at=str(meta.get("date_done") or ""),
                        prompt=prompt,
                        image_urls=image_urls,
                    )
                )
            total = len(items) if status else total

        return TaskListResponse(items=items, total=total, page=page, page_size=page_size)

    def get_task_status(self, task_id: str) -> TaskStatus:
        async_result = AsyncResult(task_id, app=self.celery)
        ready = async_result.ready()
        success = async_result.successful() if ready else None
        result = async_result.result if ready and success else None
        error = str(async_result.result) if ready and not success else None
        
        # Извлекаем параметры из результата если доступны
        prompt = None
        negative_prompt = None
        cfg_scale = None
        steps = None
        image_urls = None
        if isinstance(result, dict):
            prompt = result.get("prompt")
            negative_prompt = result.get("negative_prompt")
            cfg_scale = result.get("cfg_scale")
            steps = result.get("steps")

            if result.get("image_urls"):
                image_urls = result["image_urls"]
            else:
                paths = result.get("paths") or result.get("images")
                if paths:
                    image_urls = []
                    for p in paths:
                        try:
                            rel = Path(p).relative_to(self.settings.assets_root_path).as_posix()
                        except ValueError:
                            rel = str(p).lstrip("/")
                        image_urls.append(f"/api/assets/{rel}")
        
        return TaskStatus(
            task_id=task_id,
            state=async_result.state,
            ready=ready,
            success=success,
            result=result if isinstance(result, dict) else None,
            error=error,
            prompt=prompt,
            negative_prompt=negative_prompt,
            cfg_scale=cfg_scale,
            steps=steps,
            image_urls=image_urls,
        )

    def _build_status(self, result: AsyncResult) -> PipelineCheckStatus:
        ready = result.ready()
        success = result.successful() if ready else None
        details = result.result if ready and success else None
        error = str(result.result) if ready and not success else None

        return PipelineCheckStatus(
            task_id=result.id,
            state=result.state,
            ready=ready,
            success=success,
            details=details,
            error=error,
        )
