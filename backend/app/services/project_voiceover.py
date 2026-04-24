from __future__ import annotations

import copy
import json
import mimetypes
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.domain.models import CharacterPreset, Project, ScenarioGraph, SceneNode
from app.schemas.ai import AIVoicePreviewRequest
from app.services.voice_preview import VoicePreviewService


class ProjectVoiceoverService:
    """Project-level voiceover workflow.

    Stores generated variants and approvals in `scene.context["voiceover"]["lines"]`.
    This allows playback to use approved project files without runtime TTS calls.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()
        self.preview = VoicePreviewService()
        self.suggested_role_prompts = self._load_suggested_role_prompts()

    def _load_suggested_role_prompts(self) -> Dict[str, Optional[str]]:
        defaults = {
            "narrator": (
                "Спокойный выразительный рассказчик. Ровный темп, чёткая дикция, "
                "нейтральная эмоциональность, без театрального переигрывания."
            ),
            "inner_voice": (
                "Тихий интимный внутренний монолог. Чуть медленнее обычной речи, "
                "задумчиво и лично, с мягкими паузами."
            ),
            "interlocutor": (
                "Живой разговорный голос персонажа в диалоге. Естественная интонация, "
                "умеренная эмоциональность, без дикторского пафоса."
            ),
        }
        config_path = Path(__file__).resolve().parents[1] / "config" / "prompts" / "voiceover_role_prompts.json"
        if not config_path.exists():
            return defaults
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return defaults
        if not isinstance(payload, dict):
            return defaults
        loaded = self._normalize_role_prompts(payload)
        merged: Dict[str, Optional[str]] = dict(defaults)
        for key in ("narrator", "inner_voice", "interlocutor"):
            value = loaded.get(key)
            if value:
                merged[key] = value
        return merged

    async def get_project_voiceover(self, project_id: str) -> Dict[str, Any]:
        graph, _scenes_by_id, lines, project_settings = await self._prepare_graph_voiceover(project_id)
        return {
            "project_id": project_id,
            "graph_id": graph.id,
            "lines": [self._to_public_line(line) for line in lines],
            "summary": self._build_summary(lines),
            "settings": project_settings,
            "suggested_role_prompts": self.suggested_role_prompts,
            "updated_at": self._max_updated_at(graph.scenes),
        }

    async def generate_line_variant(
        self,
        project_id: str,
        *,
        line_id: str,
        language: str,
        voice_profile: Optional[str],
        replace_existing: bool,
    ) -> Dict[str, Any]:
        graph, scenes_by_id, lines, project_settings = await self._prepare_graph_voiceover(project_id)
        line = self._find_line(lines, line_id)
        if line is None:
            raise HTTPException(status_code=404, detail="Voiceover line not found")

        selected_voice = self._resolve_line_voice_profile(
            line,
            project_settings=project_settings,
            explicit_voice_profile=self._clean_text(voice_profile),
            default_voice_profile=None,
        )
        generated = await self._synthesize_variant(
            project_id=project_id,
            scene_id=str(line.get("scene_id") or ""),
            line_id=str(line.get("id") or line_id),
            text=str(line.get("text") or ""),
            language=language,
            voice_profile=selected_voice,
        )

        variants_raw = line.get("variants")
        variants: List[Dict[str, Any]] = list(variants_raw) if isinstance(variants_raw, list) else []
        if replace_existing:
            variants = [generated]
            line["approved_variant_id"] = None
            line["approved_audio_url"] = None
        else:
            variants.append(generated)

        line["variants"] = variants
        if self._clean_text(voice_profile):
            line["voice_profile"] = self._clean_text(voice_profile)

        scene_id = str(line.get("scene_id") or "")
        if scene_id and scene_id in scenes_by_id:
            self._touch_scene_voiceover(
                scenes_by_id[scene_id],
                language=language,
                voice_profile=selected_voice,
                project_settings=project_settings,
            )

        await self.session.commit()

        return {
            "project_id": project_id,
            "graph_id": graph.id,
            "line": self._to_public_line(line),
            "summary": self._build_summary(lines),
            "settings": project_settings,
            "suggested_role_prompts": self.suggested_role_prompts,
        }

    async def generate_all_variants(
        self,
        project_id: str,
        *,
        language: str,
        default_voice_profile: Optional[str],
        replace_existing: bool,
        skip_approved: bool,
    ) -> Dict[str, Any]:
        graph, scenes_by_id, lines, project_settings = await self._prepare_graph_voiceover(project_id)

        generated_count = 0
        skipped_count = 0
        touched_scene_ids: set[str] = set()

        for line in lines:
            has_approved = bool(self._clean_text(line.get("approved_audio_url")))
            if skip_approved and has_approved and not replace_existing:
                skipped_count += 1
                continue

            selected_voice = self._resolve_line_voice_profile(
                line,
                project_settings=project_settings,
                explicit_voice_profile=None,
                default_voice_profile=self._clean_text(default_voice_profile),
            )
            generated = await self._synthesize_variant(
                project_id=project_id,
                scene_id=str(line.get("scene_id") or ""),
                line_id=str(line.get("id") or "line"),
                text=str(line.get("text") or ""),
                language=language,
                voice_profile=selected_voice,
            )

            variants_raw = line.get("variants")
            variants: List[Dict[str, Any]] = list(variants_raw) if isinstance(variants_raw, list) else []
            if replace_existing:
                variants = [generated]
                line["approved_variant_id"] = None
                line["approved_audio_url"] = None
            else:
                variants.append(generated)
            line["variants"] = variants

            if self._clean_text(default_voice_profile):
                line["voice_profile"] = self._clean_text(default_voice_profile)

            scene_id = str(line.get("scene_id") or "")
            if scene_id:
                touched_scene_ids.add(scene_id)
            generated_count += 1

        for scene_id in touched_scene_ids:
            scene = scenes_by_id.get(scene_id)
            if scene is not None:
                self._touch_scene_voiceover(
                    scene,
                    language=language,
                    voice_profile=self._clean_text(default_voice_profile),
                    project_settings=project_settings,
                )

        if touched_scene_ids:
            await self.session.commit()

        return {
            "project_id": project_id,
            "graph_id": graph.id,
            "generated_count": generated_count,
            "skipped_count": skipped_count,
            "summary": self._build_summary(lines),
            "settings": project_settings,
            "suggested_role_prompts": self.suggested_role_prompts,
        }

    async def approve_variant(
        self,
        project_id: str,
        *,
        line_id: str,
        variant_id: str,
    ) -> Dict[str, Any]:
        graph, scenes_by_id, lines, project_settings = await self._prepare_graph_voiceover(project_id)
        line = self._find_line(lines, line_id)
        if line is None:
            raise HTTPException(status_code=404, detail="Voiceover line not found")

        variants_raw = line.get("variants")
        variants: List[Dict[str, Any]] = list(variants_raw) if isinstance(variants_raw, list) else []
        selected = next((item for item in variants if str(item.get("id") or "") == variant_id), None)
        if selected is None:
            raise HTTPException(status_code=404, detail="Voiceover variant not found")

        line["approved_variant_id"] = variant_id
        line["approved_audio_url"] = selected.get("audio_url")

        scene_id = str(line.get("scene_id") or "")
        if scene_id and scene_id in scenes_by_id:
            self._touch_scene_voiceover(scenes_by_id[scene_id], project_settings=project_settings)

        await self.session.commit()

        return {
            "project_id": project_id,
            "graph_id": graph.id,
            "line": self._to_public_line(line),
            "summary": self._build_summary(lines),
            "settings": project_settings,
            "suggested_role_prompts": self.suggested_role_prompts,
        }

    async def update_settings(
        self,
        project_id: str,
        *,
        patch: Dict[str, Any],
    ) -> Dict[str, Any]:
        graph, scenes_by_id, _lines, project_settings = await self._prepare_graph_voiceover(project_id)
        next_settings = self._merge_project_settings(project_settings, patch)
        scenes = list(scenes_by_id.values())
        changed = self._apply_project_settings_to_scenes(scenes, next_settings, touch_updated=True)
        if changed:
            await self.session.commit()

        return {
            "project_id": project_id,
            "graph_id": graph.id,
            "settings": next_settings,
            "suggested_role_prompts": self.suggested_role_prompts,
            "updated_at": self._max_updated_at(graph.scenes),
        }

    async def _prepare_graph_voiceover(
        self,
        project_id: str,
    ) -> Tuple[ScenarioGraph, Dict[str, SceneNode], List[Dict[str, Any]], Dict[str, Any]]:
        graph = await self._load_latest_graph(project_id)
        character_by_id, character_by_name = await self._load_character_maps(project_id)

        scenes = self._ordered_scenes(graph)
        project_settings = self._extract_project_settings(scenes)
        scene_map = {scene.id: scene for scene in scenes}

        all_lines: List[Dict[str, Any]] = []
        changed = False
        order_counter = 0

        for scene_order, scene in enumerate(scenes, start=1):
            extracted_lines, order_counter = self._extract_scene_lines(
                scene,
                scene_order=scene_order,
                start_order=order_counter,
                character_by_id=character_by_id,
                character_by_name=character_by_name,
            )
            merged_lines, scene_changed = self._sync_scene_voiceover(scene, extracted_lines)
            all_lines.extend(merged_lines)
            changed = changed or scene_changed

        recovered = self._recover_variants_from_assets(project_id, all_lines)
        changed = changed or recovered
        all_lines.sort(key=lambda item: int(item.get("order") or 0))

        if changed:
            await self.session.commit()

        return graph, scene_map, all_lines, project_settings

    async def _load_latest_graph(self, project_id: str) -> ScenarioGraph:
        project = await self.session.get(Project, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        graph = (
            await self.session.execute(
                select(ScenarioGraph)
                .options(selectinload(ScenarioGraph.scenes))
                .where(ScenarioGraph.project_id == project_id)
                .order_by(ScenarioGraph.created_at.desc())
                .limit(1)
            )
        ).scalars().first()

        if graph is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project has no scenario graph",
            )

        return graph

    async def _load_character_maps(
        self,
        project_id: str,
    ) -> Tuple[Dict[str, CharacterPreset], Dict[str, CharacterPreset]]:
        result = await self.session.execute(
            select(CharacterPreset).where(CharacterPreset.project_id == project_id)
        )
        by_id: Dict[str, CharacterPreset] = {}
        by_name: Dict[str, CharacterPreset] = {}

        for character in result.scalars().all():
            by_id[character.id] = character
            key = self._normalize_name(character.name)
            if key and key not in by_name:
                by_name[key] = character

        return by_id, by_name

    def _ordered_scenes(self, graph: ScenarioGraph) -> List[SceneNode]:
        scenes = list(graph.scenes or [])

        def sort_key(scene: SceneNode) -> Tuple[int, int, str, str]:
            raw_index = scene.order_index if isinstance(scene.order_index, int) else 1_000_000
            has_index = 0 if isinstance(scene.order_index, int) else 1
            created = scene.created_at.isoformat() if scene.created_at else ""
            return (has_index, raw_index, created, scene.id)

        scenes.sort(key=sort_key)
        return scenes

    def _extract_scene_lines(
        self,
        scene: SceneNode,
        *,
        scene_order: int,
        start_order: int,
        character_by_id: Dict[str, CharacterPreset],
        character_by_name: Dict[str, CharacterPreset],
    ) -> Tuple[List[Dict[str, Any]], int]:
        ctx = self._scene_context(scene)
        sequence = ctx.get("sequence") if isinstance(ctx.get("sequence"), dict) else {}
        slides = sequence.get("slides") if isinstance(sequence, dict) else None

        lines: List[Dict[str, Any]] = []
        order = start_order

        if isinstance(slides, list):
            for slide_index, raw_slide in enumerate(slides):
                if not isinstance(raw_slide, dict):
                    continue

                slide_title = self._clean_text(raw_slide.get("title"))

                exposition = self._clean_text(raw_slide.get("exposition"))
                if exposition:
                    order += 1
                    lines.append(
                        {
                            "id": f"{scene.id}:s{slide_index}:exposition",
                            "scene_id": scene.id,
                            "scene_title": scene.title,
                            "scene_order": scene_order,
                            "slide_index": slide_index,
                            "slide_title": slide_title,
                            "kind": "exposition",
                            "speaker": "Narrator",
                            "character_id": None,
                            "dialogue_id": None,
                            "dialogue_index": None,
                            "voice_profile": None,
                            "text": exposition,
                            "order": order,
                            "variants": [],
                            "approved_variant_id": None,
                            "approved_audio_url": None,
                        }
                    )

                thought = self._clean_text(raw_slide.get("thought"))
                if thought:
                    order += 1
                    lines.append(
                        {
                            "id": f"{scene.id}:s{slide_index}:thought",
                            "scene_id": scene.id,
                            "scene_title": scene.title,
                            "scene_order": scene_order,
                            "slide_index": slide_index,
                            "slide_title": slide_title,
                            "kind": "thought",
                            "speaker": "Inner Voice",
                            "character_id": None,
                            "dialogue_id": None,
                            "dialogue_index": None,
                            "voice_profile": None,
                            "text": thought,
                            "order": order,
                            "variants": [],
                            "approved_variant_id": None,
                            "approved_audio_url": None,
                        }
                    )

                dialogue = raw_slide.get("dialogue")
                if not isinstance(dialogue, list):
                    continue

                for dialogue_index, raw_line in enumerate(dialogue):
                    if not isinstance(raw_line, dict):
                        continue
                    text = self._clean_text(raw_line.get("text"))
                    if not text:
                        continue

                    speaker = self._clean_text(raw_line.get("speaker")) or self._clean_text(
                        raw_line.get("speaker_name")
                    )
                    raw_character_id = self._clean_text(raw_line.get("character_id"))
                    dialogue_id = self._clean_text(raw_line.get("id"))

                    character = None
                    if raw_character_id and raw_character_id in character_by_id:
                        character = character_by_id[raw_character_id]
                    elif speaker:
                        character = character_by_name.get(self._normalize_name(speaker))

                    character_id = raw_character_id or (character.id if character else None)
                    inferred_voice_profile = self._clean_text(raw_line.get("voice_profile"))
                    if not inferred_voice_profile and character is not None:
                        inferred_voice_profile = self._clean_text(character.voice_profile)

                    line_token = self._slug(dialogue_id) if dialogue_id else str(dialogue_index)
                    order += 1
                    lines.append(
                        {
                            "id": f"{scene.id}:s{slide_index}:dialogue:{line_token}",
                            "scene_id": scene.id,
                            "scene_title": scene.title,
                            "scene_order": scene_order,
                            "slide_index": slide_index,
                            "slide_title": slide_title,
                            "kind": "dialogue",
                            "speaker": speaker or "Speaker",
                            "character_id": character_id,
                            "dialogue_id": dialogue_id,
                            "dialogue_index": dialogue_index,
                            "voice_profile": inferred_voice_profile,
                            "text": text,
                            "order": order,
                            "variants": [],
                            "approved_variant_id": None,
                            "approved_audio_url": None,
                        }
                    )

        if not lines:
            narration = self._clean_text(scene.content)
            if narration:
                order += 1
                lines.append(
                    {
                        "id": f"{scene.id}:scene_narration",
                        "scene_id": scene.id,
                        "scene_title": scene.title,
                        "scene_order": scene_order,
                        "slide_index": None,
                        "slide_title": None,
                        "kind": "scene_narration",
                        "speaker": "Narrator",
                        "character_id": None,
                        "dialogue_id": None,
                        "dialogue_index": None,
                        "voice_profile": None,
                        "text": narration,
                        "order": order,
                        "variants": [],
                        "approved_variant_id": None,
                        "approved_audio_url": None,
                    }
                )

        return lines, order

    def _sync_scene_voiceover(
        self,
        scene: SceneNode,
        extracted_lines: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], bool]:
        ctx = self._scene_context(scene)
        voiceover = ctx.get("voiceover") if isinstance(ctx.get("voiceover"), dict) else {}

        stored_lines_raw = voiceover.get("lines") if isinstance(voiceover.get("lines"), list) else []
        stored_map: Dict[str, Dict[str, Any]] = {}
        for item in stored_lines_raw:
            if not isinstance(item, dict):
                continue
            line_id = self._clean_text(item.get("id"))
            if not line_id:
                continue
            stored_map[line_id] = self._normalize_stored_line(item)

        merged_lines: List[Dict[str, Any]] = []
        for extracted in extracted_lines:
            line_id = str(extracted.get("id") or "")
            stored = stored_map.get(line_id)
            if not stored:
                merged_lines.append(extracted)
                continue

            merged = dict(extracted)
            merged["variants"] = stored.get("variants", [])
            merged["approved_variant_id"] = stored.get("approved_variant_id")
            merged["approved_audio_url"] = stored.get("approved_audio_url")

            if stored.get("voice_profile"):
                merged["voice_profile"] = stored.get("voice_profile")

            variants = merged.get("variants") if isinstance(merged.get("variants"), list) else []
            approved_variant_id = self._clean_text(merged.get("approved_variant_id"))
            if approved_variant_id:
                approved_variant = next(
                    (item for item in variants if self._clean_text(item.get("id")) == approved_variant_id),
                    None,
                )
                if approved_variant is not None:
                    merged["approved_audio_url"] = self._clean_text(approved_variant.get("audio_url"))
                else:
                    merged["approved_variant_id"] = None
                    merged["approved_audio_url"] = None
            elif not self._clean_text(merged.get("approved_audio_url")):
                merged["approved_audio_url"] = None

            merged_lines.append(merged)

        old_canonical = self._canonical_lines(stored_lines_raw)
        new_canonical = self._canonical_lines(merged_lines)
        changed = old_canonical != new_canonical

        # Always bind merged lines into scene.context.
        # _scene_context() returns a deep copy, so callers must mutate the same
        # object attached to the ORM entity to persist generate/approve changes.
        voiceover["lines"] = merged_lines
        if changed or not isinstance(stored_lines_raw, list):
            voiceover["updated_at"] = self._utc_now()
        ctx["voiceover"] = voiceover
        scene.context = ctx
        live_lines = merged_lines

        return live_lines, changed

    def _normalize_stored_line(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        normalized: Dict[str, Any] = {
            "voice_profile": self._clean_text(payload.get("voice_profile")),
            "approved_variant_id": self._clean_text(payload.get("approved_variant_id")),
            "approved_audio_url": self._clean_text(payload.get("approved_audio_url")),
            "variants": [],
        }

        variants_raw = payload.get("variants")
        if isinstance(variants_raw, list):
            for raw_variant in variants_raw:
                if not isinstance(raw_variant, dict):
                    continue
                variant_id = self._clean_text(raw_variant.get("id"))
                audio_url = self._clean_text(raw_variant.get("audio_url"))
                if not variant_id or not audio_url:
                    continue
                normalized["variants"].append(
                    {
                        "id": variant_id,
                        "audio_url": audio_url,
                        "content_type": self._clean_text(raw_variant.get("content_type")),
                        "language": self._clean_text(raw_variant.get("language")),
                        "voice_profile": self._clean_text(raw_variant.get("voice_profile")),
                        "created_at": self._clean_text(raw_variant.get("created_at")),
                    }
                )

        return normalized

    async def _synthesize_variant(
        self,
        *,
        project_id: str,
        scene_id: str,
        line_id: str,
        text: str,
        language: str,
        voice_profile: Optional[str],
    ) -> Dict[str, Any]:
        normalized_text = self._prepare_generation_text(text)
        if not normalized_text:
            raise HTTPException(status_code=400, detail="Voiceover line has empty text")

        audio_bytes, content_type = await self.preview.generate_preview(
            AIVoicePreviewRequest(
                text=normalized_text,
                voice_profile=voice_profile,
                language=language,
            )
        )

        ext = self._ext_from_mime(content_type)
        safe_id = self._slug(line_id)[:64] or "line"
        filename = f"{safe_id}_{uuid4().hex[:10]}.{ext}"

        out_dir = self.settings.generated_assets_path / "audio" / "project_voiceover" / project_id / scene_id
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / filename
        output_path.write_bytes(audio_bytes)

        audio_url = f"/api/assets/generated/audio/project_voiceover/{project_id}/{scene_id}/{filename}"
        return {
            "id": uuid4().hex,
            "audio_url": audio_url,
            "content_type": content_type,
            "language": language,
            "voice_profile": voice_profile,
            "created_at": self._utc_now(),
        }

    def _touch_scene_voiceover(
        self,
        scene: SceneNode,
        *,
        language: Optional[str] = None,
        voice_profile: Optional[str] = None,
        project_settings: Optional[Dict[str, Any]] = None,
    ) -> None:
        ctx = self._scene_context(scene)
        voiceover = ctx.get("voiceover") if isinstance(ctx.get("voiceover"), dict) else {}
        voiceover["updated_at"] = self._utc_now()

        if project_settings is not None:
            settings = dict(project_settings)
        else:
            settings = self._normalize_voiceover_settings(voiceover.get("settings"))
        if language:
            settings["language"] = language
        if voice_profile:
            settings["voice_profile"] = voice_profile
        voiceover["settings"] = self._settings_to_storage(settings)

        ctx["voiceover"] = voiceover
        scene.context = ctx

    def _resolve_line_voice_profile(
        self,
        line: Dict[str, Any],
        *,
        project_settings: Dict[str, Any],
        explicit_voice_profile: Optional[str],
        default_voice_profile: Optional[str],
    ) -> Optional[str]:
        selected = self._clean_text(explicit_voice_profile)
        if selected:
            return selected

        selected = self._clean_text(default_voice_profile)
        if selected:
            return selected

        selected = self._clean_text(line.get("voice_profile"))
        if selected:
            return selected

        selected = self._clean_text(project_settings.get("voice_profile"))
        if selected:
            return selected

        role_prompts = project_settings.get("role_prompts") if isinstance(project_settings.get("role_prompts"), dict) else {}
        kind = self._clean_text(line.get("kind")) or ""

        if kind in {"scene_narration", "exposition"}:
            return self._clean_text(role_prompts.get("narrator"))
        if kind == "thought":
            return self._clean_text(role_prompts.get("inner_voice"))
        if kind != "dialogue":
            return None

        character_prompts = (
            project_settings.get("character_prompts")
            if isinstance(project_settings.get("character_prompts"), dict)
            else {}
        )
        speaker_prompts = (
            project_settings.get("speaker_prompts")
            if isinstance(project_settings.get("speaker_prompts"), dict)
            else {}
        )

        character_id = self._clean_text(line.get("character_id"))
        if character_id:
            selected = self._clean_text(character_prompts.get(character_id))
            if selected:
                return selected

        speaker_key = self._normalize_name(self._clean_text(line.get("speaker")))
        if speaker_key:
            selected = self._clean_text(speaker_prompts.get(speaker_key))
            if selected:
                return selected

        return self._clean_text(role_prompts.get("interlocutor"))

    def _extract_project_settings(self, scenes: List[SceneNode]) -> Dict[str, Any]:
        merged = self._normalize_voiceover_settings({})
        for scene in scenes:
            ctx = self._scene_context(scene)
            voiceover = ctx.get("voiceover") if isinstance(ctx.get("voiceover"), dict) else {}
            scene_settings = self._normalize_voiceover_settings(voiceover.get("settings"))

            if not merged.get("language") and scene_settings.get("language"):
                merged["language"] = scene_settings.get("language")
            if not merged.get("voice_profile") and scene_settings.get("voice_profile"):
                merged["voice_profile"] = scene_settings.get("voice_profile")

            merged_role = merged.get("role_prompts", {})
            scene_role = scene_settings.get("role_prompts", {})
            if isinstance(merged_role, dict) and isinstance(scene_role, dict):
                for key in ("narrator", "inner_voice", "interlocutor"):
                    if not merged_role.get(key) and scene_role.get(key):
                        merged_role[key] = scene_role.get(key)

            merged_character = merged.get("character_prompts", {})
            scene_character = scene_settings.get("character_prompts", {})
            if isinstance(merged_character, dict) and isinstance(scene_character, dict):
                for key, value in scene_character.items():
                    if key not in merged_character and value:
                        merged_character[key] = value

            merged_speaker = merged.get("speaker_prompts", {})
            scene_speaker = scene_settings.get("speaker_prompts", {})
            if isinstance(merged_speaker, dict) and isinstance(scene_speaker, dict):
                for key, value in scene_speaker.items():
                    if key not in merged_speaker and value:
                        merged_speaker[key] = value

        return merged

    def _apply_project_settings_to_scenes(
        self,
        scenes: List[SceneNode],
        settings: Dict[str, Any],
        *,
        touch_updated: bool,
    ) -> bool:
        changed = False
        serialized_settings = self._settings_to_storage(settings)
        for scene in scenes:
            ctx = self._scene_context(scene)
            voiceover = ctx.get("voiceover") if isinstance(ctx.get("voiceover"), dict) else {}
            current_settings = self._normalize_voiceover_settings(voiceover.get("settings"))
            if self._canonical_settings(current_settings) != self._canonical_settings(settings):
                voiceover["settings"] = serialized_settings
                changed = True
            if touch_updated:
                voiceover["updated_at"] = self._utc_now()
                changed = True
            ctx["voiceover"] = voiceover
            scene.context = ctx
        return changed

    def _merge_project_settings(self, current: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
        merged = self._normalize_voiceover_settings(current)
        if not isinstance(patch, dict):
            return merged

        if "language" in patch:
            merged["language"] = self._clean_text(patch.get("language"))
        if "voice_profile" in patch:
            merged["voice_profile"] = self._clean_text(patch.get("voice_profile"))
        if "character_prompts" in patch:
            merged["character_prompts"] = self._normalize_character_prompt_map(patch.get("character_prompts"))
        if "speaker_prompts" in patch:
            merged["speaker_prompts"] = self._normalize_speaker_prompt_map(patch.get("speaker_prompts"))
        if "role_prompts" in patch:
            role_patch = patch.get("role_prompts") if isinstance(patch.get("role_prompts"), dict) else {}
            role_prompts = merged.get("role_prompts", {})
            if isinstance(role_prompts, dict):
                for key in ("narrator", "inner_voice", "interlocutor"):
                    if key in role_patch:
                        role_prompts[key] = self._clean_text(role_patch.get(key))

        return merged

    def _normalize_voiceover_settings(self, payload: Any) -> Dict[str, Any]:
        source = payload if isinstance(payload, dict) else {}
        return {
            "language": self._clean_text(source.get("language")),
            "voice_profile": self._clean_text(source.get("voice_profile")),
            "role_prompts": self._normalize_role_prompts(source.get("role_prompts")),
            "character_prompts": self._normalize_character_prompt_map(source.get("character_prompts")),
            "speaker_prompts": self._normalize_speaker_prompt_map(source.get("speaker_prompts")),
        }

    def _normalize_role_prompts(self, payload: Any) -> Dict[str, Optional[str]]:
        source = payload if isinstance(payload, dict) else {}
        return {
            "narrator": self._clean_text(source.get("narrator")),
            "inner_voice": self._clean_text(source.get("inner_voice")),
            "interlocutor": self._clean_text(source.get("interlocutor")),
        }

    def _normalize_character_prompt_map(self, payload: Any) -> Dict[str, str]:
        if not isinstance(payload, dict):
            return {}
        normalized: Dict[str, str] = {}
        for raw_key, raw_value in payload.items():
            key = self._clean_text(raw_key)
            value = self._clean_text(raw_value)
            if key and value:
                normalized[key] = value
        return normalized

    def _normalize_speaker_prompt_map(self, payload: Any) -> Dict[str, str]:
        if not isinstance(payload, dict):
            return {}
        normalized: Dict[str, str] = {}
        for raw_key, raw_value in payload.items():
            key = self._normalize_name(self._clean_text(raw_key))
            value = self._clean_text(raw_value)
            if key and value:
                normalized[key] = value
        return normalized

    def _settings_to_storage(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        normalized = self._normalize_voiceover_settings(settings)
        result: Dict[str, Any] = {}
        if normalized.get("language"):
            result["language"] = normalized.get("language")
        if normalized.get("voice_profile"):
            result["voice_profile"] = normalized.get("voice_profile")

        role_prompts = normalized.get("role_prompts", {})
        if isinstance(role_prompts, dict):
            compact_role = {
                key: value
                for key, value in role_prompts.items()
                if key in {"narrator", "inner_voice", "interlocutor"} and self._clean_text(value)
            }
            if compact_role:
                result["role_prompts"] = compact_role

        character_prompts = normalized.get("character_prompts", {})
        if isinstance(character_prompts, dict) and character_prompts:
            result["character_prompts"] = character_prompts

        speaker_prompts = normalized.get("speaker_prompts", {})
        if isinstance(speaker_prompts, dict) and speaker_prompts:
            result["speaker_prompts"] = speaker_prompts

        return result

    def _canonical_settings(self, payload: Dict[str, Any]) -> str:
        return json.dumps(self._settings_to_storage(payload), ensure_ascii=False, sort_keys=True)

    def _find_line(self, lines: List[Dict[str, Any]], line_id: str) -> Optional[Dict[str, Any]]:
        for line in lines:
            if str(line.get("id") or "") == line_id:
                return line
        return None

    def _build_summary(self, lines: List[Dict[str, Any]]) -> Dict[str, int]:
        total_lines = len(lines)
        generated_lines = 0
        approved_lines = 0
        total_variants = 0

        for line in lines:
            variants = line.get("variants") if isinstance(line.get("variants"), list) else []
            if variants:
                generated_lines += 1
            total_variants += len(variants)
            if self._clean_text(line.get("approved_audio_url")):
                approved_lines += 1

        return {
            "total_lines": total_lines,
            "generated_lines": generated_lines,
            "approved_lines": approved_lines,
            "total_variants": total_variants,
        }

    def _to_public_line(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        variants_raw = payload.get("variants") if isinstance(payload.get("variants"), list) else []
        variants: List[Dict[str, Any]] = []
        for raw in variants_raw:
            if not isinstance(raw, dict):
                continue
            variant_id = self._clean_text(raw.get("id"))
            audio_url = self._clean_text(raw.get("audio_url"))
            if not variant_id or not audio_url:
                continue
            variants.append(
                {
                    "id": variant_id,
                    "audio_url": audio_url,
                    "content_type": self._clean_text(raw.get("content_type")),
                    "language": self._clean_text(raw.get("language")),
                    "voice_profile": self._clean_text(raw.get("voice_profile")),
                    "created_at": self._clean_text(raw.get("created_at")),
                }
            )

        approved_variant_id = self._clean_text(payload.get("approved_variant_id"))
        approved_audio_url = self._clean_text(payload.get("approved_audio_url"))
        if approved_variant_id and not approved_audio_url:
            variant = next((item for item in variants if item["id"] == approved_variant_id), None)
            approved_audio_url = variant.get("audio_url") if variant else None

        return {
            "id": self._clean_text(payload.get("id")) or "",
            "scene_id": self._clean_text(payload.get("scene_id")) or "",
            "scene_title": self._clean_text(payload.get("scene_title")) or "",
            "scene_order": int(payload.get("scene_order") or 0),
            "slide_index": payload.get("slide_index") if isinstance(payload.get("slide_index"), int) else None,
            "slide_title": self._clean_text(payload.get("slide_title")),
            "kind": self._clean_text(payload.get("kind")) or "dialogue",
            "speaker": self._clean_text(payload.get("speaker")),
            "character_id": self._clean_text(payload.get("character_id")),
            "dialogue_id": self._clean_text(payload.get("dialogue_id")),
            "dialogue_index": payload.get("dialogue_index")
            if isinstance(payload.get("dialogue_index"), int)
            else None,
            "voice_profile": self._clean_text(payload.get("voice_profile")),
            "text": self._clean_text(payload.get("text")) or "",
            "order": int(payload.get("order") or 0),
            "variants": variants,
            "approved_variant_id": approved_variant_id,
            "approved_audio_url": approved_audio_url,
        }

    def _scene_context(self, scene: SceneNode) -> Dict[str, Any]:
        if isinstance(scene.context, dict):
            return copy.deepcopy(scene.context)
        return {}

    def _canonical_lines(self, lines: List[Any]) -> str:
        if not isinstance(lines, list):
            return "[]"
        sanitized: List[Dict[str, Any]] = []
        for item in lines:
            if not isinstance(item, dict):
                continue
            sanitized.append(self._to_public_line(item))
        return json.dumps(sanitized, ensure_ascii=False, sort_keys=True)

    def _prepare_generation_text(self, text: str) -> str:
        normalized = self._clean_text(text) or ""
        if len(normalized) <= 1900:
            return normalized
        return f"{normalized[:1897]}..."

    def _recover_variants_from_assets(
        self,
        project_id: str,
        lines: List[Dict[str, Any]],
    ) -> bool:
        root = self.settings.generated_assets_path / "audio" / "project_voiceover" / project_id
        if not root.exists() or not root.is_dir():
            return False

        changed = False
        for line in lines:
            scene_id = self._clean_text(line.get("scene_id"))
            line_id = self._clean_text(line.get("id"))
            if not scene_id or not line_id:
                continue

            scene_dir = root / scene_id
            if not scene_dir.exists() or not scene_dir.is_dir():
                continue

            prefix = f"{(self._slug(line_id)[:64] or 'line')}_"
            discovered_files = sorted(
                [
                    path
                    for path in scene_dir.iterdir()
                    if path.is_file() and path.name.startswith(prefix)
                ],
                key=lambda path: path.stat().st_mtime,
            )
            if not discovered_files:
                continue

            variants_raw = line.get("variants")
            variants: List[Dict[str, Any]] = list(variants_raw) if isinstance(variants_raw, list) else []
            known_urls = {
                self._clean_text(item.get("audio_url"))
                for item in variants
                if isinstance(item, dict) and self._clean_text(item.get("audio_url"))
            }

            for path in discovered_files:
                audio_url = (
                    f"/api/assets/generated/audio/project_voiceover/{project_id}/{scene_id}/{path.name}"
                )
                if audio_url in known_urls:
                    continue
                known_urls.add(audio_url)
                content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                created_at = datetime.utcfromtimestamp(path.stat().st_mtime).isoformat()
                variants.append(
                    {
                        "id": f"recovered_{path.stem}",
                        "audio_url": audio_url,
                        "content_type": content_type,
                        "language": self._clean_text(line.get("language")),
                        "voice_profile": self._clean_text(line.get("voice_profile")),
                        "created_at": created_at,
                    }
                )
                changed = True

            line["variants"] = variants

        return changed

    def _normalize_name(self, value: Optional[str]) -> str:
        return (value or "").strip().lower()

    def _clean_text(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _slug(self, value: str) -> str:
        token = re.sub(r"[^a-zA-Z0-9_-]+", "_", value or "")
        token = token.strip("_")
        return token or "line"

    def _utc_now(self) -> str:
        return datetime.utcnow().isoformat()

    def _max_updated_at(self, scenes: List[SceneNode]) -> Optional[str]:
        latest: Optional[str] = None
        for scene in scenes:
            ctx = scene.context if isinstance(scene.context, dict) else {}
            voiceover = ctx.get("voiceover") if isinstance(ctx.get("voiceover"), dict) else {}
            updated = self._clean_text(voiceover.get("updated_at"))
            if updated and (latest is None or updated > latest):
                latest = updated
        return latest

    def _ext_from_mime(self, content_type: str) -> str:
        ct = (content_type or "").split(";")[0].strip().lower()
        if ct in {"audio/mpeg", "audio/mp3"}:
            return "mp3"
        if ct in {"audio/wav", "audio/x-wav"}:
            return "wav"
        if ct in {"audio/ogg", "audio/opus"}:
            return "ogg"
        guessed = mimetypes.guess_extension(ct) or ".bin"
        return guessed.lstrip(".")
