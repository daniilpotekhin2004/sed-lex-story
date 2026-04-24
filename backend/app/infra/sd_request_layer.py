"""
SD Request Layer - единая точка входа для всех запросов к Stable Diffusion.

Этот модуль является промежуточным звеном между бизнес-логикой и SD API.
Все генерации изображений должны проходить через этот слой.

Функции:
- Автоматический перевод промптов на английский
- Логирование всех запросов
- Единая обработка ошибок
- Возможность добавления middleware (rate limiting, caching, etc.)
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import List, Optional

from app.infra.sd_client import build_sd_client, BaseSdClient
from app.infra.comfy_client import ComfySdClient
from app.utils.sd_provider import SDProviderOverrides
from app.infra.translator import get_translator
from app.services.pipeline_profiles import get_pipeline_resolver, PipelineSeedContext
from app.utils.sd_tokens import extract_lora_tokens, merge_loras

logger = logging.getLogger(__name__)


@dataclass
class SDRequest:
    """Структура запроса к SD."""
    prompt: str
    negative_prompt: Optional[str] = None
    num_images: int = 1
    width: Optional[int] = None
    height: Optional[int] = None
    style: Optional[str] = None
    cfg_scale: Optional[float] = None
    steps: Optional[int] = None
    seed: Optional[int] = None
    sampler: Optional[str] = None
    scheduler: Optional[str] = None
    model_id: Optional[str] = None
    vae_id: Optional[str] = None
    loras: Optional[List[dict]] = None
    init_images: Optional[List[bytes]] = None
    denoising_strength: Optional[float] = None
    alwayson_scripts: Optional[dict] = None
    override_settings: Optional[dict] = None
    mask: Optional[bytes] = None
    mask_blur: Optional[int] = None
    inpaint_full_res: Optional[bool] = None
    inpaint_full_res_padding: Optional[int] = None

    # ComfyUI-only workflow selection (safe to ignore for A1111).
    workflow_set: Optional[str] = None
    # Hint for selecting templates inside a workflow set.
    # Allowed values: "scene" | "character".
    workflow_task: Optional[str] = None


@dataclass
class SDResponse:
    """Структура ответа от SD."""
    images: List[bytes]
    original_prompt: str
    translated_prompt: str
    original_negative: Optional[str]
    translated_negative: Optional[str]


class SDRequestLayer:
    """
    Единый слой для всех запросов к Stable Diffusion.
    
    Использование:
        layer = get_sd_layer()
        response = layer.generate(SDRequest(prompt="кот на диване"))
        # response.images содержит сгенерированные изображения
        # response.translated_prompt = "cat on the sofa"
    """
    
    def __init__(self, client: Optional[BaseSdClient] = None):
        self._client = client
        self._translator = get_translator()
    
    @property
    def client(self) -> BaseSdClient:
        """Lazy initialization of SD client."""
        if self._client is None:
            self._client = build_sd_client()
        return self._client
    
    def _translate_prompts(
        self, 
        prompt: str, 
        negative_prompt: Optional[str]
    ) -> tuple[str, str, Optional[str], Optional[str]]:
        """
        Переводит промпты на английский.
        
        Returns:
            (original_prompt, translated_prompt, original_negative, translated_negative)
        """
        translated_prompt, translated_negative = self._translator.translate_prompt_and_negative(
            prompt, negative_prompt
        )
        return prompt, translated_prompt, negative_prompt, translated_negative
    
    def generate(self, request: SDRequest) -> SDResponse:
        """
        Генерирует изображения через SD API.
        
        Автоматически:
        - Переводит промпты на английский
        - Логирует запрос
        - Обрабатывает ошибки
        """
        # Translate prompts
        orig_prompt, trans_prompt, orig_neg, trans_neg = self._translate_prompts(
            request.prompt, request.negative_prompt
        )

        # Ensure deterministic pipeline defaults from profiles if any param is missing
        seed_override = None if request.seed == -1 else request.seed
        if any(
            value is None
            for value in (
                request.steps,
                request.cfg_scale,
                seed_override,
                request.sampler,
                request.scheduler,
                request.model_id,
                request.width,
                request.height,
            )
        ):
            resolver = get_pipeline_resolver()
            resolved = resolver.resolve(
                kind="scene",
                overrides={
                    "width": request.width,
                    "height": request.height,
                    "cfg_scale": request.cfg_scale,
                    "steps": request.steps,
                    "seed": seed_override,
                    "sampler": request.sampler,
                    "scheduler": request.scheduler,
                    "model_id": request.model_id,
                    "vae_id": request.vae_id,
                    "loras": request.loras,
                },
                seed_context=PipelineSeedContext(kind="scene"),
            )
            width = request.width if request.width is not None else resolved.width
            height = request.height if request.height is not None else resolved.height
            cfg_scale = request.cfg_scale if request.cfg_scale is not None else resolved.cfg_scale
            steps = request.steps if request.steps is not None else resolved.steps
            seed = seed_override if seed_override is not None else resolved.seed
            sampler = request.sampler or resolved.sampler
            scheduler = request.scheduler or resolved.scheduler
            model_id = request.model_id or resolved.model_id
            vae_id = request.vae_id or resolved.vae_id
            clip_id = getattr(resolved, 'clip_id', None)
            loader_type = getattr(resolved, 'loader_type', 'standard')
            loras = request.loras if request.loras is not None else [lora.model_dump() for lora in resolved.loras]
        else:
            width = request.width
            height = request.height
            cfg_scale = request.cfg_scale
            steps = request.steps
            seed = seed_override
            sampler = request.sampler
            scheduler = request.scheduler
            model_id = request.model_id
            vae_id = request.vae_id
            clip_id = None
            loader_type = 'standard'
            loras = request.loras

        final_prompt, prompt_loras = extract_lora_tokens(trans_prompt)
        merged_loras = merge_loras(prompt_loras, loras)

        # Normalize "AUTO" / blank checkpoint/vae values so clients can fall back to their defaults.
        def _blank_to_none(value: object) -> Optional[str]:
            if value is None:
                return None
            if isinstance(value, str):
                v = value.strip()
                if not v or v.upper() in {"AUTO", "__AUTO__", "DEFAULT"}:
                    return None
                return v
            return str(value)

        model_id = _blank_to_none(model_id)
        vae_id = _blank_to_none(vae_id)

        # Root cause: GGUF models are not supported by ComfyUI Cloud API
        # Solution: Filter out GGUF models when using cloud API, set to None to use cloud default
        if isinstance(self.client, ComfySdClient) and self.client._is_cloud:
            if isinstance(model_id, str) and model_id.lower().endswith(".gguf"):
                logger.info("Cloud API detected: ignoring GGUF model '%s', will use cloud default", model_id)
                model_id = None
            if isinstance(loader_type, str) and loader_type == "gguf":
                loader_type = "standard"

        # Best-effort safety: skip missing LoRAs (or optional LoRAs) instead of hard-failing generation.
        # This makes shipped presets portable across machines with different model folders.
        if merged_loras:
            try:
                available = self.client.get_loras() or []
                known: set[str] = set()
                for item in available:
                    if isinstance(item, dict):
                        for key in ("name", "model_name", "filename", "file", "path"):
                            raw = item.get(key)
                            if isinstance(raw, str) and raw:
                                known.add(raw)
                                known.add(raw.rsplit("/", 1)[-1])
                                known.add(raw.rsplit("\\", 1)[-1])
                                known.add(raw.rsplit(".", 1)[0])
                if known:
                    filtered: list[dict] = []
                    for lora in merged_loras:
                        if not isinstance(lora, dict):
                            continue
                        name = (lora.get("name") or "").strip()
                        if not name:
                            continue
                        optional = bool(lora.get("optional") or lora.get("is_optional"))
                        # Match either exact names or common basename-without-extension variants.
                        cand = {name, name.rsplit("/", 1)[-1], name.rsplit("\\", 1)[-1], name.rsplit(".", 1)[0]}
                        if cand.intersection(known):
                            filtered.append(lora)
                        else:
                            if not optional:
                                logger.warning("Skipping missing LoRA '%s' (not found in SD options).", name)
                    merged_loras = filtered
            except Exception:
                # Don't block generation when options endpoints are unavailable.
                pass

        # Best-effort safety: if an explicit checkpoint is missing, fall back to server default.
        if model_id:
            try:
                models = self.client.get_sd_models() or []
                known_models: set[str] = set()
                for item in models:
                    if isinstance(item, dict):
                        raw = item.get("model_name") or item.get("title") or item.get("name") or item.get("filename")
                        if isinstance(raw, str) and raw:
                            known_models.add(raw)
                            known_models.add(raw.rsplit("/", 1)[-1])
                            known_models.add(raw.rsplit("\\", 1)[-1])
                    elif isinstance(item, str):
                        known_models.add(item)
                if known_models and model_id not in known_models:
                    logger.warning("Requested checkpoint '%s' not found in SD options. Falling back to default.", model_id)
                    model_id = None
            except Exception:
                pass

        # Log request
        logger.info(
            "SD Request resolved: prompt='%s...' -> '%s...' negative='%s...' -> '%s...' size=%sx%s num=%s "
            "model=%s vae=%s sampler=%s scheduler=%s steps=%s cfg=%s seed=%s loras=%s",
            orig_prompt[:50],
            final_prompt[:50],
            (orig_neg or "")[:50],
            (trans_neg or "")[:50],
            width,
            height,
            request.num_images,
            model_id,
            vae_id,
            sampler,
            scheduler,
            steps,
            cfg_scale,
            seed,
            [lora.get("name") for lora in merged_loras],
        )
        
        # Generate images
        try:
            alwayson_scripts = request.alwayson_scripts
            override_settings = request.override_settings
            if (alwayson_scripts or override_settings) and not self.client.supports("alwayson_scripts"):
                logger.warning("Active SD provider does not support alwayson scripts; disabling extras.")
                alwayson_scripts = None
                override_settings = None
            mask = request.mask
            mask_blur = request.mask_blur
            inpaint_full_res = request.inpaint_full_res
            inpaint_full_res_padding = request.inpaint_full_res_padding
            if (
                mask is not None
                or mask_blur is not None
                or inpaint_full_res is not None
                or inpaint_full_res_padding is not None
            ) and not self.client.supports("inpaint"):
                logger.warning("Active SD provider does not support inpainting; dropping mask parameters.")
                mask = None
                mask_blur = None
                inpaint_full_res = None
                inpaint_full_res_padding = None

            images = self.client.generate_images(
                prompt=final_prompt,
                style=request.style,
                num_images=request.num_images,
                width=width,
                height=height,
                negative_prompt=trans_neg,
                cfg_scale=cfg_scale,
                steps=steps,
                seed=seed,
                sampler=sampler,
                scheduler=scheduler,
                model_id=model_id,
                vae_id=vae_id,
                clip_id=clip_id,
                loader_type=loader_type,
                loras=merged_loras,
                init_images=request.init_images,
                denoising_strength=request.denoising_strength,
                alwayson_scripts=alwayson_scripts,
                override_settings=override_settings,
                mask=mask,
                mask_blur=mask_blur,
                inpaint_full_res=inpaint_full_res,
                inpaint_full_res_padding=inpaint_full_res_padding,
                workflow_set=request.workflow_set,
                workflow_task=request.workflow_task,
            )
        except Exception as e:
            logger.error(f"SD generation failed: {e}")
            raise
        
        logger.info(f"SD Response: generated {len(images)} images")
        
        return SDResponse(
            images=images,
            original_prompt=orig_prompt,
            translated_prompt=trans_prompt,
            original_negative=orig_neg,
            translated_negative=trans_neg,
        )
    
    def generate_simple(
        self,
        prompt: str,
        negative_prompt: Optional[str] = None,
        num_images: int = 1,
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
        init_images: Optional[List[bytes]] = None,
        denoising_strength: Optional[float] = None,
        alwayson_scripts: Optional[dict] = None,
        override_settings: Optional[dict] = None,
        mask: Optional[bytes] = None,
        mask_blur: Optional[int] = None,
        inpaint_full_res: Optional[bool] = None,
        inpaint_full_res_padding: Optional[int] = None,
        workflow_set: Optional[str] = None,
        workflow_task: Optional[str] = None,
    ) -> List[bytes]:
        """
        Упрощённый метод генерации - возвращает только изображения.
        
        Для случаев когда не нужна информация о переводе.
        """
        request = SDRequest(
            prompt=prompt,
            negative_prompt=negative_prompt,
            num_images=num_images,
            width=width,
            height=height,
            style=style,
            cfg_scale=cfg_scale,
            steps=steps,
            seed=seed,
            sampler=sampler,
            scheduler=scheduler,
            model_id=model_id,
            vae_id=vae_id,
            loras=loras,
            init_images=init_images,
            denoising_strength=denoising_strength,
            alwayson_scripts=alwayson_scripts,
            override_settings=override_settings,
            mask=mask,
            mask_blur=mask_blur,
            inpaint_full_res=inpaint_full_res,
            inpaint_full_res_padding=inpaint_full_res_padding,
            workflow_set=workflow_set,
            workflow_task=workflow_task,
        )
        response = self.generate(request)
        return response.images

    def controlnet_detect(
        self,
        module: str,
        images: List[bytes],
        processor_res: int = 512,
        threshold_a: float = 64,
        threshold_b: float = 64,
    ) -> List[bytes]:
        return self.client.controlnet_detect(
            module=module,
            images=images,
            processor_res=processor_res,
            threshold_a=threshold_a,
            threshold_b=threshold_b,
        )

    def get_controlnet_models(self) -> List[str]:
        """Get list of available ControlNet models."""
        return self.client.get_controlnet_models()

    def get_controlnet_modules(self) -> List[str]:
        """Get list of available ControlNet preprocessor modules."""
        return self.client.get_controlnet_modules()

    def find_controlnet_model(self, module_type: str) -> Optional[str]:
        """Find a matching ControlNet model for the given module type."""
        return self.client.find_controlnet_model(module_type)

    def interrogate(self, image: bytes, model: str = "clip") -> dict:
        """Interrogate an image to get a caption/tags."""
        return self.client.interrogate(image=image, model=model)

    def supports(self, feature: str) -> bool:
        """Check if the active SD client supports a feature."""
        return self.client.supports(feature)


# Global instance
_sd_layer: Optional[SDRequestLayer] = None

# Per-request/task overrides (e.g., ComfyUI API vs local).
_sd_provider_override: ContextVar[Optional[str]] = ContextVar("sd_provider_override", default=None)
_sd_comfy_api_key_override: ContextVar[Optional[str]] = ContextVar("sd_comfy_api_key_override", default=None)
_sd_comfy_url_override: ContextVar[Optional[str]] = ContextVar("sd_comfy_url_override", default=None)
_sd_poe_api_key_override: ContextVar[Optional[str]] = ContextVar("sd_poe_api_key_override", default=None)
_sd_poe_url_override: ContextVar[Optional[str]] = ContextVar("sd_poe_url_override", default=None)
_sd_poe_model_override: ContextVar[Optional[str]] = ContextVar("sd_poe_model_override", default=None)


@contextmanager
def sd_provider_context(
    provider: Optional[str] = None,
    *,
    comfy_api_key: Optional[str] = None,
    comfy_url: Optional[str] = None,
    poe_api_key: Optional[str] = None,
    poe_url: Optional[str] = None,
    poe_model: Optional[str] = None,
):
    overrides = SDProviderOverrides(
        provider=provider,
        comfy_api_key=comfy_api_key,
        comfy_url=comfy_url,
        poe_api_key=poe_api_key,
        poe_url=poe_url,
        poe_model=poe_model,
    ).normalized()
    token_provider = _sd_provider_override.set(overrides.provider)
    token_key = _sd_comfy_api_key_override.set(overrides.comfy_api_key)
    token_url = _sd_comfy_url_override.set(overrides.comfy_url)
    token_poe_key = _sd_poe_api_key_override.set(overrides.poe_api_key)
    token_poe_url = _sd_poe_url_override.set(overrides.poe_url)
    token_poe_model = _sd_poe_model_override.set(overrides.poe_model)
    try:
        yield
    finally:
        _sd_provider_override.reset(token_provider)
        _sd_comfy_api_key_override.reset(token_key)
        _sd_comfy_url_override.reset(token_url)
        _sd_poe_api_key_override.reset(token_poe_key)
        _sd_poe_url_override.reset(token_poe_url)
        _sd_poe_model_override.reset(token_poe_model)


def get_sd_layer() -> SDRequestLayer:
    """Get or create SD request layer instance.

    If provider overrides are set via sd_provider_context, a non-cached layer
    is returned so generation can target a specific backend.
    """
    provider = _sd_provider_override.get()
    comfy_api_key = _sd_comfy_api_key_override.get()
    comfy_url = _sd_comfy_url_override.get()
    poe_api_key = _sd_poe_api_key_override.get()
    poe_url = _sd_poe_url_override.get()
    poe_model = _sd_poe_model_override.get()
    if provider or comfy_api_key or comfy_url or poe_api_key or poe_url or poe_model:
        return SDRequestLayer(
            client=build_sd_client(
                provider_override=provider,
                comfy_api_key=comfy_api_key,
                comfy_url_override=comfy_url,
                poe_api_key=poe_api_key,
                poe_url_override=poe_url,
                poe_model_override=poe_model,
            )
        )

    global _sd_layer
    if _sd_layer is None:
        _sd_layer = SDRequestLayer()
    return _sd_layer


def reset_sd_layer() -> None:
    """Reset the global SD layer (useful for testing)."""
    global _sd_layer
    _sd_layer = None
