from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.models import Project, SceneArtifact, SceneNode, SceneNodeCharacter, StyleProfile
from app.schemas.prompting import PromptBundle
from app.services.prompt_templates import PromptTemplateLibrary
from app.utils.sd_tokens import collect_lora_tokens
from app.core.config import get_settings
from app.services.character_lib import get_character_lib

def _normalize_lib_id(value: str) -> str:
    raw = (value or "").strip()
    if raw.startswith("lib:"):
        return raw[4:].strip()
    if raw.startswith("library:"):
        return raw[8:].strip()
    return raw

def _build_library_prompt(char) -> tuple[str, str | None]:
    parts: list[str] = []
    if getattr(char, "name", None):
        parts.append(str(char.name))
    if getattr(char, "description", None):
        parts.append(str(char.description))
    if getattr(char, "appearance_prompt", None):
        parts.append(str(char.appearance_prompt))
    if getattr(char, "style_tags", None):
        try:
            parts.extend([str(t) for t in char.style_tags if t])
        except Exception:
            pass
    prompt = ", ".join([p for p in parts if p])
    negative = getattr(char, "negative_prompt", None)
    return prompt, (str(negative).strip() if negative else None)


class PromptEngine:
    """Builds prompts/configs for scenes using style + characters + world library."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.templates = PromptTemplateLibrary()

    async def build_for_scene(
        self,
        scene_id: str,
        override_style_profile_id: Optional[str] = None,
        visible_character_ids: Optional[list[str]] = None,
        composition_mode: str = "auto",
    ) -> Optional[PromptBundle]:
        scene = await self._load_scene(scene_id)
        if scene is None or scene.graph is None:
            return None

        style = await self._load_style(scene.graph.project_id, override_style_profile_id)

        # Scene characters can be attached for story/dialogue, but not necessarily rendered.
        all_characters = await self._load_scene_characters(scene.id)
        library_characters: list[object] = []
        library_ids: list[str] = []
        if visible_character_ids is None:
            characters = [sc for sc in all_characters if getattr(sc, "in_frame", True)]
        else:
            allowed_raw = [str(value) for value in visible_character_ids if value]
            allowed = set(_normalize_lib_id(value) for value in allowed_raw if value)
            # Accept both SceneNodeCharacter ids and CharacterPreset ids for convenience.
            characters = [
                sc
                for sc in all_characters
                if sc.id in allowed or (sc.character_preset_id and sc.character_preset_id in allowed)
            ]

            # Also allow referencing file-based character library ids.
            settings = get_settings()
            if settings.character_lib_enabled:
                matched: set[str] = set()
                for sc in characters:
                    if sc.id:
                        matched.add(sc.id)
                    if sc.character_preset_id:
                        matched.add(sc.character_preset_id)
                missing = [cid for cid in allowed if cid and cid not in matched]
                if missing:
                    lib = get_character_lib()
                    for cid in missing:
                        char = lib.get_character(cid)
                        if char:
                            library_characters.append(char)
                            library_ids.append(cid)

        prompt_parts: list[str] = []
        negative_parts: list[str] = []

        # --- Style profile
        if style:
            # LoRA tokens for the style (A1111 format). We keep them in the prompt string
            # so the SD backend doesn't need custom payload fields.
            try:
                prompt_parts.extend(collect_lora_tokens(style.lora_refs))
            except Exception:
                pass

            if style.base_prompt:
                prompt_parts.append(style.base_prompt)

            # Optional color palette nudging
            if getattr(style, "palette", None):
                try:
                    palette = ", ".join(str(c) for c in style.palette if c)
                    if palette:
                        prompt_parts.append(f"color palette: {palette}")
                except Exception:
                    pass

            if style.negative_prompt:
                negative_parts.append(style.negative_prompt)

            # Forbidden list is a good candidate for negative prompt
            if getattr(style, "forbidden", None):
                try:
                    negative_parts.extend([str(x) for x in style.forbidden if x])
                except Exception:
                    pass

        # --- Location (from WorldLibrary)
        if getattr(scene, "location", None):
            loc = scene.location
            loc_prompt = self._build_location_prompt(loc, getattr(scene, "location_overrides", None))
            if loc_prompt:
                prompt_parts.append(loc_prompt)
            if getattr(loc, "negative_prompt", None):
                negative_parts.append(loc.negative_prompt)

        # --- Artifacts / props (evidence, documents, etc.)
        if getattr(scene, "scene_artifacts", None):
            props = self._build_artifacts_prompt(scene.scene_artifacts)
            if props:
                prompt_parts.append(props)

        # --- Deterministic template enrichment (shot, lighting, quality)
        # Authors can optionally override "shot" / "lighting" / "mood" via scene.context
        ctx = scene.context or {}
        render_ctx = ctx.get("render") if isinstance(ctx, dict) else None
        if not isinstance(render_ctx, dict):
            render_ctx = {}

        # Backwards-compatible: allow render hints to be stored either at the top-level
        # (ctx["shot"]) or inside ctx["render"]["shot"].
        shot_override = (
            ctx.get("shot") if isinstance(ctx.get("shot"), str) else None
        ) or (
            render_ctx.get("shot") if isinstance(render_ctx.get("shot"), str) else None
        )
        lighting_override = (
            ctx.get("lighting") if isinstance(ctx.get("lighting"), str) else None
        ) or (
            render_ctx.get("lighting") if isinstance(render_ctx.get("lighting"), str) else None
        )
        mood_override = (
            ctx.get("mood") if isinstance(ctx.get("mood"), str) else None
        ) or (
            render_ctx.get("mood") if isinstance(render_ctx.get("mood"), str) else None
        )

        template_bundle = self.templates.build_scene_prompt(
            description=scene.content,
            mood=mood_override or scene.synopsis,
            shot=shot_override,
            lighting=lighting_override,
            style=(style.name if style else "cinematic") or "cinematic",
        )
        prompt_parts.append(template_bundle.prompt)
        if template_bundle.negative_prompt:
            negative_parts.append(template_bundle.negative_prompt)

        # --- Composition hint based on visible cast size
        if composition_mode != "none":
            visible_count = len(characters)
            if visible_count == 0:
                prompt_parts.append("empty scene, no people")
            elif visible_count == 1:
                prompt_parts.append("one person in frame, solo composition")
                negative_parts.append("extra people, crowd")
            elif visible_count == 2:
                prompt_parts.append("two people in frame, two-shot composition")
                negative_parts.append("extra people, crowd")
            else:
                prompt_parts.append(f"{visible_count} people in frame, group shot")

        # --- Characters (from CharacterPresets)
        for sc in characters:
            base = sc.character_preset
            if not base:
                continue

            sd = base.to_sd_prompt(additional_context=sc.scene_context)
            if sd.get("prompt"):
                prompt_parts.append(sd["prompt"])
            if sd.get("negative_prompt"):
                negative_parts.append(sd["negative_prompt"])
            if sc.position:
                prompt_parts.append(f"{sc.position} of frame")

        # --- Library characters (file-based, not yet imported into scene)
        for lib_char in library_characters:
            lib_prompt, lib_negative = _build_library_prompt(lib_char)
            if lib_prompt:
                prompt_parts.append(lib_prompt)
            if lib_negative:
                negative_parts.append(lib_negative)

        # --- Config
        cfg: dict[str, Optional[object]] = {}
        if style and style.resolution:
            if style.resolution.get("width") is not None:
                cfg["width"] = style.resolution["width"]
            if style.resolution.get("height") is not None:
                cfg["height"] = style.resolution["height"]
        if style and style.cfg_scale is not None:
            cfg["cfg_scale"] = style.cfg_scale
        if style and style.steps is not None:
            cfg["steps"] = style.steps
        if style and style.sampler:
            cfg["sampler"] = style.sampler
        if style and getattr(style, "scheduler", None):
            cfg["scheduler"] = style.scheduler
        if style and style.model_checkpoint:
            cfg["model_checkpoint"] = style.model_checkpoint
        if style and style.lora_refs:
            cfg["lora_refs"] = style.lora_refs
            cfg["loras"] = style.lora_refs
        if style and style.seed_policy:
            cfg["seed_policy"] = style.seed_policy

        character_ids = [sc.character_preset_id for sc in characters if sc.character_preset_id]
        if library_ids:
            cfg["character_lib_ids"] = list(dict.fromkeys(library_ids))
            character_ids.extend(library_ids)
        if character_ids:
            # Preserve order while deduplicating
            cfg["character_ids"] = list(dict.fromkeys(character_ids))
        cfg.update(template_bundle.config)

        return PromptBundle(
            prompt=", ".join([p for p in prompt_parts if p]),
            negative_prompt=", ".join([n for n in negative_parts if n]) or None,
            config=cfg,
        )

    def _build_location_prompt(self, location, overrides: Optional[dict]) -> str:
        """Build a prompt fragment for a Location entity."""
        parts: list[str] = []

        # Consistency token first (good for TI / LoRA training)
        if getattr(location, "anchor_token", None):
            parts.append(str(location.anchor_token))

        if getattr(location, "name", None):
            parts.append(str(location.name))
        if getattr(location, "description", None):
            parts.append(str(location.description))
        if getattr(location, "visual_reference", None):
            parts.append(str(location.visual_reference))
        if getattr(location, "tags", None):
            try:
                tags = ", ".join(str(t) for t in location.tags if t)
                if tags:
                    parts.append(f"tags: {tags}")
            except Exception:
                pass
        if getattr(location, "atmosphere_rules", None):
            try:
                parts.append(self._stringify_rules(location.atmosphere_rules))
            except Exception:
                pass

        if overrides:
            try:
                parts.append(f"overrides: {self._stringify_rules(overrides)}")
            except Exception:
                pass

        joined = ", ".join([p for p in parts if p])
        return f"location: {joined}" if joined else ""

    def _build_artifacts_prompt(self, scene_artifacts: list[SceneArtifact]) -> str:
        """Build a short props/evidence string from SceneArtifact relations."""
        items: list[str] = []
        for sa in scene_artifacts or []:
            art = getattr(sa, "artifact", None)
            if not art:
                continue
            name = getattr(art, "name", None) or ""
            if not name:
                continue
            # Keep it short; SD prompt length grows quickly.
            items.append(str(name))

        if not items:
            return ""
        # Dedup while preserving order
        seen: set[str] = set()
        uniq: list[str] = []
        for it in items:
            if it in seen:
                continue
            seen.add(it)
            uniq.append(it)
        return "props: " + ", ".join(uniq)

    def _stringify_rules(self, rules: dict) -> str:
        fragments: list[str] = []
        for key, value in (rules or {}).items():
            if value is None:
                continue
            if isinstance(value, (list, tuple)):
                fragments.append(f"{key}: {', '.join(str(v) for v in value)}")
            else:
                fragments.append(f"{key}: {value}")
        return "; ".join(fragments)

    async def _load_scene(self, scene_id: str) -> Optional[SceneNode]:
        result = await self.session.execute(
            select(SceneNode)
            .options(
                selectinload(SceneNode.graph),
                selectinload(SceneNode.location),
                selectinload(SceneNode.scene_artifacts).selectinload(SceneArtifact.artifact),
            )
            .where(SceneNode.id == scene_id)
        )
        return result.scalar_one_or_none()

    async def _load_style(self, project_id: str, override_style_profile_id: Optional[str]) -> Optional[StyleProfile]:
        if override_style_profile_id:
            return await self.session.get(StyleProfile, override_style_profile_id)
        project = await self.session.get(Project, project_id)
        if project and project.style_profile_id:
            return await self.session.get(StyleProfile, project.style_profile_id)
        result = await self.session.execute(
            select(StyleProfile).where(StyleProfile.project_id == project_id).limit(1)
        )
        return result.scalar_one_or_none()

    async def _load_scene_characters(self, scene_id: str) -> list[SceneNodeCharacter]:
        result = await self.session.execute(
            select(SceneNodeCharacter)
            .options(selectinload(SceneNodeCharacter.character_preset))
            .where(SceneNodeCharacter.scene_id == scene_id)
        )
        return list(result.scalars().all())
