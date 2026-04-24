from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

from pydantic import BaseModel, Field, ValidationError

from app.core.config import get_settings
from app.utils.seed import stable_seed

logger = logging.getLogger(__name__)


def detect_model_type(model_path: str) -> str:
    """Auto-detect model type based on file extension."""
    if model_path.lower().endswith(".gguf"):
        return "gguf"
    elif model_path.lower().endswith(".safetensors"):
        return "safetensors"
    else:
        return "safetensors"  # Default


class LoraConfig(BaseModel):
    name: str
    weight: float = Field(0.8, ge=0.0, le=2.0)
    clip_weight: Optional[float] = Field(None, ge=0.0, le=2.0)
    optional: bool = Field(False, description="If true, missing LoRA is skipped without warnings")


class PipelineProfile(BaseModel):
    profile_id: str = Field(..., min_length=1)
    version: int = Field(1, ge=1)
    # Optional human-facing metadata. These fields make it possible to ship curated
    # “recommended” profiles without forcing UI changes immediately.
    label: Optional[str] = None
    description: Optional[str] = None
    recommended: Optional[bool] = None
    tags: Optional[list[str]] = None
    model_checkpoint: str
    vae: Optional[str] = None
    clip: Optional[str] = None
    model_type: Optional[str] = None  # "gguf" or "safetensors"
    loader_type: Optional[str] = None  # "gguf" or "standard"
    sampler: str
    scheduler: str
    steps: int = Field(20, ge=1, le=200)
    cfg_scale: float = Field(7.0, ge=0.1, le=50.0)
    width: int = Field(640, ge=64, le=4096)
    height: int = Field(480, ge=64, le=4096)
    seed_policy: str = Field("random", description="fixed | random | derived")
    seed: Optional[int] = None
    loras: list[LoraConfig] = Field(default_factory=list)
    controlnet_enabled: Optional[bool] = None
    ip_adapter_enabled: Optional[bool] = None

    # ComfyUI-only: select a workflow set (see app/config/comfy_workflow_sets.json).
    # Safe to include in pipeline_profiles.json because other providers ignore it.
    workflow_set: Optional[str] = None


class PipelineDefaults(BaseModel):
    profile_id: str
    version: Optional[int] = None


class PipelineProfilesFile(BaseModel):
    defaults: dict[str, PipelineDefaults] = Field(default_factory=dict)
    profiles: list[PipelineProfile] = Field(default_factory=list)


@dataclass(frozen=True)
class PipelineSeedContext:
    kind: str
    project_id: Optional[str] = None
    scene_id: Optional[str] = None
    character_id: Optional[str] = None
    character_ids: Optional[list[str]] = None
    slot: Optional[str] = None
    profile_version: Optional[int] = None


class ResolvedPipeline(BaseModel):
    profile_id: str
    profile_version: int
    model_id: str
    vae_id: Optional[str]
    clip_id: Optional[str]
    model_type: Optional[str] = None  # "gguf" or "safetensors"
    loader_type: Optional[str] = None  # "gguf" or "standard"
    sampler: str
    scheduler: str
    steps: int
    cfg_scale: float
    width: int
    height: int
    seed: int
    seed_policy: str
    loras: list[LoraConfig] = Field(default_factory=list)
    # Feature toggles (currently used as hints by higher-level services).
    controlnet_enabled: Optional[bool] = None
    ip_adapter_enabled: Optional[bool] = None

    # ComfyUI-only workflow selector propagated from the profile.
    workflow_set: Optional[str] = None


def _normalize_loras(items: Optional[Iterable[Any]]) -> list[LoraConfig]:
    loras: list[LoraConfig] = []
    for item in items or []:
        if not item:
            continue
        if isinstance(item, LoraConfig):
            loras.append(item)
            continue
        if isinstance(item, dict):
            name = item.get("name") or item.get("id")
            if not name:
                continue
            try:
                weight = float(item.get("weight", 0.8))
            except Exception:
                weight = 0.8
            clip_weight = item.get("clip_weight")
            if clip_weight is None:
                clip_weight = item.get("weight_clip")
            if clip_weight is None:
                clip_weight = item.get("strength_clip")
            try:
                clip_weight_val = float(clip_weight) if clip_weight is not None else None
            except Exception:
                clip_weight_val = None
            loras.append(
                LoraConfig(
                    name=str(name),
                    weight=weight,
                    clip_weight=clip_weight_val,
                    optional=bool(item.get("optional")),
                )
            )
            continue
        try:
            name = getattr(item, "name", None)
            weight = getattr(item, "weight", None)
            clip_weight = getattr(item, "clip_weight", None)
            if name:
                loras.append(
                    LoraConfig(
                        name=str(name),
                        weight=float(weight) if weight is not None else 0.8,
                        clip_weight=float(clip_weight) if clip_weight is not None else None,
                        optional=bool(getattr(item, "optional", False)),
                    )
                )
        except Exception:
            continue
    # Deduplicate by name (last wins)
    unique: dict[str, LoraConfig] = {}
    for lora in loras:
        unique[lora.name] = lora
    return list(unique.values())


class PipelineProfileStore:
    def __init__(self, path: Path):
        self.path = path
        self._profiles: dict[str, list[PipelineProfile]] = {}
        self._defaults: dict[str, PipelineDefaults] = {}
        self._loaded = False

    def _load(self) -> None:
        self._loaded = True
        if not self.path.exists():
            logger.warning("Pipeline profile file not found: %s", self.path)
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            parsed = PipelineProfilesFile(**data)
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            logger.error("Failed to load pipeline profiles: %s", exc)
            return

        profiles: dict[str, list[PipelineProfile]] = {}
        for profile in parsed.profiles:
            profiles.setdefault(profile.profile_id, []).append(profile)
        for profile_id, items in profiles.items():
            items.sort(key=lambda p: p.version)

        self._profiles = profiles
        self._defaults = parsed.defaults

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self._load()

    def get(self, profile_id: str, version: Optional[int] = None) -> Optional[PipelineProfile]:
        self._ensure_loaded()
        items = self._profiles.get(profile_id, [])
        if not items:
            return None
        if version is None:
            return items[-1]
        for item in items:
            if item.version == version:
                return item
        return None

    def default_for(self, kind: str) -> Optional[PipelineDefaults]:
        self._ensure_loaded()
        return self._defaults.get(kind)


class PipelineProfileResolver:
    def __init__(self, store: Optional[PipelineProfileStore] = None) -> None:
        settings = get_settings()
        self.store = store or PipelineProfileStore(settings.pipeline_profiles_path)
        self.settings = settings

    def resolve(
        self,
        *,
        kind: str,
        profile_id: Optional[str] = None,
        profile_version: Optional[int] = None,
        overrides: Optional[dict[str, Any]] = None,
        seed_context: Optional[PipelineSeedContext] = None,
    ) -> ResolvedPipeline:
        overrides = overrides or {}
        chosen_id, chosen_version = self._pick_profile(kind, profile_id, profile_version)
        profile = self.store.get(chosen_id, chosen_version)
        if profile is None:
            raise RuntimeError(f"Pipeline profile not found: {chosen_id} (v{chosen_version or 'latest'})")

        loras = _normalize_loras(profile.loras)
        loras = _normalize_loras([*loras, *(overrides.get("loras") or []), *(overrides.get("lora_refs") or [])])

        seed_policy = str(overrides.get("seed_policy") or profile.seed_policy or "random")
        if seed_policy in {"character-consistent", "character_consistent"}:
            seed_policy = "derived"
        seed = overrides.get("seed")
        if seed is None:
            seed = self._resolve_seed(profile, seed_policy, seed_context)

        return ResolvedPipeline(
            profile_id=profile.profile_id,
            profile_version=profile.version,
            model_id=str(overrides.get("model_checkpoint") or overrides.get("model_id") or profile.model_checkpoint),
            vae_id=(overrides.get("vae") or overrides.get("vae_id") or profile.vae),
            clip_id=(overrides.get("clip") or overrides.get("clip_id") or profile.clip),
            model_type=profile.model_type or detect_model_type(profile.model_checkpoint),
            loader_type=profile.loader_type or ("gguf" if (profile.model_type or detect_model_type(profile.model_checkpoint)) == "gguf" else "standard"),
            sampler=str(overrides.get("sampler") or profile.sampler),
            scheduler=str(overrides.get("scheduler") or profile.scheduler),
            steps=int(overrides.get("steps") or profile.steps),
            cfg_scale=float(overrides.get("cfg_scale") or profile.cfg_scale),
            width=int(overrides.get("width") or profile.width),
            height=int(overrides.get("height") or profile.height),
            seed=int(seed),
            seed_policy=seed_policy,
            loras=loras,
            controlnet_enabled=bool(overrides.get("controlnet_enabled")) if "controlnet_enabled" in overrides else profile.controlnet_enabled,
            ip_adapter_enabled=bool(overrides.get("ip_adapter_enabled")) if "ip_adapter_enabled" in overrides else profile.ip_adapter_enabled,
            workflow_set=(
                str(overrides.get("workflow_set"))
                if overrides.get("workflow_set") is not None
                else profile.workflow_set
            ),
        )

    def _pick_profile(
        self,
        kind: str,
        profile_id: Optional[str],
        profile_version: Optional[int],
    ) -> tuple[str, Optional[int]]:
        if profile_id:
            return profile_id, profile_version
        defaults = self.store.default_for(kind)
        if defaults:
            return defaults.profile_id, defaults.version
        fallback_id = self.settings.pipeline_profile_default_id
        return fallback_id, self.settings.pipeline_profile_default_version

    def _resolve_seed(
        self,
        profile: PipelineProfile,
        seed_policy: str,
        context: Optional[PipelineSeedContext],
    ) -> int:
        if seed_policy == "fixed":
            if profile.seed is not None:
                return int(profile.seed)
            return stable_seed(profile.profile_id, str(profile.version), namespace="pipeline")

        if seed_policy == "derived":
            if context and context.character_id:
                return stable_seed(
                    "character",
                    context.character_id,
                    context.slot or "",
                    str(context.profile_version or profile.version),
                    namespace="pipeline",
                )
            if context and context.character_ids:
                return stable_seed(
                    "scene-cast",
                    context.project_id or "",
                    ",".join(sorted(context.character_ids)),
                    str(context.profile_version or profile.version),
                    namespace="pipeline",
                )
            if context and context.scene_id:
                return stable_seed(
                    "scene",
                    context.scene_id,
                    str(context.profile_version or profile.version),
                    namespace="pipeline",
                )
            return stable_seed(profile.profile_id, str(profile.version), namespace="pipeline")

        # random
        return random.randint(0, 2**32 - 1)


_resolver: Optional[PipelineProfileResolver] = None


def get_pipeline_resolver() -> PipelineProfileResolver:
    global _resolver
    if _resolver is None:
        _resolver = PipelineProfileResolver()
    return _resolver


def peek_pipeline_profile(
    resolver: PipelineProfileResolver,
    *,
    kind: str,
    profile_id: Optional[str],
    profile_version: Optional[int],
) -> Optional[PipelineProfile]:
    """Return the profile that would be used for resolution (without applying overrides)."""
    if profile_id:
        return resolver.store.get(profile_id, profile_version)
    defaults = resolver.store.default_for(kind)
    if defaults:
        return resolver.store.get(defaults.profile_id, defaults.version)
    return resolver.store.get(resolver.settings.pipeline_profile_default_id, resolver.settings.pipeline_profile_default_version)


def is_gguf_profile(profile: Optional[PipelineProfile]) -> bool:
    if not profile or not profile.model_checkpoint:
        return False
    return str(profile.model_checkpoint).lower().endswith(".gguf")


def is_qwen_profile(profile: Optional[PipelineProfile]) -> bool:
    if not profile:
        return False
    if profile.workflow_set and str(profile.workflow_set).lower() == "qwen":
        return True
    model = str(profile.model_checkpoint or "").lower()
    return "qwen" in model
