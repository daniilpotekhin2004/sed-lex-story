from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from uuid import uuid4

import httpx
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.models import CharacterPreset
from app.infra.ai_backoff import NonRetryableAIError, RetryableAIError, run_with_backoff
from app.infra.llm_client import LLMConfigError, create_chat_completion
from app.schemas.ai import AIVoicePreviewRequest
from app.services.voice_preview import VoicePreviewService


class CharacterVoiceService:
    """Generate and persist a voice sample for a CharacterPreset.

    - Uses CharacterPreset.voice_profile as a voice prompt when available.
    - If voice_profile is missing, tries to generate one via the configured LLM.
      Falls back to a deterministic heuristic if LLM is unavailable.
    - Saves output under assets/generated/entities/characters/<id>/voice.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()
        self.preview = VoicePreviewService()

    async def generate_voice_sample(
        self,
        preset_id: str,
        *,
        language: str = "ru",
        sample_text: Optional[str] = None,
        overwrite: bool = False,
    ) -> Dict[str, Any]:
        preset = await self.session.get(CharacterPreset, preset_id)
        if preset is None:
            raise HTTPException(status_code=404, detail="Character preset not found")

        # If we already generated a sample and caller doesn't want overwrite,
        # keep the latest known URL in metadata (if present).
        if not overwrite and isinstance(getattr(preset, "reference_images", None), list):
            for item in reversed(preset.reference_images or []):
                if isinstance(item, dict) and item.get("kind") == "voice_sample" and item.get("url"):
                    return {
                        "success": True,
                        "voice_profile": preset.voice_profile,
                        "audio_url": item.get("url"),
                        "message": "Using cached voice sample",
                    }

        voice_profile = (preset.voice_profile or "").strip() or None
        if voice_profile is None:
            voice_profile = await self._generate_voice_profile(preset, language=language)
            preset.voice_profile = voice_profile

        text = (sample_text or "").strip()
        if not text:
            text = self._default_sample_text(preset.name, language=language)

        audio_bytes, content_type = await self.preview.generate_preview(
            AIVoicePreviewRequest(text=text, voice_profile=voice_profile, language=language)
        )
        ext = self._ext_from_mime(content_type)

        out_dir = self.settings.generated_assets_path / "entities" / "characters" / preset_id / "voice"
        out_dir.mkdir(parents=True, exist_ok=True)
        filename = f"voice_sample_{uuid4().hex[:10]}.{ext}"
        path = out_dir / filename
        path.write_bytes(audio_bytes)
        audio_url = f"/api/assets/generated/entities/characters/{preset_id}/voice/{filename}"

        # Store as a reference item so the frontend can discover it without extra tables.
        ref_item = {
            "kind": "voice_sample",
            "url": audio_url,
            "content_type": content_type,
            "sample_text": text,
            "generated_at": datetime.utcnow().isoformat(),
        }
        refs = list(preset.reference_images or [])
        refs.append(ref_item)
        preset.reference_images = refs
        await self.session.commit()

        return {
            "success": True,
            "voice_profile": voice_profile,
            "audio_url": audio_url,
            "message": "Voice sample generated",
        }

    async def _generate_voice_profile(self, preset: CharacterPreset, *, language: str) -> str:
        # Heuristic fallback (deterministic) if LLM is not configured.
        fallback = self._heuristic_voice_profile(preset)

        system = (
            "You are a voice director. Generate a short voice profile prompt for TTS. "
            "Return ONLY JSON with one field: voice_profile. "
            "No markdown. Keep it 1-2 sentences. "
            "Focus on tone, tempo, accent (if any), emotion range, and age impression."
        )
        user = json.dumps(
            {
                "language": language,
                "character": {
                    "id": preset.id,
                    "name": preset.name,
                    "role": preset.character_type,
                    "description": preset.description,
                    "motivation": getattr(preset, "motivation", None),
                },
                "constraints": {
                    "length": "1-2 sentences",
                    "avoid": ["quotes", "new lines", "long backstory"],
                },
                "fallback": fallback,
            },
            ensure_ascii=False,
        )

        async def _call() -> dict:
            return await create_chat_completion(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.3,
                max_tokens=200,
            )

        try:
            response = await run_with_backoff(
                _call,
                retries=self.settings.llm_max_retries,
                base_delay=self.settings.llm_backoff_base,
                max_delay=self.settings.llm_backoff_max,
                retry_on=(RetryableAIError, httpx.RequestError),
            )
        except (LLMConfigError, RetryableAIError, NonRetryableAIError, httpx.RequestError):
            return fallback

        content = (
            response.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        try:
            data = json.loads(content) if content.startswith("{") else {}
        except Exception:
            data = {}
        voice_profile = str(data.get("voice_profile") or "").strip()
        return voice_profile or fallback

    def _heuristic_voice_profile(self, preset: CharacterPreset) -> str:
        role = (preset.character_type or "supporting").lower()
        base = {
            "protagonist": "Warm, confident, steady pace, clear articulation",
            "antagonist": "Controlled, slightly холодная интонация, низкий тембр, короткие паузы",
            "supporting": "Natural conversational tone, friendly, medium pace",
            "background": "Neutral voice, clear and unobtrusive, medium pace",
        }.get(role, "Neutral voice, clear articulation, medium pace")
        return f"{base}."

    def _default_sample_text(self, name: str, *, language: str) -> str:
        lang = (language or "ru").strip().lower()
        if lang.startswith("en"):
            return f"Hello. I'm {name}. We don't have much time—tell me what happened." 
        if lang.startswith("uk"):
            return f"Привіт. Я {name}. У нас мало часу — розкажи, що сталося." 
        return f"Привет. Я {name}. У нас мало времени — расскажи, что произошло." 

    def _ext_from_mime(self, content_type: str) -> str:
        ct = (content_type or "").split(";")[0].strip().lower()
        if ct in {"audio/mpeg", "audio/mp3"}:
            return "mp3"
        if ct in {"audio/wav", "audio/x-wav"}:
            return "wav"
        if ct in {"audio/ogg", "audio/opus"}:
            return "ogg"
        return "bin"
