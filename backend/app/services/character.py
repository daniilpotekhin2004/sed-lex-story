from __future__ import annotations

import asyncio
import base64
import json
import logging
import random
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

import anyio

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.models import CharacterPreset, CharacterType, SceneCharacter, Project, StyleProfile, GenerationJob
from app.domain.character_references import (
    CHARACTER_REFERENCE_SLOTS,
    PORTRAIT_REFERENCE_KINDS,
    BODY_REFERENCE_KINDS,
    DEFAULT_VIEW_SPECIFIC_PROMPTS,
    DEFAULT_VIEW_SPECIFIC_NEGATIVES,
    DEFAULT_SHEET_PROMPT_PREFIX,
    get_reference_slot_by_kind,
    is_portrait_kind,
    is_body_kind,
    get_view_key_for_kind,
    get_preferred_reference_kinds,
    calculate_denoise_strength,
)
from app.infra.comfy_client import ComfySdClient
from app.infra.repositories.character import CharacterPresetRepository, SceneCharacterRepository
from app.infra.sd_request_layer import get_sd_layer
from app.infra.storage import LocalImageStorage
from app.infra.translator import get_translator, translate_prompt
from app.schemas.characters import (
    CharacterPresetCreate,
    CharacterPresetUpdate,
    SceneCharacterCreate,
    SceneCharacterUpdate,
    CharacterRenderRequest,
)
from app.schemas.generation_overrides import GenerationOverrides
from app.services.asset_metadata import (
    build_generated_marker,
    build_uploaded_marker,
    merge_ref_meta,
    upsert_asset_marker,
)
from app.services.asset_uploads import save_uploaded_image
from app.services.prompt_templates import PromptTemplateLibrary
from app.services.prompt_builder import PromptBuilder
from app.services.prompt_builder import PromptBuilder
from app.services.visuals import VisualGenerationService
from app.services.pipeline_profiles import get_pipeline_resolver, PipelineSeedContext
from app.utils.sd_options import extract_sd_option_overrides
from app.utils.sd_tokens import collect_embedding_tokens, collect_lora_tokens, extract_lora_tokens, prepend_tokens

# Root cause: Character reference prompt configuration needs to be loaded from config file
# Solution: Keep config loading logic here, but use domain module for defaults
logger = logging.getLogger(__name__)
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "a", "an", "and", "the", "with", "without", "on", "in", "at", "for", "to", "of", "from", "by",
    "is", "are", "was", "were", "be", "been", "being", "this", "that", "these", "those",
    "person", "people", "solo", "one", "single", "character", "view", "front", "side", "back",
    "full", "body", "portrait", "profile", "close", "up", "centered", "studio", "lighting",
    "clean", "plain", "background", "neutral", "pose", "standing", "sitting", "walking",
}

_CHARACTER_REFERENCE_PROMPTS_CACHE: Optional[dict] = None
_WILDCARD_PATTERN = re.compile(r"\{([^{}]+)\}")


def _load_character_reference_prompt_config() -> dict:
    global _CHARACTER_REFERENCE_PROMPTS_CACHE
    if _CHARACTER_REFERENCE_PROMPTS_CACHE is not None:
        return _CHARACTER_REFERENCE_PROMPTS_CACHE

    settings = get_settings()
    path = getattr(settings, "character_reference_prompts_path", None)
    if path is None:
        _CHARACTER_REFERENCE_PROMPTS_CACHE = {}
        return _CHARACTER_REFERENCE_PROMPTS_CACHE

    try:
        if not path.exists():
            _CHARACTER_REFERENCE_PROMPTS_CACHE = {}
            return _CHARACTER_REFERENCE_PROMPTS_CACHE
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            _CHARACTER_REFERENCE_PROMPTS_CACHE = payload
        else:
            _CHARACTER_REFERENCE_PROMPTS_CACHE = {}
    except Exception as exc:
        logger.warning("Failed to load character reference prompt config %s: %s", path, exc)
        _CHARACTER_REFERENCE_PROMPTS_CACHE = {}

    return _CHARACTER_REFERENCE_PROMPTS_CACHE


def _normalize_wildcard_key(value: str) -> str:
    return value.strip().strip("_").lower()


def _get_wildcards_config() -> tuple[dict[str, list[str]], bool]:
    config = _load_character_reference_prompt_config()
    enabled = config.get("wildcards_enabled", True)
    raw = config.get("wildcards") if isinstance(config, dict) else None
    normalized: dict[str, list[str]] = {}
    if isinstance(raw, dict):
        for key, options in raw.items():
            if key is None:
                continue
            norm_key = _normalize_wildcard_key(str(key))
            if not norm_key:
                continue
            values: list[str] = []
            if isinstance(options, (list, tuple)):
                values = [str(opt).strip() for opt in options if str(opt).strip()]
            elif isinstance(options, str):
                values = [opt.strip() for opt in options.split("|") if opt.strip()]
            if values:
                normalized[norm_key] = values
    return normalized, bool(enabled)


def _merge_reference_slots(config_slots: list[dict]) -> list[dict]:
    """Merge config slots with defaults from domain module."""
    defaults_by_kind = {slot.get("kind"): slot for slot in CHARACTER_REFERENCE_SLOTS if slot.get("kind")}
    merged: list[dict] = []
    seen: set[str] = set()
    for slot in config_slots:
        if not isinstance(slot, dict):
            continue
        kind = slot.get("kind")
        if not isinstance(kind, str) or not kind:
            continue
        base = defaults_by_kind.get(kind, {})
        merged_slot = {**base, **slot}
        merged.append(merged_slot)
        seen.add(kind)
    for kind, base in defaults_by_kind.items():
        if not kind or kind in seen:
            continue
        merged.append(base)
    return merged


def _get_reference_slots() -> list[dict]:
    """Get reference slots from config, merged with defaults."""
    config = _load_character_reference_prompt_config()
    slots = config.get("reference_slots")
    if isinstance(slots, list) and slots:
        return _merge_reference_slots([slot for slot in slots if isinstance(slot, dict)])
    return CHARACTER_REFERENCE_SLOTS


def _get_view_specific_prompts() -> dict:
    config = _load_character_reference_prompt_config()
    overrides = config.get("view_specific_prompts")
    if isinstance(overrides, dict):
        merged = {**DEFAULT_VIEW_SPECIFIC_PROMPTS}
        merged.update({str(k): str(v) for k, v in overrides.items() if k and v is not None})
        return merged
    return DEFAULT_VIEW_SPECIFIC_PROMPTS


def _get_view_specific_negatives() -> dict:
    config = _load_character_reference_prompt_config()
    overrides = config.get("view_specific_negatives")
    if isinstance(overrides, dict):
        merged = {**DEFAULT_VIEW_SPECIFIC_NEGATIVES}
        merged.update({str(k): str(v) for k, v in overrides.items() if k and v is not None})
        return merged
    return DEFAULT_VIEW_SPECIFIC_NEGATIVES


def _get_sheet_prompt_prefix() -> str:
    config = _load_character_reference_prompt_config()
    value = config.get("sheet_prompt_prefix")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return DEFAULT_SHEET_PROMPT_PREFIX


class CharacterService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.preset_repo = CharacterPresetRepository(db)
        self.scene_char_repo = SceneCharacterRepository(db)

    def _mark_generated_ref(self, ref: dict, *, kind: Optional[str] = None) -> dict:
        marked = dict(ref)
        marked["meta"] = merge_ref_meta(
            marked.get("meta") if isinstance(marked.get("meta"), dict) else None,
            build_generated_marker(asset_kind="reference", slot=kind or ref.get("kind")),
        )
        return marked

    def _set_preview_marker(
        self,
        preset: CharacterPreset,
        *,
        marker: dict,
    ) -> None:
        profile = deepcopy(preset.appearance_profile) if isinstance(preset.appearance_profile, dict) else {}
        preset.appearance_profile = upsert_asset_marker(profile, "preview", marker)

    async def upload_reference_image(
        self,
        preset_id: str,
        kind: str,
        *,
        user_id: str,
        image_bytes: bytes,
        filename: str,
        unsafe: bool = False,
        set_as_preview: bool = True,
    ) -> CharacterPreset:
        preset = await self.preset_repo.get_by_id(preset_id)
        if not preset:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character preset not found")
        if preset.author_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        if preset.project_id and preset.source_preset_id and not unsafe:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Imported character is locked. Pass unsafe=true to overwrite.",
            )

        previous_ref = next(
            (
                ref
                for ref in (preset.reference_images or [])
                if isinstance(ref, dict) and ref.get("kind") == kind
            ),
            None,
        )
        previous_url = previous_ref.get("url") if isinstance(previous_ref, dict) else None
        previous_preview_url = preset.preview_image_url
        url = save_uploaded_image("characters", preset.id, kind or "reference", image_bytes)
        item = {
            "id": uuid4().hex,
            "kind": kind,
            "label": get_reference_slot_by_kind(kind).get("label") if get_reference_slot_by_kind(kind) else None,
            "url": url,
            "thumb_url": url,
            "meta": merge_ref_meta(
                None,
                build_uploaded_marker(
                    filename=filename,
                    asset_kind="reference",
                    slot=kind,
                    replaced_url=previous_url,
                ),
            ),
        }
        refs = [
            ref
            for ref in (preset.reference_images or [])
            if isinstance(ref, dict) and ref.get("kind") != kind
        ]
        refs.append(item)
        preset.reference_images = refs
        if set_as_preview:
            preset.preview_image_url = url
            preset.preview_thumbnail_url = url
            self._set_preview_marker(
                preset,
                marker=build_uploaded_marker(
                    filename=filename,
                    asset_kind="preview",
                    slot=kind,
                    replaced_url=previous_preview_url or previous_url,
                ),
            )
        return await self.preset_repo.update(preset)

    async def create_preset(
        self,
        data: CharacterPresetCreate,
        author_id: str
    ) -> CharacterPreset:
        """Создать пресет персонажа."""
        # Проверка уникальности имени для автора
        existing = await self.preset_repo.get_by_name(data.name, author_id, project_id=None)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Character preset with name '{data.name}' already exists"
            )

        # Валидация типа персонажа
        if data.character_type not in [t.value for t in CharacterType]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid character type. Must be one of: {', '.join(t.value for t in CharacterType)}"
            )

        # Конвертация LoRA моделей в JSON
        lora_models = None
        if data.lora_models:
            lora_models = [{"name": lora.name, "weight": lora.weight} for lora in data.lora_models]


        # Anchor token: human-readable unique tag that can be used as SD embedding/LoRA token
        anchor_token = data.anchor_token
        if not anchor_token:
            anchor_token = f"wlchar_{uuid4().hex[:8]}"
        preset = CharacterPreset(
            name=data.name,
            description=data.description,
            character_type=data.character_type,
            appearance_prompt=data.appearance_prompt,
            negative_prompt=data.negative_prompt,
            anchor_token=anchor_token,
            appearance_profile=data.appearance_profile,
            reference_images=data.reference_images,
            lora_models=lora_models,
            embeddings=data.embeddings,
            style_tags=data.style_tags,
            default_pose=data.default_pose,
            voice_profile=data.voice_profile,
            motivation=data.motivation,
            legal_status=data.legal_status,
            competencies=data.competencies,
            relationships=data.relationships,
            artifact_refs=data.artifact_refs,
            is_public=data.is_public,
            author_id=author_id,
            project_id=None,
            source_preset_id=None,
            source_version=None,
            version=1,
        )

        return await self.preset_repo.create(preset)

    async def get_preset(self, preset_id: str, user_id: Optional[str] = None) -> CharacterPreset:
        """Получить пресет по ID."""
        preset = await self.preset_repo.get_by_id(preset_id)
        
        if not preset:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Character preset not found"
            )

        # Проверка доступа (если не публичный и не автор)
        if preset.project_id is None and not preset.is_public and user_id and preset.author_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this character preset"
            )

        return preset

    async def list_presets(
        self,
        user_id: Optional[str] = None,
        only_mine: bool = False,
        only_public: bool = False,
        character_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        project_id: Optional[str] = None,
    ) -> tuple[List[CharacterPreset], int]:
        """Получить список пресетов."""
        skip = (page - 1) * page_size

        if project_id:
            items = await self.preset_repo.list_by_project(project_id, skip, page_size)
            return items, len(items)

        if only_mine and user_id:
            return await self.preset_repo.list_by_author(user_id, skip, page_size)
        elif only_public:
            return await self.preset_repo.list_public(skip, page_size, character_type)
        elif user_id:
            return await self.preset_repo.list_accessible(user_id, skip, page_size)
        else:
            return await self.preset_repo.list_public(skip, page_size, character_type)

    async def update_preset(
        self,
        preset_id: str,
        data: CharacterPresetUpdate,
        user_id: str,
        *,
        unsafe: bool = False,
    ) -> CharacterPreset:
        """Обновить пресет."""
        preset = await self.preset_repo.get_by_id(preset_id)
        
        if not preset:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Character preset not found"
            )

        # Проверка прав (только автор)
        if preset.author_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update this preset"
            )

        if preset.project_id and preset.source_preset_id and not unsafe:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Imported preset is locked. Pass unsafe=true to overwrite.",
            )

        # Обновление полей
        update_data = data.dict(exclude_unset=True)
        
        if "lora_models" in update_data and update_data["lora_models"]:
            update_data["lora_models"] = [
                {"name": lora.name, "weight": lora.weight}
                for lora in update_data["lora_models"]
            ]

        for field, value in update_data.items():
            setattr(preset, field, value)

        if preset.project_id is None:
            preset.version = (preset.version or 1) + 1


        return await self.preset_repo.update(preset)

    async def import_preset(
        self,
        project_id: str,
        preset_id: str,
        user_id: str,
    ) -> CharacterPreset:
        preset = await self.get_preset(preset_id, user_id)
        imported = CharacterPreset(
            name=preset.name,
            description=preset.description,
            character_type=preset.character_type,
            appearance_prompt=preset.appearance_prompt,
            negative_prompt=preset.negative_prompt,
            anchor_token=preset.anchor_token,
            appearance_profile=preset.appearance_profile,
            reference_images=preset.reference_images,
            voice_profile=preset.voice_profile,
            motivation=preset.motivation,
            legal_status=preset.legal_status,
            competencies=preset.competencies,
            relationships=preset.relationships,
            artifact_refs=preset.artifact_refs,
            lora_models=preset.lora_models,
            embeddings=preset.embeddings,
            style_tags=preset.style_tags,
            default_pose=preset.default_pose,
            preview_image_url=preset.preview_image_url,
            preview_thumbnail_url=preset.preview_thumbnail_url,
            is_public=False,
            author_id=preset.author_id,
            project_id=project_id,
            source_preset_id=preset.id,
            source_version=preset.version,
            version=preset.version or 1,
        )
        return await self.preset_repo.create(imported)
    async def generate_preset_sheet(
        self,
        preset_id: str,
        user_id: str,
        *,
        project_id: Optional[str] = None,
        style_profile_id: Optional[str] = None,
        overrides: Optional[GenerationOverrides] = None,
        variants: Optional[int] = None,
        kinds: Optional[list[str]] = None,
        job_id: Optional[str] = None,
    ) -> CharacterPreset:
        """Generate and store a *standard* reference set for a character preset.

        Historically this endpoint produced a single "sheet" image. For consistent reuse inside
        quests/scenes we now generate a fixed set of slots (face/profile/full-body views) and
        store each as a separate reference_images entry.
        """
        reference_slots = _get_reference_slots()
        ordered_kinds = [slot.get("kind") for slot in reference_slots if slot.get("kind")]

        if kinds:
            requested = [str(k).strip() for k in kinds if str(k).strip()]
            allowed = set(ordered_kinds)
            ordered_kinds = [k for k in ordered_kinds if k in requested and k in allowed]
            if not ordered_kinds:
                ordered_kinds = [slot.get("kind") for slot in reference_slots if slot.get("kind")]
        else:
            ordered_kinds = [
                slot.get("kind")
                for slot in reference_slots
                if slot.get("kind") and slot.get("required", True)
            ]
            if not ordered_kinds:
                ordered_kinds = [slot.get("kind") for slot in reference_slots if slot.get("kind")]

        return await self._generate_preset_reference_set(
            preset_id,
            user_id,
            kinds=ordered_kinds,
            project_id=project_id,
            style_profile_id=style_profile_id,
            refresh_seed_base=True,
            overrides=overrides,
            job_id=job_id,
            sheet_mode=True,
        )

    async def generate_preset_representation(
        self,
        preset_id: str,
        payload: CharacterRenderRequest,
        user_id: str,
        *,
        project_id: Optional[str] = None,
        style_profile_id: Optional[str] = None,
        job_id: Optional[str] = None,
    ) -> CharacterPreset:
        """Generate and store a canonical/variant representation for a preset."""
        preset = await self.preset_repo.get_by_id(preset_id)
        if not preset:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character preset not found")

        if preset.author_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update this preset",
            )

        if not getattr(preset, "anchor_token", None):
            preset.anchor_token = f"wlchar_{uuid4().hex[:8]}"

        style_profile = await self._load_style_profile(
            style_profile_id=style_profile_id,
            project_id=project_id or preset.project_id,
        )

        render_profile = self._extract_render_profile(preset)
        width = payload.width if payload.width is not None else self._coerce_int(render_profile.get("width"))
        height = payload.height if payload.height is not None else self._coerce_int(render_profile.get("height"))
        steps = payload.steps if payload.steps is not None else self._coerce_int(render_profile.get("steps"))
        cfg_scale = payload.cfg_scale if payload.cfg_scale is not None else self._coerce_float(render_profile.get("cfg_scale"))
        if style_profile:
            if cfg_scale is None and style_profile.cfg_scale is not None:
                cfg_scale = style_profile.cfg_scale
            if steps is None and style_profile.steps is not None:
                steps = style_profile.steps

        base_parts: list[str] = []
        if preset.name:
            base_parts.append(preset.name)
        if preset.appearance_prompt:
            base_parts.append(preset.appearance_prompt)
        if preset.description:
            base_parts.append(preset.description)
        if preset.style_tags:
            base_parts.extend([str(t) for t in preset.style_tags if t])
        if style_profile and style_profile.base_prompt:
            base_parts.append(style_profile.base_prompt)
        base_prompt = ", ".join([p for p in base_parts if p])

        prompt_base = payload.prompt_override.strip() if payload.prompt_override else base_prompt
        prompt_base = prompt_base or preset.name or "character portrait"

        sd_tokens: list[str] = []
        if preset.anchor_token:
            sd_tokens.append(preset.anchor_token)
        sd_tokens.extend(collect_embedding_tokens(getattr(preset, "embeddings", None)))
        sd_tokens.extend(collect_lora_tokens(getattr(preset, "lora_models", None)))
        if style_profile:
            try:
                sd_tokens.extend(collect_lora_tokens(style_profile.lora_refs))
            except Exception:
                pass

        loras: list[dict] = []
        if preset.lora_models:
            loras.extend(preset.lora_models)
        if style_profile and style_profile.lora_refs:
            loras.extend(style_profile.lora_refs)
        if getattr(payload, "loras", None):
            try:
                loras.extend([dict(l) for l in payload.loras if l])
            except Exception:
                # Payload validation is intentionally permissive; ignore malformed LoRAs.
                pass

        kind = (payload.kind or "variant").strip() or "variant"
        kind_positive, kind_negative = self._kind_constraints(kind)
        prompt = prepend_tokens(
            ", ".join([
                prompt_base,
                *kind_positive,
                "single character, solo, consistent identity, same person",
            ]),
            sd_tokens,
        )

        negative_parts: list[str] = []
        if style_profile and style_profile.negative_prompt:
            negative_parts.append(style_profile.negative_prompt)
        if payload.negative_prompt:
            negative_parts.append(payload.negative_prompt)
        if preset.negative_prompt:
            negative_parts.append(preset.negative_prompt)
        negative_parts.extend(kind_negative)
        negative_parts.append(PromptTemplateLibrary.CHARACTER_NEGATIVE)
        negative = ", ".join([n for n in negative_parts if n]) or None

        generator = VisualGenerationService()
        refs = list(preset.reference_images or [])
        reference_urls, reference_kind = self._pick_reference_selection(
            preset,
            preferred_kinds=self._reference_preferred_kinds(kind),
        )
        denoise_strength = self._reference_denoise_strength(
            preset,
            target_kind=kind,
            reference_kind=reference_kind,
        )

        job: GenerationJob | None = None
        if job_id:
            try:
                job = await self.db.get(GenerationJob, job_id)
            except Exception:
                job = None
        if job:
            job.stage = f"character_render:{kind}"
            job.progress = 0
            if not isinstance(job.results, dict):
                job.results = {"entity_type": "character_preset", "entity_id": preset.id, "items": []}

        if kind == "canonical":
            for ref in refs:
                if isinstance(ref, dict) and ref.get("kind") == "canonical":
                    ref["kind"] = "variant"

        resolver = get_pipeline_resolver()
        sd_layer = get_sd_layer()
        option_overrides = extract_sd_option_overrides(sd_layer.client.get_options())
        sampler_override = (
            payload.sampler
            or (style_profile.sampler if style_profile and style_profile.sampler else None)
            or option_overrides.get("sampler")
        )
        scheduler_override = payload.scheduler or option_overrides.get("scheduler")
        model_override = (
            payload.model_id
            or (style_profile.model_checkpoint if style_profile and style_profile.model_checkpoint else None)
        )
        vae_override = payload.vae_id

        resolved = resolver.resolve(
            kind="character_ref",
            profile_id=payload.pipeline_profile_id,
            profile_version=payload.pipeline_profile_version,
            overrides={
                "width": int(width),
                "height": int(height),
                "cfg_scale": cfg_scale,
                "steps": steps,
                "sampler": sampler_override,
                "scheduler": scheduler_override,
                "model_checkpoint": model_override,
                "vae": vae_override,
                "loras": loras,
                "seed_policy": "random",
            },
            seed_context=PipelineSeedContext(
                kind="character_ref",
                character_id=preset.id,
                slot=kind,
            ),
        )

        created: list[dict] = []
        if payload.seed is None:
            base_seed = resolved.seed
        elif payload.seed == -1:
            base_seed = random.randint(0, 2**32 - 1)
        else:
            base_seed = payload.seed
        total = payload.count or 1
        for idx in range(total):
            seed = base_seed + idx
            url = await generator.generate_preview(
                f"characters/{preset.id}/variants/{kind}",
                prompt,
                negative_prompt=negative,
                width=resolved.width,
                height=resolved.height,
                style=None,
                cfg_scale=resolved.cfg_scale,
                steps=resolved.steps,
                seed=seed,
                sampler=resolved.sampler,
                scheduler=resolved.scheduler,
                model_id=resolved.model_id,
                vae_id=resolved.vae_id,
                loras=[lora.model_dump() for lora in resolved.loras],
                pipeline_profile_id=resolved.profile_id,
                pipeline_profile_version=resolved.profile_version,
                workflow_task="character",
                seed_context=PipelineSeedContext(
                    kind="character_ref",
                    character_id=preset.id,
                    slot=kind,
                    profile_version=resolved.profile_version,
                ),
                reference_images=reference_urls,
                denoising_strength=denoise_strength,
            )
            item = {
                "id": uuid4().hex,
                "kind": kind,
                "label": payload.label,
                "url": url,
                "thumb_url": url,
                "meta": merge_ref_meta(
                    {
                        "created_at": datetime.utcnow().isoformat(),
                        "prompt": prompt_base,
                        "negative_prompt": negative,
                        "width": resolved.width,
                        "height": resolved.height,
                        "cfg_scale": resolved.cfg_scale,
                        "steps": resolved.steps,
                        "seed": seed,
                        "seed_base": base_seed,
                        "sampler": resolved.sampler,
                        "scheduler": resolved.scheduler,
                        "model_id": resolved.model_id,
                        "vae_id": resolved.vae_id,
                        "loras": [lora.model_dump() for lora in resolved.loras],
                        "pipeline_profile_id": resolved.profile_id,
                        "pipeline_profile_version": resolved.profile_version,
                    },
                    build_generated_marker(asset_kind="reference", slot=kind),
                ),
            }
            created.append(item)

            if job:
                job.stage = f"character_render:{kind}:{idx + 1}/{total}"
                job.progress = int(((idx + 1) / max(total, 1)) * 100)
                if isinstance(job.results, dict):
                    job.results["items"] = refs + created

            # Persist progressively so the frontend can poll and display
            # variants immediately as they're generated.
            preset.reference_images = refs + created
            if kind == "canonical" and idx == 0:
                preset.preview_image_url = item.get("url")
                preset.preview_thumbnail_url = item.get("thumb_url") or item.get("url")

            preset = await self.preset_repo.update(preset)

        return preset

    async def regenerate_preset_reference(
        self,
        preset_id: str,
        kind: str,
        user_id: str,
        *,
        project_id: Optional[str] = None,
        style_profile_id: Optional[str] = None,
        overrides: Optional[GenerationOverrides] = None,
        job_id: Optional[str] = None,
    ) -> CharacterPreset:
        """Regenerate a single reference slot (e.g. portrait/full_back) for a preset."""
        allowed = {slot["kind"] for slot in _get_reference_slots()}
        if kind not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported reference kind '{kind}'. Allowed: {', '.join(sorted(allowed))}",
            )

        return await self._generate_preset_reference_set(
            preset_id,
            user_id,
            kinds=[kind],
            project_id=project_id,
            style_profile_id=style_profile_id,
            refresh_seed_base=True,
            overrides=overrides,
            job_id=job_id,
        )

    async def _generate_preset_reference_set(
        self,
        preset_id: str,
        user_id: str,
        *,
        kinds: list[str],
        project_id: Optional[str],
        style_profile_id: Optional[str],
        refresh_seed_base: bool,
        overrides: Optional[GenerationOverrides] = None,
        job_id: Optional[str] = None,
        sheet_mode: bool = False,
    ) -> CharacterPreset:
        preset = await self.preset_repo.get_by_id(preset_id)
        if not preset:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character preset not found")

        if preset.author_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update this preset",
            )

        # Ensure anchor token exists (used as SD-consistency tag)
        if not getattr(preset, "anchor_token", None):
            preset.anchor_token = f"wlchar_{uuid4().hex[:8]}"

        style_profile = await self._load_style_profile(style_profile_id=style_profile_id, project_id=project_id)
        cfg_scale = style_profile.cfg_scale if style_profile and style_profile.cfg_scale is not None else None
        steps = style_profile.steps if style_profile and style_profile.steps is not None else None
        render_params = self._extract_render_params(preset)
        cfg_scale = render_params.get("cfg_scale") or cfg_scale
        steps = render_params.get("steps") or steps
        if overrides:
            if overrides.cfg_scale is not None:
                cfg_scale = overrides.cfg_scale
            if overrides.steps is not None:
                steps = overrides.steps

        refs = preset.reference_images or []
        reference_pool: list[dict] = [r for r in refs if isinstance(r, dict)]

        # Seed strategy:
        # - If we're not refreshing, try to reuse the previous sheet seed_base.
        # - If the caller explicitly sets seed: use it (seed=-1 means "randomize").
        # - Otherwise: use a random base seed for this run.
        seed_base: Optional[int] = None
        if not refresh_seed_base:
            seed_base = self._extract_seed_base(refs)

        if overrides and overrides.seed is not None:
            try:
                forced = int(overrides.seed)
            except Exception:
                forced = None
            if forced is not None and forced >= 0:
                seed_base = forced
            elif forced == -1:
                seed_base = random.randint(0, 2**32 - 1)

        if seed_base is None:
            seed_base = random.randint(0, 2**32 - 1)

        # Build base prompt parts (without view-specific tags)
        base_parts: list[str] = []
        if preset.name:
            base_parts.append(preset.name)
        if preset.appearance_prompt:
            base_parts.append(preset.appearance_prompt)
        if preset.description:
            base_parts.append(preset.description)
        if preset.style_tags:
            base_parts.extend([str(t) for t in preset.style_tags if t])

        # Style profile (project defaults)
        if style_profile and style_profile.base_prompt:
            base_parts.append(style_profile.base_prompt)

        base_prompt = ", ".join([p for p in base_parts if p])

        # SD special tokens (TI/LoRA/anchors)
        sd_tokens: list[str] = []
        if preset.anchor_token:
            sd_tokens.append(preset.anchor_token)
        sd_tokens.extend(collect_embedding_tokens(getattr(preset, "embeddings", None)))
        sd_tokens.extend(collect_lora_tokens(getattr(preset, "lora_models", None)))
        if style_profile:
            try:
                sd_tokens.extend(collect_lora_tokens(style_profile.lora_refs))
            except Exception:
                pass

        templates = PromptTemplateLibrary()
        wildcards, wildcards_enabled = _get_wildcards_config()
        prompt_builder = PromptBuilder(wildcards=wildcards if wildcards_enabled else None)
        generator = VisualGenerationService()
        resolver = get_pipeline_resolver()
        sd_layer = get_sd_layer()
        option_overrides = extract_sd_option_overrides(sd_layer.client.get_options())
        sampler_override = (
            (overrides.sampler if overrides else None)
            or (style_profile.sampler if style_profile and style_profile.sampler else None)
            or option_overrides.get("sampler")
        )
        scheduler_override = (overrides.scheduler if overrides else None) or option_overrides.get("scheduler")
        model_override = (
            (overrides.model_id if overrides else None)
            or (style_profile.model_checkpoint if style_profile and style_profile.model_checkpoint else None)
        )
        vae_override = (overrides.vae_id if overrides else None)
        exclude_kinds: set[str] = set()

        # Build negative prompt
        negative_parts: list[str] = []
        if style_profile and style_profile.negative_prompt:
            negative_parts.append(style_profile.negative_prompt)
        if preset.negative_prompt:
            negative_parts.append(preset.negative_prompt)
        if overrides and overrides.negative_prompt:
            negative_parts.append(overrides.negative_prompt)
        # A reasonable general negative for character refs
        negative_parts.append(templates.CHARACTER_NEGATIVE)
        # Prevent accidental extra characters in the frame
        negative_parts.append("extra people, multiple people, crowd, group, two people, extra person, extra faces, extra body")
        loras: list[dict] = []
        if preset.lora_models:
            loras.extend(preset.lora_models)
        if style_profile and style_profile.lora_refs:
            loras.extend(style_profile.lora_refs)
        if overrides and overrides.loras:
            try:
                loras.extend([dict(l) for l in overrides.loras if l])
            except Exception:
                pass

        # Root cause: Weak prompts don't give model clear indication of angle/pose
        # Solution: Add strong view-specific prompts with weights for each reference type
        view_specific_prompts = _get_view_specific_prompts()
        view_specific_negatives = _get_view_specific_negatives()
        sheet_prompt_prefix = _get_sheet_prompt_prefix()

        # Generate selected slots
        reference_slots = _get_reference_slots()
        slots_by_kind = {slot["kind"]: slot for slot in reference_slots}
        generated: dict[str, dict] = {}

        # Ordered hint lists used for character identity consistency across slots.
        # For A1111/Forge we can use ControlNet/IP-Adapter (alwayson scripts).
        # For ComfyUI we fall back to img2img references (reference_images).
        face_hint_order = [
            "sketch",
            "complex",
            "portrait",
            "profile",
            "face_front",
            "face_profile",
            "face",
            "expression",
            "canonical",
        ]
        body_hint_order = [
            "full_front",
            "full_side",
            "full_back",
            "complex",
            "body",
            "turnaround",
        ]

        def _pick_pool_url(order: list[str]) -> Optional[str]:
            for k in order:
                for ref in reversed(reference_pool):
                    if not isinstance(ref, dict):
                        continue
                    if ref.get("kind") != k:
                        continue
                    url = ref.get("url")
                    if isinstance(url, str) and url:
                        return url
            return None

        sheet_reference_url: Optional[str] = None
        if sheet_mode:
            if isinstance(getattr(preset, "preview_image_url", None), str) and preset.preview_image_url:
                sheet_reference_url = preset.preview_image_url
            else:
                sheet_reference_url = _pick_pool_url(["sketch"])
            if sheet_reference_url:
                has_sketch = any(
                    isinstance(ref, dict)
                    and ref.get("kind") == "sketch"
                    and ref.get("url") == sheet_reference_url
                    for ref in reference_pool
                )
                if not has_sketch:
                    reference_pool.append(
                        {
                            "kind": "sketch",
                            "label": "Sketch",
                            "url": sheet_reference_url,
                            "thumb_url": sheet_reference_url,
                            "meta": {"source": "preview"},
                        }
                    )


        job: GenerationJob | None = None
        if job_id:
            try:
                job = await self.db.get(GenerationJob, job_id)
            except Exception:
                job = None

        # Root cause: Generating all images at once overloads memory and UI crashes
        # Solution: Generate one at a time with save after each
        for idx, kind in enumerate(kinds):
            logger.info(f"[Character Ref] Generating {idx+1}/{len(kinds)}: {kind}")
            slot = slots_by_kind[kind]
            slot_positive, slot_negative = self._kind_constraints(kind)
            preferred_kinds = self._reference_preferred_kinds(kind)
            kind_value = (kind or "").strip().lower()
            local_exclude = set(exclude_kinds)
            allow_preview = kind_value != "profile"
            if kind_value.startswith("pose") or kind_value in BODY_REFERENCE_KINDS:
                preferred_kinds = [value for value in preferred_kinds if value not in PORTRAIT_REFERENCE_KINDS]
                local_exclude.update(PORTRAIT_REFERENCE_KINDS)
                allow_preview = False
            elif kind_value in PORTRAIT_REFERENCE_KINDS:
                preferred_kinds = [value for value in preferred_kinds if value not in BODY_REFERENCE_KINDS]
                local_exclude.update(BODY_REFERENCE_KINDS)
            if not preferred_kinds:
                preferred_kinds = self._reference_preferred_kinds(kind)
            reference_urls, reference_kind = self._pick_reference_selection(
                preset,
                reference_images=reference_pool,
                exclude_kinds=local_exclude,
                preferred_kinds=preferred_kinds,
                allow_preview=allow_preview,
            )

            # If we're generating a full-body slot but we don't yet have a body reference,
            # fall back to a face reference as an identity hint (img2img). This is a pragmatic
            # substitute for IP-Adapter in ComfyUI-only setups.
            if not reference_urls and (kind_value.startswith("pose") or kind_value in BODY_REFERENCE_KINDS):
                fallback_face_url = _pick_pool_url(["portrait", "profile", "canonical"])
                if fallback_face_url:
                    reference_urls = [fallback_face_url]
                    reference_kind = "portrait"
            reference_kind_value = (reference_kind or "").strip().lower()
            if reference_kind_value:
                # Allow cross-kind references within the same category (face↔face, body↔body).
                # This is critical for ComfyUI where we rely on img2img to keep identity consistent.
                target_is_face = kind_value in PORTRAIT_REFERENCE_KINDS
                target_is_body = kind_value in BODY_REFERENCE_KINDS or kind_value.startswith("pose")
                ref_is_face = reference_kind_value in PORTRAIT_REFERENCE_KINDS
                ref_is_body = reference_kind_value in BODY_REFERENCE_KINDS or reference_kind_value.startswith("pose")
                # Only reject cross-category references when a more appropriate reference exists.
                has_face_ref = any(
                    isinstance(r, dict) and (r.get("kind") in PORTRAIT_REFERENCE_KINDS) for r in reference_pool
                )
                has_body_ref = any(
                    isinstance(r, dict)
                    and (
                        (r.get("kind") in BODY_REFERENCE_KINDS)
                        or (isinstance(r.get("kind"), str) and str(r.get("kind")).startswith("pose"))
                    )
                    for r in reference_pool
                )

                reject = False
                if target_is_face and ref_is_body and has_face_ref:
                    reject = True
                if target_is_body and ref_is_face and has_body_ref:
                    reject = True

                if reject:
                    reference_urls = []
                    reference_kind = None

            if sheet_mode and sheet_reference_url:
                reference_urls = [sheet_reference_url]
                reference_kind = "sketch"
            denoise_strength = self._reference_denoise_strength(
                preset,
                target_kind=kind,
                reference_kind=reference_kind,
            )
            slot_negative_parts = negative_parts + slot_negative
            slot_specific_negative = slot.get("negative")
            if isinstance(slot_specific_negative, list):
                slot_negative_parts.extend([str(n) for n in slot_specific_negative if n])
            elif isinstance(slot_specific_negative, str) and slot_specific_negative.strip():
                slot_negative_parts.append(slot_specific_negative.strip())
            slot_negative_prompt = ", ".join([n for n in slot_negative_parts if n]) or None

            slot_width = int(overrides.width) if overrides and overrides.width is not None else int(slot["width"])
            slot_height = int(overrides.height) if overrides and overrides.height is not None else int(slot["height"])
            resolved = resolver.resolve(
                kind="character_ref",
                profile_id=overrides.pipeline_profile_id if overrides else None,
                profile_version=overrides.pipeline_profile_version if overrides else None,
                overrides={
                    "width": slot_width,
                    "height": slot_height,
                    "cfg_scale": cfg_scale,
                    "steps": steps,
                    "sampler": sampler_override,
                    "scheduler": scheduler_override,
                    "model_checkpoint": model_override,
                    "vae": vae_override,
                    "loras": loras,
                    "seed_policy": "random",
                },
                seed_context=PipelineSeedContext(
                    kind="character_ref",
                    character_id=preset.id,
                    slot=kind,
                ),
            )
            
            # Seed policy for consistency within this run:
            # Use a base seed (random unless overridden) and add a small offset per slot.
            # This improves identity consistency compared to hashing the kind (which can drift faces).
            max_seed = 2**32 - 1
            slot_seed = int((seed_base + idx) % max_seed)
            
            # Determine view type for enhanced prompts
            view_key = get_view_key_for_kind(kind)
            
            # Build enhanced prompt with view-specific weights
            # Root cause: Repetitive prompts confuse FLUX Kontext, making all views look similar
            # Solution: Clean, natural language prompts optimized for FLUX understanding
            prompt_parts = []
            
            # 1. View-specific prompt (most important - clear angle instruction)
            if view_key and view_key in view_specific_prompts:
                prompt_parts.append(view_specific_prompts[view_key])
            else:
                # Fallback to slot prompt if no view-specific prompt
                prompt_parts.append(slot["prompt"])
            
            # Enhanced negative prompt with view-specific negatives
            # Root cause: Overly long negative prompts dilute the important negatives
            # Solution: Keep only essential negatives - view-specific and quality
            slot_negative_parts = []
            
            # 1. View-specific negatives (most important)
            if view_key and view_key in view_specific_negatives:
                slot_negative_parts.append(view_specific_negatives[view_key])
            
            # 2. Slot-specific negatives
            slot_specific_negative = slot.get("negative")
            if isinstance(slot_specific_negative, list):
                slot_negative_parts.extend([str(n) for n in slot_specific_negative if n])
            elif isinstance(slot_specific_negative, str) and slot_specific_negative.strip():
                slot_negative_parts.append(slot_specific_negative.strip())
            
            # 3. Essential quality negatives only
            slot_negative_parts.append("blurry, low quality, deformed")
            
            # Skip general negative_parts - too verbose and dilutes view-specific negatives
            
            slot_negative_prompt = ", ".join([n for n in slot_negative_parts if n]) or None
            
            # Root cause: Low CFG and steps result in poor prompt following and quality
            # Solution: Increase CFG to min 9.0 and steps to min 35
            # If the caller explicitly set cfg/steps overrides - respect them.
            # IMPORTANT: do not hard-force very high CFG/steps here.
            # Different model families behave differently (SD 3.x generally prefers lower CFG than SD 1.5).
            # We rely on pipeline profiles + style profiles to define safe defaults.
            enhanced_cfg = (
                overrides.cfg_scale
                if overrides and overrides.cfg_scale is not None
                else (resolved.cfg_scale or 6.0)
            )
            enhanced_steps = (
                overrides.steps
                if overrides and overrides.steps is not None
                else (resolved.steps or 30)
            )
            
            logger.info(f"[Character Ref] {kind} - seed={slot_seed}, cfg={enhanced_cfg}, steps={enhanced_steps}, view={view_key}")
            
            # Do not re-resolve the pipeline here. We intentionally keep a single resolved profile
            # per slot and only adjust CFG/steps via the per-call params below.
            alwayson_scripts = None
            force_sketch_reference = bool(sheet_mode and sheet_reference_url)
            if force_sketch_reference:
                reference_images_for_call = [sheet_reference_url]
                denoise_for_call = denoise_strength
            else:
                reference_images_for_call = reference_urls
                denoise_for_call = denoise_strength
            
            # 2. Base character description (identity) - only for txt2img
            # For img2img, identity comes from reference image
            if not reference_images_for_call:
                prompt_parts.append(base_prompt)
            
            prompt_text = ", ".join([p for p in prompt_parts if p])
            prompt_text = prompt_builder.expand_wildcards(prompt_text)
            prompt = prepend_tokens(prompt_text, sd_tokens)

            # Prefer ControlNet/IP-Adapter when available (A1111/Forge). This yields much more stable
            # identity consistency compared to pure seed-based generation.
            # IMPORTANT: Skip alwayson_scripts for ComfyUI Cloud (cloud_api). Cloud uses FluxKontextPro
            # img2img node and requires reference_images to stay attached.
            is_cloud = bool(getattr(sd_layer.client, "_is_cloud", False))
            use_alwayson = (
                not force_sketch_reference
                and not is_cloud
                and sd_layer.client.supports("alwayson_scripts")
                and reference_pool
                and (resolved.workflow_set or "").strip().lower() != "cloud_api"
            )
            if use_alwayson:
                face_url = _pick_pool_url(face_hint_order)
                body_url = _pick_pool_url(body_hint_order)
                face_bytes = self._load_asset_bytes(face_url) if face_url else None
                body_bytes = self._load_asset_bytes(body_url) if body_url else None
                alwayson_scripts = self._build_controlnet_scripts(
                    face_bytes=face_bytes,
                    body_bytes=body_bytes,
                    pose_bytes=None,
                )
                if alwayson_scripts:
                    # When IP-Adapter is active, prefer txt2img + adapter conditioning.
                    reference_images_for_call = []
                    denoise_for_call = None

            use_existing_sketch = bool(sheet_mode and kind == "sketch" and sheet_reference_url)
            if use_existing_sketch:
                url = sheet_reference_url
            else:
                url = await generator.generate_preview(
                    f"characters/{preset.id}/refs/{kind}",
                    prompt,
                    negative_prompt=slot_negative_prompt,
                    width=resolved.width,
                    height=resolved.height,
                    style=None,
                    cfg_scale=enhanced_cfg,
                    steps=enhanced_steps,
                    seed=slot_seed,
                    sampler=resolved.sampler,
                    scheduler=resolved.scheduler,
                    model_id=resolved.model_id,
                    vae_id=resolved.vae_id,
                    loras=[lora.model_dump() for lora in resolved.loras],
                    pipeline_profile_id=resolved.profile_id,
                    pipeline_profile_version=resolved.profile_version,
                    workflow_task="character",
                    seed_context=PipelineSeedContext(
                        kind="character_ref",
                        character_id=preset.id,
                        slot=kind,
                        profile_version=resolved.profile_version,
                    ),
                    reference_images=reference_images_for_call,
                    denoising_strength=denoise_for_call,
                    alwayson_scripts=alwayson_scripts,
                    force_img2img=bool(reference_images_for_call or denoise_for_call),  # Use img2img when references or denoising specified
                )
            generated[kind] = {
                "kind": kind,
                "label": slot.get("label"),
                "url": url,
                "thumb_url": url,
                "meta": merge_ref_meta(
                    {
                        "label": slot.get("label"),
                        "note": slot.get("note"),
                        "seed": slot_seed,
                        "seed_base": int(seed_base),
                        "width": resolved.width,
                        "height": resolved.height,
                        "cfg_scale": enhanced_cfg,
                        "steps": enhanced_steps,
                        "sampler": resolved.sampler,
                        "scheduler": resolved.scheduler,
                        "model_id": resolved.model_id,
                        "vae_id": resolved.vae_id,
                        "loras": [lora.model_dump() for lora in resolved.loras],
                        "pipeline_profile_id": resolved.profile_id,
                        "pipeline_profile_version": resolved.profile_version,
                        "prompt": prompt,
                        "negative_prompt": slot_negative_prompt,
                        "style_profile_id": getattr(style_profile, "id", None) if style_profile else None,
                        "view_key": view_key,
                    },
                    build_generated_marker(asset_kind="reference", slot=kind),
                ),
            }
            reference_pool.append(generated[kind])
            
            # Save progress after each image to prevent UI crashes
            # Merge back into reference_images incrementally
            kept: list[dict] = []
            for r in refs:
                if not isinstance(r, dict):
                    continue
                rk = r.get("kind")
                if rk in generated:
                    continue
                if rk == "sheet":
                    continue
                kept.append(r)
            
            ordered: list[dict] = []
            for slot_def in reference_slots:
                k = slot_def["kind"]
                replacement = generated.get(k)
                if replacement is not None:
                    ordered.append(replacement)
                    continue
                existing = next((r for r in refs if isinstance(r, dict) and r.get("kind") == k), None)
                if existing is not None:
                    ordered.append(existing)
            
            preset.reference_images = kept + ordered
            
            # Commit after each image
            if job is not None:
                job.stage = f"{kind} ({idx + 1}/{max(len(kinds), 1)})"
                job.progress = int(((idx + 1) / max(len(kinds), 1)) * 100)
                job.results = {
                    "entity_type": "character_preset",
                    "entity_id": preset.id,
                    "items": [r for r in (preset.reference_images or []) if isinstance(r, dict)],
                    "updated_kind": kind,
                }
            await self.preset_repo.update(preset)
            logger.info(f"[Character Ref] Saved {kind}, progress: {idx+1}/{len(kinds)}")
            
            # Small pause between generations for stability
            await asyncio.sleep(0.5)

        # Apply quality gate after all images are generated
        face_ref_key, body_ref_key = await self._apply_reference_quality_gate(
            preset,
            generated,
            base_prompt=base_prompt,
            generator=generator,
        )
        if face_ref_key or body_ref_key:
            profile = preset.appearance_profile if isinstance(preset.appearance_profile, dict) else {}
            identity = self._ensure_profile_path(profile, "visual_profile", "identity")
            if face_ref_key:
                identity["face_ref"] = face_ref_key
            if body_ref_key:
                identity["body_ref"] = body_ref_key
            preset.appearance_profile = profile

        # If preview is missing, use the portrait slot as preview.
        if not getattr(preset, "preview_image_url", None):
            face = next((r for r in preset.reference_images if isinstance(r, dict) and r.get("kind") == "portrait"), None)
            if face and face.get("url"):
                preset.preview_image_url = face.get("url")
                preset.preview_thumbnail_url = face.get("thumb_url") or face.get("url")

        if job is not None:
            job.progress = 100
            job.results = {
                "entity_type": "character_preset",
                "entity_id": preset.id,
                "items": [r for r in (preset.reference_images or []) if isinstance(r, dict)],
            }

        return await self.preset_repo.update(preset)

    def _ensure_profile_path(self, profile: dict, *keys: str) -> dict:
        node = profile
        for key in keys:
            value = node.get(key)
            if not isinstance(value, dict):
                value = {}
                node[key] = value
            node = value
        return node

    def _get_reference_key(self, ref: Optional[dict]) -> Optional[str]:
        if not isinstance(ref, dict):
            return None
        key = ref.get("id") or ref.get("url") or ref.get("thumb_url") or ref.get("thumbnail_url")
        return str(key) if key else None

    def _pick_reference_key_by_kind(self, generated: dict[str, dict], kinds: list[str]) -> Optional[str]:
        for kind in kinds:
            ref = generated.get(kind)
            key = self._get_reference_key(ref)
            if key:
                return key
        return None

    def _tokenize_text(self, text: str) -> set[str]:
        if not text:
            return set()
        cleaned = re.sub(r"<[^>]+>", " ", text.lower())
        tokens = _TOKEN_PATTERN.findall(cleaned)
        result = set()
        for token in tokens:
            if len(token) < 3:
                continue
            if token in _STOPWORDS:
                continue
            if token.startswith(("wlchar", "wlloc")):
                continue
            result.add(token)
        return result

    def _score_overlap(self, expected: set[str], actual: set[str]) -> float:
        if not expected or not actual:
            return 0.0
        return len(expected & actual) / len(expected)

    def _flatten_profile_text(self, value: object) -> list[str]:
        if isinstance(value, dict):
            parts: list[str] = []
            for entry in value.values():
                parts.extend(self._flatten_profile_text(entry))
            return parts
        if isinstance(value, list):
            parts = []
            for entry in value:
                parts.extend(self._flatten_profile_text(entry))
            return parts
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            if text.startswith("/api/assets/") or text.startswith("http"):
                return []
            return [text]
        return []

    def _build_expected_text(self, preset: CharacterPreset, base_prompt: str) -> str:
        parts: list[str] = [base_prompt]
        profile = preset.appearance_profile if isinstance(preset.appearance_profile, dict) else {}
        visual = profile.get("visual_profile") if isinstance(profile.get("visual_profile"), dict) else None
        if visual:
            visual_filtered = {key: value for key, value in visual.items() if key != "identity"}
            parts.extend(self._flatten_profile_text(visual_filtered))
        else:
            parts.extend(self._flatten_profile_text(profile))
        if preset.style_tags:
            parts.extend([str(tag) for tag in preset.style_tags if tag])
        return ", ".join([part for part in parts if part])

    def _load_asset_bytes(self, url: str) -> Optional[bytes]:
        if not url or not url.startswith("/api/assets/"):
            return None
        settings = get_settings()
        rel = url[len("/api/assets/") :]
        path = settings.assets_root_path / rel
        if not path.exists():
            return None
        try:
            return path.read_bytes()
        except OSError:
            return None

    async def _interrogate_image(self, image_bytes: bytes, model: str) -> Optional[str]:
        def _call() -> dict:
            sd_layer = get_sd_layer()
            return sd_layer.interrogate(image=image_bytes, model=model)

        try:
            result = await anyio.to_thread.run_sync(_call)
        except Exception as exc:
            logger.warning(f"Image interrogation failed: {exc}")
            return None

        if isinstance(result, dict):
            caption = result.get("caption") or result.get("description") or result.get("text") or result.get("tags")
            if isinstance(caption, str):
                return caption.strip()
        return None

    async def _build_pose_map(self, image_bytes: bytes) -> Optional[bytes]:
        settings = get_settings()
        if not settings.controlnet_enabled:
            return None
        module = (settings.controlnet_openpose_module or "").strip()
        if not module:
            return None

        def _call() -> list[bytes]:
            sd_layer = get_sd_layer()
            if not sd_layer.client.supports("controlnet_detect"):
                return []
            return sd_layer.controlnet_detect(
                module=module,
                images=[image_bytes],
                processor_res=settings.controlnet_processor_res,
                threshold_a=settings.controlnet_threshold_a,
                threshold_b=settings.controlnet_threshold_b,
            )

        try:
            results = await anyio.to_thread.run_sync(_call)
        except Exception as exc:
            logger.warning(f"OpenPose detection failed: {exc}")
            return None

        if results:
            return results[0]
        return None

    def _build_controlnet_scripts(
        self,
        *,
        face_bytes: Optional[bytes],
        body_bytes: Optional[bytes],
        pose_bytes: Optional[bytes],
    ) -> Optional[dict]:
        settings = get_settings()
        if not settings.controlnet_enabled:
            return None

        sd_layer = get_sd_layer()
        if not sd_layer.client.supports("alwayson_scripts"):
            return None

        args: list[dict] = []

        def _encode(data: bytes) -> str:
            return base64.b64encode(data).decode()

        def _build_unit(image: bytes, module: str, model: str, weight: float, guidance_end: float = 1.0) -> dict:
            return {
                "enabled": True,
                "image": _encode(image),
                "module": module,
                "model": model,
                "weight": weight,
                "guidance_start": 0.0,
                "guidance_end": guidance_end,
                "control_mode": 0,
                "pixel_perfect": True,
            }

        if pose_bytes and settings.character_quality_use_openpose:
            pose_module = (settings.controlnet_openpose_module or "").strip()
            pose_model = (settings.controlnet_openpose_model or "").strip()
            if pose_module:
                if pose_model:
                    pose_model = sd_layer.client.find_controlnet_model(pose_model) or pose_model
                else:
                    pose_model = sd_layer.client.find_controlnet_model(pose_module) or ""
            if pose_module and pose_model:
                unit = _build_unit(pose_bytes, pose_module, pose_model, settings.controlnet_pose_weight, guidance_end=0.7)
                unit["processor_res"] = settings.controlnet_processor_res
                unit["threshold_a"] = settings.controlnet_threshold_a
                unit["threshold_b"] = settings.controlnet_threshold_b
                args.append(unit)

        used_face = False
        used_body = False

        if settings.character_quality_use_ip_adapter:
            if face_bytes:
                face_model = sd_layer.client.find_controlnet_model("ip-adapter-face")
                if face_model:
                    args.append(
                        _build_unit(
                            face_bytes,
                            "ip-adapter-face",
                            face_model,
                            settings.character_quality_face_weight,
                        )
                    )
                    used_face = True
            if body_bytes:
                body_model = sd_layer.client.find_controlnet_model("ip-adapter")
                if body_model:
                    args.append(
                        _build_unit(
                            body_bytes,
                            "ip-adapter",
                            body_model,
                            settings.character_quality_body_weight,
                        )
                    )
                    used_body = True

        ref_module = (settings.controlnet_reference_module or "").strip()
        if ref_module:
            is_reference = ref_module.startswith("reference_")
            ref_model = ""
            if not is_reference:
                ref_model = sd_layer.client.find_controlnet_model(settings.controlnet_reference_model or ref_module) or ""
            if face_bytes and not used_face:
                args.append(
                    _build_unit(
                        face_bytes,
                        ref_module,
                        ref_model or "None",
                        settings.controlnet_reference_weight,
                    )
                )
            if body_bytes and not used_body:
                args.append(
                    _build_unit(
                        body_bytes,
                        ref_module,
                        ref_model or "None",
                        settings.controlnet_reference_weight,
                    )
                )

        if not args:
            return None
        return {"controlnet": {"args": args}}

    def _is_face_kind(self, kind: str) -> bool:
        return kind in {"sketch", "complex", "portrait", "profile", "face_front", "face_profile", "face", "expression"}

    def _is_body_kind(self, kind: str) -> bool:
        return kind in {
            "full_front",
            "full_side",
            "full_back",
            "body",
            "turnaround",
        }

    def _pick_best_reference(self, quality: dict[str, dict], kinds: list[str]) -> Optional[dict]:
        best: Optional[dict] = None
        best_score = -1.0
        for kind in kinds:
            candidate = quality.get(kind)
            if not candidate:
                continue
            score = candidate.get("desc_score") or 0.0
            if score > best_score:
                best_score = score
                best = candidate
        return best

    def _quality_status(
        self,
        kind: str,
        desc_score: float,
        face_score: Optional[float],
        body_score: Optional[float],
        settings,
    ) -> str:
        min_desc = settings.character_quality_min_score
        if self._is_face_kind(kind):
            if face_score is not None and face_score < settings.character_quality_face_min_score:
                return "low"
            if desc_score < min_desc:
                return "low"
            return "ok"
        if self._is_body_kind(kind):
            if body_score is not None and body_score < settings.character_quality_body_min_score:
                return "low"
            if desc_score < min_desc:
                return "low"
            return "ok"
        return "ok" if desc_score >= min_desc else "low"

    def _apply_quality_scores(
        self,
        quality: dict[str, dict],
        face_tokens: Optional[set[str]],
        body_tokens: Optional[set[str]],
        *,
        attempt: int,
    ) -> None:
        settings = get_settings()
        for kind, data in quality.items():
            tokens = data.get("tokens") or set()
            desc_score = float(data.get("desc_score") or 0.0)
            face_score = self._score_overlap(face_tokens, tokens) if face_tokens else None
            body_score = self._score_overlap(body_tokens, tokens) if body_tokens else None
            overall = desc_score
            if face_score is not None:
                overall = max(overall, face_score * 0.5 + desc_score * 0.5)
            if body_score is not None:
                overall = max(overall, body_score * 0.5 + desc_score * 0.5)

            status = self._quality_status(kind, desc_score, face_score, body_score, settings)
            data["status"] = status
            ref = data.get("ref")
            if isinstance(ref, dict):
                meta = ref.get("meta")
                if not isinstance(meta, dict):
                    meta = {}
                    ref["meta"] = meta
                quality_meta = {
                    "desc_score": round(desc_score, 3),
                    "face_score": round(face_score, 3) if face_score is not None else None,
                    "body_score": round(body_score, 3) if body_score is not None else None,
                    "overall": round(overall, 3),
                    "status": status,
                    "attempt": attempt,
                }
                if data.get("caption"):
                    meta["caption"] = data.get("caption")
                meta["quality"] = quality_meta

    async def _apply_reference_quality_gate(
        self,
        preset: CharacterPreset,
        generated: dict[str, dict],
        *,
        base_prompt: str,
        generator: VisualGenerationService,
    ) -> tuple[Optional[str], Optional[str]]:
        settings = get_settings()

        face_ref_key = self._pick_reference_key_by_kind(
            generated,
            ["sketch", "complex", "portrait", "profile", "face_front", "face_profile"],
        )
        body_ref_key = self._pick_reference_key_by_kind(
            generated,
            ["full_front", "full_side", "full_back"],
        )

        if not settings.character_quality_enabled:
            return face_ref_key, body_ref_key

        expected_text = self._build_expected_text(preset, base_prompt)
        expected_tokens = self._tokenize_text(translate_prompt(expected_text))
        if not expected_tokens:
            return face_ref_key, body_ref_key

        quality: dict[str, dict] = {}
        for kind, ref in generated.items():
            url = ref.get("url") if isinstance(ref, dict) else None
            if not url:
                continue
            image_bytes = self._load_asset_bytes(str(url))
            if not image_bytes:
                continue
            caption = await self._interrogate_image(image_bytes, settings.character_quality_interrogate_model)
            tokens = self._tokenize_text(caption or "")
            desc_score = self._score_overlap(expected_tokens, tokens)
            quality[kind] = {
                "ref": ref,
                "bytes": image_bytes,
                "caption": caption,
                "tokens": tokens,
                "desc_score": desc_score,
            }

        if not quality:
            return face_ref_key, body_ref_key
        if not any(data.get("caption") for data in quality.values()):
            return face_ref_key, body_ref_key

        face_pick = self._pick_best_reference(quality, ["sketch", "complex", "portrait", "profile", "face_front", "face_profile"])
        body_pick = self._pick_best_reference(
            quality,
            ["full_front", "full_side", "full_back"],
        )

        face_tokens = face_pick.get("tokens") if face_pick else None
        body_tokens = body_pick.get("tokens") if body_pick else None
        face_bytes = face_pick.get("bytes") if face_pick else None
        body_bytes = body_pick.get("bytes") if body_pick else None
        if face_pick:
            face_ref_key = self._get_reference_key(face_pick.get("ref")) or face_ref_key
        if body_pick:
            body_ref_key = self._get_reference_key(body_pick.get("ref")) or body_ref_key

        self._apply_quality_scores(
            quality,
            face_tokens if isinstance(face_tokens, set) else None,
            body_tokens if isinstance(body_tokens, set) else None,
            attempt=0,
        )

        max_attempts = max(0, int(settings.character_quality_max_attempts))
        # Cloud API calls are paid and can be rate-limited; avoid automatic quality re-render loops there.
        try:
            is_cloud = bool(getattr(get_sd_layer().client, "_is_cloud", False))
        except Exception:
            is_cloud = False
        if is_cloud:
            max_attempts = 0
        for attempt in range(max_attempts):
            low_kinds = [kind for kind, data in quality.items() if data.get("status") == "low"]
            if not low_kinds:
                break

            for kind in low_kinds:
                data = quality.get(kind)
                if not data:
                    continue
                ref = data.get("ref")
                if not isinstance(ref, dict):
                    continue
                meta = ref.get("meta") if isinstance(ref.get("meta"), dict) else {}
                prompt = meta.get("prompt") or base_prompt
                negative = meta.get("negative_prompt")
                width = int(meta.get("width") or 512)
                height = int(meta.get("height") or 512)
                cfg_scale = meta.get("cfg_scale")
                steps = meta.get("steps")
                seed = meta.get("seed")
                sampler = meta.get("sampler")
                scheduler = meta.get("scheduler")
                model_id = meta.get("model_id")
                vae_id = meta.get("vae_id")
                loras = meta.get("loras")
                profile_id = meta.get("pipeline_profile_id")
                profile_version = meta.get("pipeline_profile_version")

                pose_bytes = None
                if settings.character_quality_use_openpose and self._is_body_kind(kind):
                    if data.get("bytes"):
                        pose_bytes = await self._build_pose_map(data.get("bytes"))

                scripts = self._build_controlnet_scripts(
                    face_bytes=face_bytes if isinstance(face_bytes, bytes) else None,
                    body_bytes=body_bytes if isinstance(body_bytes, bytes) else None,
                    pose_bytes=pose_bytes,
                )

                url = await generator.generate_preview(
                    f"characters/{preset.id}/refs/{kind}",
                    str(prompt),
                    negative_prompt=str(negative) if negative else None,
                    width=width,
                    height=height,
                    style=None,
                    cfg_scale=cfg_scale,
                    steps=steps,
                    seed=seed,
                    sampler=sampler,
                    scheduler=scheduler,
                    model_id=model_id,
                    vae_id=vae_id,
                    loras=loras if isinstance(loras, list) else None,
                    pipeline_profile_id=profile_id,
                    pipeline_profile_version=profile_version,
                    workflow_task="character",
                    seed_context=PipelineSeedContext(
                        kind="character_ref",
                        character_id=preset.id,
                        slot=kind,
                        profile_version=profile_version,
                    ),
                    init_images=[data.get("bytes")] if data.get("bytes") else None,
                    denoising_strength=settings.character_quality_denoise,
                    alwayson_scripts=scripts,
                    force_img2img=True,  # Explicitly use img2img for character reference refinement
                )
                ref["url"] = url
                ref["thumb_url"] = url

                new_bytes = self._load_asset_bytes(url)
                data["bytes"] = new_bytes
                caption = None
                tokens = set()
                desc_score = 0.0
                if new_bytes:
                    caption = await self._interrogate_image(new_bytes, settings.character_quality_interrogate_model)
                    tokens = self._tokenize_text(caption or "")
                    desc_score = self._score_overlap(expected_tokens, tokens)
                data["caption"] = caption
                data["tokens"] = tokens
                data["desc_score"] = desc_score

            face_pick = self._pick_best_reference(quality, ["sketch", "complex", "portrait", "profile", "face_front", "face_profile"])
            body_pick = self._pick_best_reference(
                quality,
                ["full_front", "full_side", "full_back"],
            )
            if face_pick:
                face_tokens = face_pick.get("tokens")
                face_bytes = face_pick.get("bytes")
                face_ref_key = self._get_reference_key(face_pick.get("ref")) or face_ref_key
            if body_pick:
                body_tokens = body_pick.get("tokens")
                body_bytes = body_pick.get("bytes")
                body_ref_key = self._get_reference_key(body_pick.get("ref")) or body_ref_key

            self._apply_quality_scores(
                quality,
                face_tokens if isinstance(face_tokens, set) else None,
                body_tokens if isinstance(body_tokens, set) else None,
                attempt=attempt + 1,
            )

        return face_ref_key, body_ref_key

    async def _load_style_profile(
        self,
        *,
        style_profile_id: Optional[str],
        project_id: Optional[str],
    ) -> Optional[StyleProfile]:
        if style_profile_id:
            return await self.db.get(StyleProfile, style_profile_id)
        if not project_id:
            return None
        project = await self.db.get(Project, project_id)
        if project and getattr(project, "style_profile_id", None):
            style = await self.db.get(StyleProfile, project.style_profile_id)
            if style is not None:
                return style
        result = await self.db.execute(
            select(StyleProfile).where(StyleProfile.project_id == project_id).limit(1)
        )
        return result.scalar_one_or_none()

    def _extract_seed_base(self, refs: list) -> Optional[int]:
        for r in refs or []:
            if not isinstance(r, dict):
                continue
            meta = r.get("meta") or {}
            if isinstance(meta, dict) and meta.get("seed_base") is not None:
                try:
                    return int(meta.get("seed_base"))
                except Exception:
                    continue
        return None

    def _pick_reference_selection(
        self,
        preset: CharacterPreset,
        *,
        reference_images: Optional[list] = None,
        max_count: int = 1,
        exclude_kinds: Optional[set[str]] = None,
        preferred_kinds: Optional[list[str]] = None,
        allow_preview: bool = True,
    ) -> tuple[list[str], Optional[str]]:
        source = reference_images if reference_images is not None else (preset.reference_images or [])
        def _is_visual_ref(item: dict) -> bool:
            url = item.get("url")
            if not isinstance(url, str) or not url:
                return False

            kind_val = item.get("kind")
            if isinstance(kind_val, str) and kind_val.lower() in {"voice_sample", "audio", "music"}:
                return False

            ct = item.get("content_type")
            if isinstance(ct, str) and ct.lower().startswith("audio/"):
                return False

            # If the URL has an obvious audio extension, skip it.
            url_lower = url.split("?", 1)[0].lower()
            if url_lower.endswith((".wav", ".mp3", ".ogg", ".opus", ".flac")):
                return False

            return True

        refs = [r for r in source if isinstance(r, dict) and _is_visual_ref(r)]
        if not refs and getattr(preset, "preview_image_url", None) and allow_preview:
            return [preset.preview_image_url], None

        exclude_kinds = exclude_kinds or set()
        preferred_kinds = preferred_kinds or [
            "canonical",
            "portrait",
            "profile",
            "full_front",
            "full_side",
            "full_back",
        ]
        picked: list[str] = []
        picked_kind: Optional[str] = None
        for kind in preferred_kinds:
            match = next(
                (r for r in refs if r.get("kind") == kind and kind not in exclude_kinds),
                None,
            )
            if match and match.get("url"):
                picked.append(str(match.get("url")))
                picked_kind = kind
                break

        if not picked:
            for ref in refs:
                if ref.get("kind") in exclude_kinds:
                    continue
                url = ref.get("url")
                if isinstance(url, str):
                    picked.append(url)
                    picked_kind = ref.get("kind") if isinstance(ref.get("kind"), str) else None
                    break

        if not picked and getattr(preset, "preview_image_url", None) and allow_preview:
            picked.append(preset.preview_image_url)

        unique: list[str] = []
        for url in picked:
            if url and url not in unique:
                unique.append(url)
        return unique[:max_count], picked_kind

    def _reference_preferred_kinds(self, target_kind: Optional[str]) -> list[str]:
        kind = (target_kind or "").strip().lower()
        if kind.startswith("pose"):
            preferred = [
                "full_front",
                "full_side",
                "full_back",
                "turnaround",
                "body",
                "sketch",
                "complex",
                "canonical",
                "portrait",
                "profile",
            ]
        elif kind in {"full_front", "full_side", "full_back", "body", "turnaround"}:
            preferred = [
                "full_front",
                "full_side",
                "full_back",
                "turnaround",
                "body",
                "sketch",
                "complex",
                "canonical",
                "portrait",
                "profile",
            ]
        elif kind in {"portrait", "profile", "face", "expression", "sketch", "complex"}:
            preferred = [
                "sketch",
                "complex",
                "portrait",
                "profile",
                "face",
                "canonical",
                "full_front",
                "full_side",
                "full_back",
            ]
        elif kind == "canonical":
            preferred = [
                "sketch",
                "complex",
                "canonical",
                "portrait",
                "profile",
                "full_front",
                "full_side",
                "full_back",
            ]
        else:
            preferred = [
                "canonical",
                "portrait",
                "profile",
                "full_front",
                "full_side",
                "full_back",
            ]

        if kind and kind in preferred:
            preferred = [kind] + [value for value in preferred if value != kind]
        return preferred

    def _kind_constraints(self, kind: Optional[str]) -> tuple[list[str], list[str]]:
        kind_value = (kind or "").strip().lower()
        full_body = {
            "full_front",
            "full_side",
            "full_back",
            "body",
            "turnaround",
        }
        portrait = {"portrait", "profile", "face", "expression", "sketch", "complex"}
        if kind_value.startswith("pose"):
            return (
                ["full body", "head to toe", "full length", "feet visible", "wide framing", "no crop"],
                ["portrait", "close-up", "headshot", "upper body", "waist-up", "cropped", "out of frame"],
            )
        if kind_value in full_body:
            return (
                ["full body", "head to toe", "full length", "feet visible", "wide framing", "no crop"],
                ["portrait", "close-up", "headshot", "upper body", "waist-up", "cropped", "out of frame"],
            )
        if kind_value in portrait:
            return (
                ["portrait close-up", "head and shoulders", "face focus", "tight framing"],
                ["full body", "full length", "head to toe", "feet visible"],
            )
        return ([], [])

    def _reference_denoise_strength(
        self,
        preset: CharacterPreset,
        *,
        target_kind: Optional[str] = None,
        reference_kind: Optional[str] = None,
    ) -> Optional[float]:
        profile = preset.appearance_profile if isinstance(preset.appearance_profile, dict) else {}
        visual = profile.get("visual_profile") if isinstance(profile.get("visual_profile"), dict) else {}
        identity = visual.get("identity") if isinstance(visual.get("identity"), dict) else {}
        lock_strength = identity.get("lock_strength")
        if isinstance(lock_strength, (int, float)):
            value = 1 - float(lock_strength)
            base = max(0.35, min(0.85, round(value, 2)))
        else:
            base = 0.5

        target_raw = (target_kind or "").strip().lower()
        reference_raw = (reference_kind or "").strip().lower()
        target = target_raw
        reference = reference_raw
        full_body = {"full_front", "full_side", "full_back", "body", "turnaround"}
        portrait = {"sketch", "complex", "portrait", "profile", "face", "expression"}
        if target.startswith("pose"):
            target = "body"
        if reference.startswith("pose"):
            reference = "body"

        same_category = (
            (target in full_body and reference in full_body)
            or (target in portrait and reference in portrait)
        )
        if same_category:
            if target_raw and reference_raw and target_raw != reference_raw:
                return min(0.85, round(base + 0.1, 2))
            return max(0.35, min(0.6, round(base - 0.08, 2)))
        if target in full_body and reference in portrait:
            return min(0.85, round(base + 0.15, 2))
        if target in portrait and reference in full_body:
            return min(0.85, round(base + 0.1, 2))
        return base

    def _extract_render_profile(self, preset: CharacterPreset) -> dict:
        profile = preset.appearance_profile
        if not isinstance(profile, dict):
            return {}
        visual = profile.get("visual_profile")
        if isinstance(visual, dict) and isinstance(visual.get("render"), dict):
            return visual.get("render") or {}
        render = profile.get("render")
        if isinstance(render, dict):
            return render
        return {}

    def _coerce_int(self, value: object) -> Optional[int]:
        try:
            if value is None:
                return None
            return int(value)
        except Exception:
            return None

    def _coerce_float(self, value: object) -> Optional[float]:
        try:
            if value is None:
                return None
            return float(value)
        except Exception:
            return None

    def _sanitize_dim(self, value: object, default: int) -> int:
        dim = self._coerce_int(value)
        if dim is None or dim < 256 or dim > 2048:
            return default
        return dim

    def _extract_render_params(self, preset: CharacterPreset) -> dict:
        render = self._extract_render_profile(preset)
        return {
            "width": self._sanitize_dim(render.get("width"), 512),
            "height": self._sanitize_dim(render.get("height"), 640),
            "steps": self._coerce_int(render.get("steps")),
            "cfg_scale": self._coerce_float(render.get("cfg_scale")),
        }


    async def delete_preset(self, preset_id: str, user_id: str) -> None:
        """Удалить пресет."""
        preset = await self.preset_repo.get_by_id(preset_id)
        
        if not preset:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Character preset not found"
            )

        # Проверка прав (только автор)
        if preset.author_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to delete this preset"
            )

        await self.preset_repo.delete(preset)

    async def add_character_to_scene(
        self,
        scene_id: str,
        data: SceneCharacterCreate,
        user_id: str
    ) -> SceneCharacter:
        """Добавить персонажа к сцене."""
        # Проверка доступа к пресету
        preset = await self.get_preset(data.character_preset_id, user_id)

        # Создание связи
        scene_character = SceneCharacter(
            scene_id=scene_id,
            character_preset_id=data.character_preset_id,
            scene_context=data.scene_context,
            position=data.position,
            importance=data.importance,
        )

        result = await self.scene_char_repo.create(scene_character)
        
        # Увеличить счетчик использования
        await self.preset_repo.increment_usage(data.character_preset_id)
        
        return result

    async def get_scene_characters(self, scene_id: str) -> List[SceneCharacter]:
        """Получить всех персонажей сцены."""
        return await self.scene_char_repo.list_by_scene(scene_id)

    async def update_scene_character(
        self,
        scene_character_id: str,
        data: SceneCharacterUpdate,
        user_id: str
    ) -> SceneCharacter:
        """Обновить персонажа в сцене."""
        scene_char = await self.scene_char_repo.get_by_id(scene_character_id)
        
        if not scene_char:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Scene character not found"
            )

        # Обновление полей
        update_data = data.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(scene_char, field, value)

        return await self.scene_char_repo.update(scene_char)

    async def remove_character_from_scene(
        self,
        scene_character_id: str,
        user_id: str
    ) -> None:
        """Удалить персонажа из сцены."""
        scene_char = await self.scene_char_repo.get_by_id(scene_character_id)
        
        if not scene_char:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Scene character not found"
            )

        await self.scene_char_repo.delete(scene_char)

    async def generate_combined_prompt(
        self,
        scene_prompt: str,
        character_ids: List[str],
        user_id: str
    ) -> dict:
        """
        Сгенерировать комбинированный промпт для нескольких персонажей.
        
        Returns:
            dict: {
                "prompt": str,
                "negative_prompt": str,
                "lora_models": list,
                "embeddings": list
            }
        """
        all_loras = []
        all_embeddings = []
        all_negative_prompts = []
        character_prompts = []

        for char_id in character_ids:
            preset = await self.get_preset(char_id, user_id)
            char_data = preset.to_sd_prompt()
            
            character_prompts.append(char_data["prompt"])
            
            if char_data["negative_prompt"]:
                all_negative_prompts.append(char_data["negative_prompt"])
            
            if char_data["lora_models"]:
                all_loras.extend(char_data["lora_models"])
            
            if char_data["embeddings"]:
                all_embeddings.extend(char_data["embeddings"])

        # Объединение промптов
        combined_prompt = f"{scene_prompt}, " + ", ".join(character_prompts)
        combined_negative = ", ".join(all_negative_prompts)

        # Удаление дубликатов LoRA и embeddings
        unique_loras = {lora["name"]: lora for lora in all_loras}.values()
        unique_embeddings = list(set(all_embeddings))

        return {
            "prompt": combined_prompt,
            "negative_prompt": combined_negative,
            "lora_models": list(unique_loras),
            "embeddings": unique_embeddings,
        }

    async def generate_preset_sketch(
        self,
        preset_id: str,
        user_id: str,
        *,
        overrides: Optional[GenerationOverrides] = None,
        job_id: Optional[str] = None,
    ) -> CharacterPreset:
        """Generate and store a preview image for a character preset."""
        preset = await self.preset_repo.get_by_id(preset_id)
        if not preset:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Character preset not found",
            )

        if preset.author_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update this preset",
            )

        job: GenerationJob | None = None
        if job_id:
            try:
                job = await self.db.get(GenerationJob, job_id)
            except Exception:
                job = None
            if job:
                job.stage = "character_sketch"
                job.progress = 0

        render_params = self._extract_render_params(preset)
        width = render_params.get("width")
        height = render_params.get("height")
        cfg_scale = render_params.get("cfg_scale")
        steps = render_params.get("steps")
        if overrides:
            if overrides.width:
                width = overrides.width
            if overrides.height:
                height = overrides.height
            if overrides.cfg_scale is not None:
                cfg_scale = overrides.cfg_scale
            if overrides.steps is not None:
                steps = overrides.steps

        prompt_data = preset.to_sd_prompt()
        base_prompt_raw = prompt_data["prompt"]
        
        # Log what we got from the preset
        logger.info(f"Character preset prompt (length={len(base_prompt_raw)}): {base_prompt_raw[:300]}...")
        
        kind_positive, kind_negative = self._kind_constraints("portrait")
        prompt_raw = ", ".join(
            [
                "portrait close-up, 85mm lens, studio lighting",
                *kind_positive,
                base_prompt_raw,
            ]
        )
        negative_parts = [prompt_data.get("negative_prompt"), *kind_negative, PromptTemplateLibrary.CHARACTER_NEGATIVE]
        negative_raw = ", ".join([n for n in negative_parts if n]) or PromptTemplateLibrary.CHARACTER_NEGATIVE
        sd_layer = get_sd_layer()
        is_comfy = isinstance(sd_layer.client, ComfySdClient)
        base_prompt = base_prompt_raw
        prompt_comfy = prompt_raw
        negative_comfy = negative_raw
        if is_comfy:
            translator = get_translator()
            base_prompt_clean, _ = extract_lora_tokens(base_prompt_raw)
            base_prompt = translator.translate(base_prompt_clean)
            prompt_comfy = ", ".join(
                [
                    "portrait close-up, 85mm lens, studio lighting",
                    *kind_positive,
                    base_prompt,
                ]
            )
            negative_clean, _ = extract_lora_tokens(negative_raw)
            negative_comfy = (
                translator.translate(negative_clean) if negative_clean else PromptTemplateLibrary.CHARACTER_NEGATIVE
            )

        generator = VisualGenerationService()
        resolver = get_pipeline_resolver()
        settings = get_settings()
        option_overrides = extract_sd_option_overrides(sd_layer.client.get_options())
        loras: list[dict] = []
        if preset.lora_models:
            loras.extend(preset.lora_models)
        if overrides and overrides.loras:
            try:
                loras.extend([dict(item) for item in overrides.loras if item])
            except Exception:
                pass
        resolved = resolver.resolve(
            kind="character_ref",
            profile_id=overrides.pipeline_profile_id if overrides else None,
            profile_version=overrides.pipeline_profile_version if overrides else None,
            overrides={
                "width": width,
                "height": height,
                "cfg_scale": cfg_scale,
                "steps": steps,
                "sampler": (overrides.sampler if overrides else None) or option_overrides.get("sampler"),
                "scheduler": (overrides.scheduler if overrides else None) or option_overrides.get("scheduler"),
                "model_checkpoint": (overrides.model_id if overrides else None),
                "vae": (overrides.vae_id if overrides else None),
                "loras": loras,
                "seed_policy": "random",
            },
            seed_context=PipelineSeedContext(
                kind="character_ref",
                character_id=preset.id,
                slot="portrait",
            ),
        )
        reference_urls, reference_kind = self._pick_reference_selection(
            preset,
            preferred_kinds=self._reference_preferred_kinds("portrait"),
        )
        denoise_strength = self._reference_denoise_strength(
            preset,
            target_kind="portrait",
            reference_kind=reference_kind,
        )
        preview_url: Optional[str] = None
        created_refs: list[dict] = []

        if is_comfy:
            try:
                generate_reference_images = settings.character_reference_multiview_enabled
                if overrides and overrides.generate_reference_images is not None:
                    generate_reference_images = overrides.generate_reference_images
                preview_url, created_refs = await self._generate_comfy_sketch_with_multiview(
                    client=sd_layer.client,
                    preset=preset,
                    prompt=prompt_comfy,
                    negative_prompt=negative_comfy,
                    base_prompt=base_prompt,
                    width=resolved.width,
                    height=resolved.height,
                    steps=resolved.steps,
                    cfg_scale=resolved.cfg_scale,
                    seed=resolved.seed,
                    sampler=resolved.sampler,
                    scheduler=resolved.scheduler,
                    model_id=resolved.model_id,
                    vae_id=resolved.vae_id,
                    clip_id=getattr(resolved, 'clip_id', None),
                    loader_type=getattr(resolved, 'loader_type', 'standard'),
                    loras=[lora.model_dump() for lora in resolved.loras],
                    workflow_set=resolved.workflow_set,
                    generate_reference_images=bool(generate_reference_images),
                )
            except Exception as exc:
                logger.warning("Comfy sketch workflow failed; falling back to default preview: %s", exc)
                preview_url = None

        if preview_url is None:
            preview_url = await generator.generate_preview(
                f"characters/{preset.id}",
                prompt_raw,
                negative_prompt=negative_raw,
                width=resolved.width,
                height=resolved.height,
                style=None,
                cfg_scale=resolved.cfg_scale,
                steps=resolved.steps,
                seed=resolved.seed,
                sampler=resolved.sampler,
                scheduler=resolved.scheduler,
                model_id=resolved.model_id,
                vae_id=resolved.vae_id,
                loras=[lora.model_dump() for lora in resolved.loras],
                pipeline_profile_id=resolved.profile_id,
                pipeline_profile_version=resolved.profile_version,
                workflow_task="character",
                seed_context=PipelineSeedContext(
                    kind="character_ref",
                    character_id=preset.id,
                    slot="portrait",
                    profile_version=resolved.profile_version,
                ),
                reference_images=reference_urls,
                denoising_strength=denoise_strength,
                use_option_overrides=False,
            )

        if created_refs:
            existing_refs = [r for r in (preset.reference_images or []) if isinstance(r, dict)]
            replace_kinds = {ref.get("kind") for ref in created_refs if isinstance(ref, dict)}
            kept = [r for r in existing_refs if r.get("kind") not in replace_kinds]
            preset.reference_images = kept + [self._mark_generated_ref(ref) for ref in created_refs]

        preset.preview_image_url = preview_url
        preset.preview_thumbnail_url = preview_url
        self._set_preview_marker(
            preset,
            marker=build_generated_marker(asset_kind="preview", slot="portrait"),
        )

        if job:
            job.progress = 100
            job.stage = "done"
            job.results = {
                "entity_type": "character_preset",
                "entity_id": preset.id,
                "preview_image_url": preview_url,
                "preview_thumbnail_url": preview_url,
                "reference_images": preset.reference_images,
            }
        return await self.preset_repo.update(preset)

    def _apply_comfy_prompt_inputs(
        self,
        workflow: dict,
        *,
        prompt: str,
        negative_prompt: Optional[str],
        width: int,
        height: int,
        steps: Optional[int],
        cfg_scale: Optional[float],
        seed: Optional[int],
        sampler: Optional[str],
        scheduler: Optional[str],
        batch_size: int = 1,
    ) -> None:
        def _set_text(node: dict, value: str) -> None:
            inputs = node.setdefault("inputs", {})
            if "text" in inputs:
                inputs["text"] = value
            elif "prompt" in inputs:
                inputs["prompt"] = value
            else:
                inputs["text"] = value

        encode_nodes = []
        for node_id in sorted(
            workflow.keys(), key=lambda value: int(value) if str(value).isdigit() else str(value)
        ):
            node = workflow.get(node_id)
            if not isinstance(node, dict):
                continue
            class_type = node.get("class_type", "")
            if class_type in {
                "CLIPTextEncode",
                "TextEncodeQwenImageEdit",
                "TextEncodeQwenImageEditPlus",
                "TextEncodeQwenImageEditPlusPro_lrzjason",
            }:
                encode_nodes.append(node)
        if encode_nodes:
            _set_text(encode_nodes[0], prompt)
        if len(encode_nodes) > 1 and negative_prompt is not None:
            _set_text(encode_nodes[1], negative_prompt)

        for node in workflow.values():
            if not isinstance(node, dict):
                continue
            class_type = node.get("class_type", "")
            inputs = node.setdefault("inputs", {})
            if class_type == "EmptyLatentImage":
                inputs["width"] = width
                inputs["height"] = height
                inputs["batch_size"] = batch_size
            elif class_type == "KSampler":
                if steps is not None:
                    inputs["steps"] = steps
                if cfg_scale is not None:
                    inputs["cfg"] = cfg_scale
                if seed is not None:
                    inputs["seed"] = seed
                if sampler:
                    inputs["sampler_name"] = sampler
                if scheduler:
                    inputs["scheduler"] = scheduler

    def _apply_comfy_load_image(self, workflow: dict, image_name: str) -> None:
        for node in workflow.values():
            if not isinstance(node, dict):
                continue
            if node.get("class_type") == "LoadImage":
                inputs = node.setdefault("inputs", {})
                inputs["image"] = image_name

    async def _generate_comfy_sketch_with_multiview(
        self,
        *,
        client: ComfySdClient,
        preset: CharacterPreset,
        prompt: str,
        negative_prompt: Optional[str],
        base_prompt: str,
        width: int,
        height: int,
        steps: Optional[int],
        cfg_scale: Optional[float],
        seed: Optional[int],
        sampler: Optional[str],
        scheduler: Optional[str],
        model_id: Optional[str],
        vae_id: Optional[str],
        clip_id: Optional[str],
        loader_type: str,
        loras: list[dict],
        workflow_set: Optional[str],
        generate_reference_images: bool,
    ) -> tuple[str, list[dict]]:
        settings = get_settings()
        # Use generated_assets_path so that character sketches and references live under
        # the unified generated assets tree rather than the root assets directory. This ensures
        # all generated outputs are stored in one top-level folder (assets/generated).
        storage = LocalImageStorage(settings.generated_assets_path)

        def _path_to_url(path: str) -> str:
            rel = Path(path).relative_to(settings.assets_root_path).as_posix()
            return f"/api/assets/{rel}"

        def _run() -> tuple[str, list[dict]]:
            reference_slots = _get_reference_slots()
            slots_by_kind = {slot["kind"]: slot for slot in reference_slots}
            ordered_kinds = [slot["kind"] for slot in reference_slots if slot.get("kind")]

            def _seed(idx: int) -> int | None:
                if seed is None:
                    return None
                return int(seed) + idx

            def _slot_dims(kind: str) -> tuple[int, int]:
                slot = slots_by_kind.get(kind, {})
                w = slot.get("width") or width
                h = slot.get("height") or height
                try:
                    return int(w), int(h)
                except Exception:
                    return width, height

            # 1) Sketch (character txt2img)
            sketch = client.generate_images(
                prompt=prompt,
                style=None,
                num_images=1,
                width=width,
                height=height,
                negative_prompt=negative_prompt,
                cfg_scale=cfg_scale,
                steps=steps,
                seed=_seed(0),
                sampler=sampler,
                scheduler=scheduler,
                model_id=model_id,
                vae_id=vae_id,
                clip_id=clip_id,
                loader_type=loader_type,
                loras=loras,
                workflow_set=workflow_set,
                workflow_task="character",
            )
            if not sketch:
                raise RuntimeError("ComfyUI returned no images for character sketch")
            preview_bytes = sketch[0]

            preview_paths = storage.save_images(f"entities/characters/{preset.id}/sketches/latest", [preview_bytes])
            preview_url = _path_to_url(preview_paths[0])

            refs: list[dict] = []
            sketch_slot = slots_by_kind.get("sketch", {})
            refs.append(
                {
                    "id": uuid4().hex,
                    "kind": "sketch",
                    "label": sketch_slot.get("label"),
                    "url": preview_url,
                    "thumb_url": preview_url,
                    "meta": {
                        "created_at": datetime.utcnow().isoformat(),
                        "prompt": prompt,
                        "width": width,
                        "height": height,
                        "cfg_scale": cfg_scale,
                        "steps": steps,
                        "seed": seed,
                        "sampler": sampler,
                        "scheduler": scheduler,
                        "workflow": "character_txt2img",
                        "source": "sketch",
                    },
                }
            )

            if not generate_reference_images:
                return preview_url, refs

            # 2) Multi-view references via repeated img2img from the sketch.
            # Root cause: Need to preserve character identity while changing pose/position
            # Solution: Use strong identity preservation prompts with specific pose/angle instructions
            wildcards, wildcards_enabled = _get_wildcards_config()
            prompt_builder = PromptBuilder(wildcards=wildcards if wildcards_enabled else None)
            sheet_prompt_prefix = _get_sheet_prompt_prefix()
            view_prompts: dict[str, str] = {}
            for kind in ["full_front", "full_side", "full_back"]:
                slot = slots_by_kind.get(kind, {})
                slot_prompt = slot.get("prompt") or ""
                prompt_parts = [
                    sheet_prompt_prefix,
                    slot_prompt,  # Specific pose/angle instruction
                    "PRESERVE_IDENTITY: same person, exact same face, same facial features, same hairstyle",
                    "same outfit, same clothing, consistent character design",
                    base_prompt,  # Original character description
                ]
                prompt_text = ", ".join([p for p in prompt_parts if p])
                prompt_text = prompt_builder.expand_wildcards(prompt_text)
                view_prompts[kind] = prompt_text

            complex_prompt = slots_by_kind.get("complex", {}).get("prompt") or "three quarter view, dynamic pose"
            complex_parts = [
                sheet_prompt_prefix,
                complex_prompt,
                "PRESERVE_IDENTITY: same person, exact same face, same facial features, same hairstyle",
                "same outfit, same clothing, consistent character design",
                base_prompt,
            ]
            complex_text = ", ".join([p for p in complex_parts if p])
            complex_text = prompt_builder.expand_wildcards(complex_text)
            view_prompts["complex"] = complex_text

            # Conservative denoise to preserve identity.
            denoise = 0.65
            for i, kind in enumerate(["complex", "full_front", "full_side", "full_back"], start=1):
                w, h = _slot_dims(kind)
                images = client.generate_images(
                    prompt=view_prompts.get(kind, base_prompt),
                    style=None,
                    num_images=1,
                    width=w,
                    height=h,
                    negative_prompt=negative_prompt,
                    cfg_scale=cfg_scale,
                    steps=steps,
                    seed=_seed(i),
                    sampler=sampler,
                    scheduler=scheduler,
                    model_id=model_id,
                    vae_id=vae_id,
                    clip_id=clip_id,
                    loader_type=loader_type,
                    loras=loras,
                    init_images=[preview_bytes],
                    denoising_strength=denoise,
                    workflow_set=workflow_set,
                    workflow_task="character",
                )
                if not images:
                    continue
                image_bytes = images[0]
                slot = slots_by_kind.get(kind, {})
                ref_paths = storage.save_images(f"entities/characters/{preset.id}/references/{kind}", [image_bytes])
                url = _path_to_url(ref_paths[0])
                refs.append(
                    {
                        "id": uuid4().hex,
                        "kind": kind,
                        "label": slot.get("label"),
                        "url": url,
                        "thumb_url": url,
                        "meta": {
                            "created_at": datetime.utcnow().isoformat(),
                            "prompt": view_prompts.get(kind),
                            "width": w,
                            "height": h,
                            "cfg_scale": cfg_scale,
                            "steps": steps,
                            "seed": seed,
                            "sampler": sampler,
                            "scheduler": scheduler,
                            "workflow": "character_img2img",
                            "source": "sketch",
                        },
                    }
                )

            order_index = {k: idx for idx, k in enumerate(ordered_kinds)}
            refs.sort(key=lambda ref: order_index.get(ref.get("kind", ""), 999))

            return preview_url, refs

        return await anyio.to_thread.run_sync(_run)

    async def generate_character_3step_workflow(
        self,
        preset_id: str,
        user_id: str,
        *,
        project_id: Optional[str] = None,
        style_profile_id: Optional[str] = None,
        scene_prompt: Optional[str] = None,
        use_wildcards: bool = True,
        overrides: Optional[GenerationOverrides] = None,
        job_id: Optional[str] = None,
    ) -> CharacterPreset:
        """
        Generate character using 3-step workflow: portrait -> multiview -> scene
        
        Root cause: Need complete character generation pipeline with scene context
        Solution: Execute 3 sequential workflows with proper reference passing
        """
        
        preset = await self.preset_repo.get_by_id(preset_id)
        if not preset:
            raise HTTPException(status_code=404, detail="Character preset not found")
        
        if preset.author_id != user_id:
            raise HTTPException(status_code=403, detail="Permission denied")
        
        # Ensure anchor token exists
        if not getattr(preset, "anchor_token", None):
            preset.anchor_token = f"wlchar_{uuid4().hex[:8]}"
        
        # Load multiview config (custom workflow set)
        view_config_path = Path("backend/app/config/character_view_config.json")
        if not view_config_path.exists():
            raise HTTPException(status_code=500, detail="Character view configuration not found")

        with open(view_config_path) as f:
            view_config = json.load(f)

        # Scene defaults (use workflow params if available for prompt text only)
        default_scene_prompt = (
            "Use this character reference. Create a cinematic scene with detailed environment and lighting. "
            "Keep the same character identity, face, hairstyle, outfit details and proportions. "
            "Add environment, lighting and mood, but do not change the character."
        )
        default_scene_negative = (
            "low quality, blurry, distorted, deformed, ugly, bad anatomy, worst quality, "
            "character changes, different person, face changes"
        )
        workflow_params_path = Path("tools/workflows/workflow_parameters.json")
        if workflow_params_path.exists():
            try:
                workflow_params = json.loads(workflow_params_path.read_text(encoding="utf-8"))
                step3_params = workflow_params.get("workflow_parameters", {}).get("step3_scene", {})
                default_scene_prompt = step3_params.get("default_prompt") or default_scene_prompt
                default_scene_negative = step3_params.get("default_negative") or default_scene_negative
            except Exception:
                pass
        
        # Initialize job tracking
        job: GenerationJob | None = None
        if job_id:
            try:
                job = await self.db.get(GenerationJob, job_id)
            except Exception:
                job = None
        
        if job:
            job.stage = "character_3step_init"
            job.progress = 5
            job.results = {
                "entity_type": "character_preset",
                "entity_id": preset.id,
                "workflow_type": "3step_character",
                "steps_completed": 0,
                "total_steps": 3
            }
        
        try:
            # STEP 1 + 2: Generate portrait + multiview using custom workflow set
            if job:
                job.stage = "step1_portrait_generation"
                job.progress = 10

            logger.info(f"[Character 3-Step] Starting Step 1+2 (custom multiview) for preset {preset.id}")

            multiview_preset = await self.generate_preset_multiview(
                preset_id=preset.id,
                user_id=user_id,
                project_id=project_id,
                style_profile_id=style_profile_id,
                overrides=overrides,
                job_id=None,
            )
            preset = multiview_preset

            refs = [r for r in (multiview_preset.reference_images or []) if isinstance(r, dict)]
            portrait_ref = next((r for r in refs if r.get("kind") == "multiview_initial"), None)
            portrait_url = (
                (portrait_ref.get("url") if isinstance(portrait_ref, dict) else None)
                or multiview_preset.preview_image_url
            )
            step1_prompt = None
            if isinstance(portrait_ref, dict):
                meta = portrait_ref.get("meta")
                if isinstance(meta, dict):
                    step1_prompt = meta.get("prompt")

            view_order = list((view_config.get("view_configurations") or {}).keys())
            multiview_urls: list[str] = []
            for view_name in view_order:
                ref = next((r for r in refs if r.get("kind") == f"multiview_{view_name}"), None)
                if isinstance(ref, dict) and ref.get("url"):
                    multiview_urls.append(ref["url"])
            extra_urls = [
                r.get("url")
                for r in refs
                if isinstance(r, dict)
                and str(r.get("kind", "")).startswith("multiview_")
                and r.get("kind") != "multiview_initial"
                and r.get("url")
                and r.get("url") not in multiview_urls
            ]
            multiview_urls.extend(extra_urls)

            if job:
                job.stage = "step2_complete"
                job.progress = 70
                job.results["steps_completed"] = 2
                job.results["step1_result"] = {
                    "portrait_url": portrait_url,
                    "prompt": step1_prompt,
                }
                job.results["step2_result"] = {
                    "multiview_urls": multiview_urls,
                    "reference_url": portrait_url,
                }

            logger.info(f"[Character 3-Step] Step 1+2 complete: {len(multiview_urls)} views generated")
            
            # STEP 3: Generate scene (optional)
            scene_url = None
            if scene_prompt:
                if job:
                    job.stage = "step3_scene_generation"
                    job.progress = 80
                
                logger.info(f"[Character 3-Step] Starting Step 3 for preset {preset.id}")
                
                # Build scene prompt
                full_scene_prompt = f"{default_scene_prompt} {scene_prompt}".strip()

                generator = VisualGenerationService()
                scene_url = await generator.generate_preview(
                    f"characters/{preset.id}/scene",
                    full_scene_prompt,
                    negative_prompt=default_scene_negative,
                    width=overrides.width if overrides and overrides.width else None,
                    height=overrides.height if overrides and overrides.height else None,
                    seed=overrides.seed if overrides and overrides.seed is not None else None,
                    sampler=overrides.sampler if overrides and overrides.sampler else None,
                    scheduler=overrides.scheduler if overrides and overrides.scheduler else None,
                    cfg_scale=overrides.cfg_scale if overrides and overrides.cfg_scale is not None else None,
                    steps=overrides.steps if overrides and overrides.steps is not None else None,
                    model_id=overrides.model_id if overrides and overrides.model_id else None,
                    vae_id=overrides.vae_id if overrides and overrides.vae_id else None,
                    loras=overrides.loras if overrides and overrides.loras else None,
                    seed_context=PipelineSeedContext(
                        kind="scene",
                        project_id=preset.project_id,
                    ),
                    reference_images=[portrait_url] if portrait_url else None,
                    denoising_strength=0.65,
                    workflow_set="custom",
                    workflow_task="scene",
                    use_option_overrides=False,
                )

                if job:
                    job.results["step3_result"] = {
                        "scene_url": scene_url,
                        "scene_prompt": scene_prompt,
                    }

                logger.info(f"[Character 3-Step] Step 3 complete: {scene_url}")
            
            # STEP 4: Organize and store references
            if job:
                job.stage = "organizing_references"
                job.progress = 90
            
            # Build reference set
            refs = preset.reference_images or []
            
            # Add portrait as sketch reference
            sketch_ref = {
                "id": uuid4().hex,
                "kind": "sketch",
                "label": "Portrait",
                "url": portrait_url,
                "thumb_url": portrait_url,
                "meta": merge_ref_meta(
                    {
                        "created_at": datetime.utcnow().isoformat(),
                        "workflow_step": 1,
                        "view_type": "portrait",
                        "prompt": step1_prompt,
                    },
                    build_generated_marker(asset_kind="reference", slot="sketch"),
                ),
            }
            
            # Add multiview references
            view_kind_map = {
                "front_view": ("full_front", "Front View"),
                "side_profile": ("full_side", "Side View"),
                "back_view": ("full_back", "Back View"),
            }

            multiview_refs = []
            for idx, url in enumerate(multiview_urls):
                if not url:
                    continue
                view_name = view_order[idx] if idx < len(view_order) else f"view_{idx}"
                kind, label = view_kind_map.get(view_name, (view_name, view_name.replace("_", " ").title()))
                ref = {
                    "id": uuid4().hex,
                    "kind": kind,
                    "label": label,
                    "url": url,
                    "thumb_url": url,
                    "meta": merge_ref_meta(
                        {
                            "created_at": datetime.utcnow().isoformat(),
                            "workflow_step": 2,
                            "view_type": view_name,
                            "reference_url": portrait_url,
                        },
                        build_generated_marker(asset_kind="reference", slot=kind),
                    ),
                }
                multiview_refs.append(ref)
            
            # Add scene reference if generated
            scene_ref = None
            if scene_url:
                scene_ref = {
                    "id": uuid4().hex,
                    "kind": "scene",
                    "label": "Scene",
                    "url": scene_url,
                    "thumb_url": scene_url,
                    "meta": merge_ref_meta(
                        {
                            "created_at": datetime.utcnow().isoformat(),
                            "workflow_step": 3,
                            "view_type": "scene",
                            "scene_prompt": scene_prompt,
                            "reference_url": portrait_url,
                        },
                        build_generated_marker(asset_kind="reference", slot="scene"),
                    ),
                }
            
            # Create complex reference combining all
            complex_ref = {
                "id": uuid4().hex,
                "kind": "complex",
                "label": "Complete Reference",
                "url": portrait_url,  # Use portrait as primary
                "thumb_url": portrait_url,
                "meta": merge_ref_meta(
                    {
                        "created_at": datetime.utcnow().isoformat(),
                        "workflow_step": "combined",
                        "view_type": "complex",
                        "component_urls": [portrait_url] + multiview_urls + ([scene_url] if scene_url else []),
                        "total_views": len(multiview_urls) + 1 + (1 if scene_url else 0),
                    },
                    build_generated_marker(asset_kind="reference", slot="complex"),
                ),
            }
            
            # Remove old references of same kinds
            existing_kinds = {"sketch", "complex", "full_front", "full_back", "full_side", "scene"}
            filtered_refs = [
                r for r in refs 
                if not (isinstance(r, dict) and r.get("kind") in existing_kinds)
            ]
            
            # Add new references in proper order
            new_refs = [sketch_ref, complex_ref] + multiview_refs
            if scene_ref:
                new_refs.append(scene_ref)
            
            preset.reference_images = filtered_refs + new_refs
            
            # Set preview images
            preset.preview_image_url = portrait_url
            preset.preview_thumbnail_url = portrait_url
            self._set_preview_marker(
                preset,
                marker=build_generated_marker(asset_kind="preview", slot="portrait"),
            )
            
            # Final job update
            if job:
                job.stage = "complete"
                job.progress = 100
                job.results.update({
                    "steps_completed": 3 if scene_url else 2,
                    "total_images": len(new_refs),
                    "portrait_url": portrait_url,
                    "multiview_urls": multiview_urls,
                    "scene_url": scene_url,
                    "reference_count": len(preset.reference_images),
                    "workflow_complete": True
                })
            
            # Save preset with new references
            preset = await self.preset_repo.update(preset)
            
            logger.info(f"[Character 3-Step] Workflow complete for preset {preset.id}: {len(new_refs)} references created")
            
            return preset
            
        except Exception as e:
            logger.error(f"[Character 3-Step] Workflow failed for preset {preset.id}: {e}")
            
            if job:
                job.stage = "error"
                job.progress = 0
                job.results["error"] = str(e)
                job.results["workflow_complete"] = False
            
            raise HTTPException(
                status_code=500,
                detail=f"Character 3-step workflow failed: {str(e)}"
            )
    async def generate_preset_multiview(
        self,
        preset_id: str,

        user_id: str,
        *,
        project_id: Optional[str] = None,
        style_profile_id: Optional[str] = None,
        overrides: Optional[GenerationOverrides] = None,
        job_id: Optional[str] = None,
    ) -> CharacterPreset:
        """Generate multi-view character images using sequential img2img processing.
        
        Root cause: Need comprehensive multi-view character generation with view-specific
        prompts and character identity preservation across all generated views.
        
        Process:
        1. Generate initial character image (txt2img)
        2. Generate multiple views sequentially (img2img) with view-specific prompts
        3. Preserve character identity and consistency across all views
        """
        preset = await self.preset_repo.get_by_id(preset_id)
        if not preset:
            raise HTTPException(status_code=404, detail="Character preset not found")
        
        if preset.author_id != user_id:
            raise HTTPException(status_code=403, detail="Permission denied")
        
        # Load character view configuration
        config_path = Path("backend/app/config/character_view_config.json")
        if not config_path.exists():
            raise HTTPException(status_code=500, detail="Character view configuration not found")
        
        with open(config_path) as f:
            view_config = json.load(f)

        def _normalize_workflow_task(value: Optional[str]) -> Optional[str]:
            if not value:
                return None
            for suffix in ("_txt2img", "_img2img"):
                if value.endswith(suffix):
                    return value[: -len(suffix)]
            return value
        
        # Initialize job tracking
        job: GenerationJob | None = None
        if job_id:
            try:
                job = await self.db.get(GenerationJob, job_id)
            except Exception:
                job = None
        
        if job:
            job.stage = "multiview_generation"
            job.progress = 0
            job.results = {
                "entity_type": "character_preset",
                "entity_id": preset.id,
                "views_generated": [],
                "total_views": len(view_config["view_configurations"]) + 1  # +1 for initial
            }
        
        # Ensure anchor token exists
        if not getattr(preset, "anchor_token", None):
            preset.anchor_token = f"wlchar_{uuid4().hex[:8]}"
        
        # Load style profile
        style_profile = await self._load_style_profile(
            style_profile_id=style_profile_id,
            project_id=project_id or preset.project_id
        )
        
        # Build base character description
        base_parts = []
        if preset.name:
            base_parts.append(preset.name)
        if preset.appearance_prompt:
            base_parts.append(preset.appearance_prompt)
        if preset.description:
            base_parts.append(preset.description)
        if preset.style_tags:
            base_parts.extend([str(t) for t in preset.style_tags if t])
        if style_profile and style_profile.base_prompt:
            base_parts.append(style_profile.base_prompt)
        
        base_description = ", ".join([p for p in base_parts if p])
        
        # SD tokens for consistency
        sd_tokens = []
        if preset.anchor_token:
            sd_tokens.append(preset.anchor_token)
        sd_tokens.extend(collect_embedding_tokens(getattr(preset, "embeddings", None)))
        sd_tokens.extend(collect_lora_tokens(getattr(preset, "lora_models", None)))
        if style_profile:
            try:
                sd_tokens.extend(collect_lora_tokens(style_profile.lora_refs))
            except Exception:
                pass
        
        # LoRA models
        loras = []
        if preset.lora_models:
            loras.extend(preset.lora_models)
        if style_profile and style_profile.lora_refs:
            loras.extend(style_profile.lora_refs)
        if overrides and overrides.loras:
            try:
                loras.extend([dict(l) for l in overrides.loras if l])
            except Exception:
                pass
        
        # Get pipeline resolver and SD layer
        resolver = get_pipeline_resolver()
        sd_layer = get_sd_layer()
        generator = VisualGenerationService()
        
        # Stage 1: Generate initial character image (txt2img)
        if job:
            job.stage = "initial_generation"
            job.progress = 10
        
        initial_config = view_config["default_workflow"]["initial_generation"]
        view_generation_config = view_config["default_workflow"]["view_generation"]
        initial_workflow_set = initial_config.get("workflow_set")
        initial_workflow_task = _normalize_workflow_task(initial_config.get("workflow_task")) or "character"
        view_workflow_set = view_generation_config.get("workflow_set")
        view_workflow_task = _normalize_workflow_task(view_generation_config.get("workflow_task")) or "character"
        
        # Build initial prompt with consistency tokens
        initial_prompt_parts = [
            base_description,
            view_config["prompt_templates"]["base_character_prompt"].format(
                character_description=base_description
            ),
            view_config["prompt_templates"]["style_consistency"]
        ]
        initial_prompt = prepend_tokens(
            ", ".join(initial_prompt_parts),
            sd_tokens
        )
        
        # Build negative prompt
        negative_parts = []
        if style_profile and style_profile.negative_prompt:
            negative_parts.append(style_profile.negative_prompt)
        if preset.negative_prompt:
            negative_parts.append(preset.negative_prompt)
        if overrides and overrides.negative_prompt:
            negative_parts.append(overrides.negative_prompt)
        negative_parts.append(view_config["prompt_templates"]["negative_base"].format(
            view_negative=""
        ))
        initial_negative = ", ".join([n for n in negative_parts if n])
        
        # Resolve pipeline for initial generation
        resolved_initial = resolver.resolve(
            kind="character_multiview",
            profile_id=overrides.pipeline_profile_id if overrides else None,
            profile_version=overrides.pipeline_profile_version if overrides else None,
            overrides={
                "width": initial_config["width"],
                "height": initial_config["height"],
                "cfg_scale": initial_config["guidance"],
                "steps": initial_config["steps"],
                "loras": loras,
                "seed_policy": "random",
                "workflow_set": initial_workflow_set,
            },
            seed_context=PipelineSeedContext(
                kind="character_multiview",
                character_id=preset.id,
                slot="initial",
            ),
        )
        
        # Generate initial image
        initial_url = await generator.generate_preview(
            f"characters/{preset.id}/multiview/initial",
            initial_prompt,
            negative_prompt=initial_negative,
            width=resolved_initial.width,
            height=resolved_initial.height,
            style=None,
            cfg_scale=resolved_initial.cfg_scale,
            steps=resolved_initial.steps,
            seed=resolved_initial.seed,
            sampler=resolved_initial.sampler,
            scheduler=resolved_initial.scheduler,
            model_id=resolved_initial.model_id,
            vae_id=resolved_initial.vae_id,
            loras=[lora.model_dump() for lora in resolved_initial.loras],
            pipeline_profile_id=resolved_initial.profile_id,
            pipeline_profile_version=resolved_initial.profile_version,
            workflow_set=initial_workflow_set,
            workflow_task=initial_workflow_task,
            seed_context=PipelineSeedContext(
                kind="character_multiview",
                character_id=preset.id,
                slot="initial",
                profile_version=resolved_initial.profile_version,
            ),
        )
        
        # Store initial image as reference
        created_refs = [{
            "id": uuid4().hex,
            "kind": "multiview_initial",
            "label": "Initial Character",
            "url": initial_url,
            "thumb_url": initial_url,
            "meta": {
                "created_at": datetime.utcnow().isoformat(),
                "prompt": initial_prompt,
                "negative_prompt": initial_negative,
                "width": resolved_initial.width,
                "height": resolved_initial.height,
                "cfg_scale": resolved_initial.cfg_scale,
                "steps": resolved_initial.steps,
                "seed": resolved_initial.seed,
                "workflow_stage": "initial",
                "view_type": "txt2img",
            }
        }]
        
        if job:
            job.results["views_generated"].append("initial")
            job.results["reference_images"] = created_refs
            job.results["latest_view"] = {
                "name": "initial",
                "url": initial_url,
                "completed_at": datetime.utcnow().isoformat()
            }
            job.progress = 20
            # Commit initial result immediately so UI can display it
            await self.db.commit()
            await self.db.refresh(job)
        
        # Stage 2: Generate multiple views sequentially (img2img)
        view_configs = view_config["view_configurations"]
        
        total_views = len(view_configs)
        for idx, (view_name, view_spec) in enumerate(view_configs.items()):
            if job:
                job.stage = f"generating_{view_name}"
                job.progress = 20 + int((idx / total_views) * 70)
            
            # Build view-specific prompt
            view_prompt_parts = [
                base_description,
                view_config["prompt_templates"]["view_specific_prompt"].format(
                    base_description=base_description,
                    view_suffix=view_spec["prompt_suffix"]
                ),
                view_config["prompt_templates"]["style_consistency"]
            ]
            view_prompt = prepend_tokens(
                ", ".join(view_prompt_parts),
                sd_tokens
            )
            
            # Build view-specific negative prompt
            view_negative_parts = negative_parts.copy()
            view_negative_parts.append(view_config["prompt_templates"]["negative_base"].format(
                view_negative=view_spec["negative_suffix"]
            ))
            view_negative = ", ".join([n for n in view_negative_parts if n])
            
            # Resolve pipeline for view generation
            resolved_view = resolver.resolve(
                kind="character_multiview",
                profile_id=overrides.pipeline_profile_id if overrides else None,
                profile_version=overrides.pipeline_profile_version if overrides else None,
                overrides={
                    "width": initial_config["width"],
                    "height": initial_config["height"],
                    "cfg_scale": view_spec["guidance"],
                    "steps": view_generation_config["steps"],
                    "loras": loras,
                    "seed_policy": "random",
                    "workflow_set": view_workflow_set,
                },
                seed_context=PipelineSeedContext(
                    kind="character_multiview",
                    character_id=preset.id,
                    slot=view_name,
                ),
            )

            # Generate view using img2img with initial image as reference
            view_url = await generator.generate_preview(
                f"characters/{preset.id}/multiview/{view_name}",
                view_prompt,
                negative_prompt=view_negative,
                width=resolved_view.width,
                height=resolved_view.height,
                style=None,
                cfg_scale=resolved_view.cfg_scale,
                steps=resolved_view.steps,
                seed=resolved_view.seed,
                sampler=resolved_view.sampler,
                scheduler=resolved_view.scheduler,
                model_id=resolved_view.model_id,
                vae_id=resolved_view.vae_id,
                loras=[lora.model_dump() for lora in resolved_view.loras],
                pipeline_profile_id=resolved_view.profile_id,
                pipeline_profile_version=resolved_view.profile_version,
                workflow_set=view_workflow_set,
                workflow_task=view_workflow_task,
                seed_context=PipelineSeedContext(
                    kind="character_multiview",
                    character_id=preset.id,
                    slot=view_name,
                    profile_version=resolved_view.profile_version,
                ),
                reference_images=[initial_url],
                denoising_strength=view_spec["denoise"],
                force_img2img=True,  # Explicitly use img2img for multiview generation
            )

            # Store view reference
            view_ref = {
                "id": uuid4().hex,
                "kind": f"multiview_{view_name}",
                "label": view_name.replace("_", " ").title(),
                "url": view_url,
                "thumb_url": view_url,
                "meta": merge_ref_meta(
                    {
                        "created_at": datetime.utcnow().isoformat(),
                        "prompt": view_prompt,
                        "negative_prompt": view_negative,
                        "width": resolved_view.width,
                        "height": resolved_view.height,
                        "cfg_scale": resolved_view.cfg_scale,
                        "steps": resolved_view.steps,
                        "seed": resolved_view.seed,
                        "workflow_stage": "multiview",
                        "view_type": "img2img",
                        "view_name": view_name,
                        "denoise_strength": view_spec["denoise"],
                        "reference_image": initial_url,
                    },
                    build_generated_marker(asset_kind="reference", slot=f"multiview_{view_name}"),
                ),
            }
            created_refs.append(view_ref)

            # Root cause: UI was waiting for all views to complete before showing any results
            # Solution: Commit job results after each view so UI can poll and display incrementally
            if job:
                job.results["views_generated"].append(view_name)
                job.results["reference_images"] = created_refs  # Update with all refs so far
                job.results["latest_view"] = {
                    "name": view_name,
                    "url": view_url,
                    "completed_at": datetime.utcnow().isoformat()
                }
                # Commit to DB so UI can see the update immediately
                await self.db.commit()
                await self.db.refresh(job)

            # Small pause between generations for stability
            await asyncio.sleep(0.5)
        
        # Update preset with all generated references
        existing_refs = [r for r in (preset.reference_images or []) if isinstance(r, dict)]
        # Remove any existing multiview references to avoid duplicates
        kept_refs = [r for r in existing_refs if not r.get("kind", "").startswith("multiview_")]
        preset.reference_images = kept_refs + created_refs
        
        # Set preview image to initial generation if not already set
        if not preset.preview_image_url and created_refs:
            preset.preview_image_url = created_refs[0]["url"]
            preset.preview_thumbnail_url = created_refs[0]["url"]
            self._set_preview_marker(
                preset,
                marker=build_generated_marker(asset_kind="preview", slot="multiview_initial"),
            )
        
        if job:
            job.stage = "complete"
            job.progress = 100
            job.results["total_generated"] = len(created_refs)
            job.results["reference_images"] = created_refs
        
        return await self.preset_repo.update(preset)


    
