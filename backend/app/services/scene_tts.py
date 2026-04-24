from __future__ import annotations

import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import get_settings
from app.domain.models import CharacterPreset, SceneNode
from app.schemas.ai import AIVoicePreviewRequest
from app.schemas.narrative_ai import NarrativeScriptLine
from app.services.voice_preview import VoicePreviewService


class SceneTTSService:
    """Generate per-line TTS audio for a SceneNode.

    Design goals:
    - Keep files under assets/generated to simplify cleanup.
    - Store results inside scene.context["tts"] so the frontend can
      reuse without re-synthesizing.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()
        self.preview = VoicePreviewService()

    async def synthesize_scene_script(
        self,
        scene_id: str,
        *,
        language: str = "ru",
        overwrite: bool = False,
        fallback_mode: str = "narration",
    ) -> Dict[str, Any]:
        scene = await self.session.get(SceneNode, scene_id)
        if scene is None:
            raise HTTPException(status_code=404, detail="Scene not found")

        ctx: Dict[str, Any] = scene.context or {}
        if not isinstance(ctx, dict):
            ctx = {}

        existing = ctx.get("tts")
        if not overwrite and isinstance(existing, dict) and existing.get("items"):
            return {
                "success": True,
                "audio_items": existing.get("items"),
                "message": "Using cached TTS assets",
            }

        script_lines = self._extract_script(ctx, scene)
        if not script_lines:
            if fallback_mode == "none":
                return {
                    "success": False,
                    "audio_items": [],
                    "message": "No script to synthesize",
                }
            # Narration fallback: synthesize the whole scene as exposition
            text = (scene.content or "").strip()
            if not text:
                return {
                    "success": False,
                    "audio_items": [],
                    "message": "Scene has no content",
                }
            script_lines = [NarrativeScriptLine(kind="exposition", text=text)]

        # Resolve all character voice profiles upfront
        voice_profiles: Dict[str, Optional[str]] = {}
        char_ids = {line.character_id for line in script_lines if line.character_id}
        if char_ids:
            result = await self.session.execute(select(CharacterPreset).where(CharacterPreset.id.in_(list(char_ids))))
            for c in result.scalars().all():
                voice_profiles[c.id] = c.voice_profile

        out_dir = self.settings.generated_assets_path / "audio" / "scene_tts" / scene_id
        out_dir.mkdir(parents=True, exist_ok=True)

        audio_items: List[Dict[str, Any]] = []
        for idx, line in enumerate(script_lines):
            voice_profile = None
            if line.character_id:
                voice_profile = voice_profiles.get(line.character_id)
            # If we still don't have a voice_profile, let the provider use its default/narrator.
            audio_bytes, content_type = await self.preview.generate_preview(
                AIVoicePreviewRequest(text=line.text, voice_profile=voice_profile, language=language)
            )

            ext = self._ext_from_mime(content_type)
            filename = f"line_{idx+1:03d}_{uuid4().hex[:8]}.{ext}"
            path = out_dir / filename
            path.write_bytes(audio_bytes)

            audio_url = f"/api/assets/generated/audio/scene_tts/{scene_id}/{filename}"
            audio_items.append(
                {
                    "index": idx,
                    "kind": line.kind,
                    "speaker_name": line.speaker_name,
                    "character_id": line.character_id,
                    "emotion": line.emotion,
                    "text": line.text,
                    "audio_url": audio_url,
                    "content_type": content_type,
                }
            )

        ctx["tts"] = {
            "language": language,
            "generated_at": datetime.utcnow().isoformat(),
            "items": audio_items,
        }
        scene.context = ctx
        await self.session.commit()
        return {
            "success": True,
            "audio_items": audio_items,
            "message": "TTS synthesized",
        }

    def _extract_script(self, ctx: Dict[str, Any], scene: SceneNode) -> List[NarrativeScriptLine]:
        raw = ctx.get("script")
        lines: List[NarrativeScriptLine] = []
        if isinstance(raw, list):
            for item in raw[:300]:
                if not isinstance(item, dict):
                    continue
                try:
                    lines.append(NarrativeScriptLine.model_validate(item))
                except Exception:
                    continue
        # Backwards-compatible: allow `slides` as a list of dicts with exposition/thought/dialogue
        if not lines and isinstance(ctx.get("slides"), list):
            for slide in ctx.get("slides")[:200]:
                if not isinstance(slide, dict):
                    continue
                for kind in ("exposition", "thought"):
                    text = slide.get(kind)
                    if isinstance(text, str) and text.strip():
                        lines.append(NarrativeScriptLine(kind=kind, text=text.strip()))
                dlg = slide.get("dialogue")
                if isinstance(dlg, list):
                    for d in dlg[:50]:
                        if not isinstance(d, dict):
                            continue
                        text = d.get("text")
                        if isinstance(text, str) and text.strip():
                            lines.append(
                                NarrativeScriptLine(
                                    kind="dialogue",
                                    text=text.strip(),
                                    speaker_name=d.get("speaker_name") or d.get("speaker"),
                                    character_id=d.get("character_id"),
                                    emotion=d.get("emotion"),
                                )
                            )
        return lines

    def _ext_from_mime(self, content_type: str) -> str:
        ct = (content_type or "").split(";")[0].strip().lower()
        if ct in {"audio/mpeg", "audio/mp3"}:
            return "mp3"
        if ct in {"audio/wav", "audio/x-wav"}:
            return "wav"
        if ct in {"audio/ogg", "audio/opus"}:
            return "ogg"
        ext = mimetypes.guess_extension(ct) or ".bin"
        return ext.lstrip(".")
