from __future__ import annotations

import asyncio
import base64
import logging
import mimetypes
import random
from pathlib import Path
from typing import Optional, Tuple

import httpx
from fastapi import HTTPException, status

from app.core.config import get_settings
from app.infra.comfy_client import ComfySdClient
from app.infra.sd_client import build_sd_client
from app.schemas.ai import AIVoicePreviewRequest

logger = logging.getLogger(__name__)


class VoicePreviewService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _resolve_config(self) -> Tuple[str, str, str]:
        base_url = (self.settings.tts_base_url or self.settings.openai_base_url or "").rstrip("/")
        api_key = self.settings.tts_api_key or self.settings.openai_api_key
        model = self.settings.tts_model or self.settings.openai_model
        if not base_url or not api_key or not model:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "TTS is not configured. Set TTS_BASE_URL/TTS_API_KEY and TTS_MODEL "
                    "(or OPENAI_BASE_URL/OPENAI_API_KEY/OPENAI_MODEL fallback)."
                ),
            )
        endpoint = self.settings.tts_endpoint or "/audio/speech"
        url = endpoint if endpoint.startswith("http") else f"{base_url}/{endpoint.lstrip('/')}"
        return url, api_key, model

    def _resolve_comfy_workflow_path(self) -> Optional[Path]:
        raw = (self.settings.tts_comfy_workflow_path or "").strip()
        if not raw:
            return None
        candidate = Path(raw)
        if not candidate.is_absolute():
            backend_dir = Path(__file__).resolve().parents[2]
            candidate = (backend_dir / candidate).resolve()
        return candidate

    def _resolve_comfy_output_nodes(self) -> Optional[list[str]]:
        raw = (self.settings.tts_comfy_output_nodes or "").strip()
        if not raw:
            return None
        nodes = [part.strip() for part in raw.split(",") if part.strip()]
        return nodes or None

    def _normalize_qwen_language(self, value: str) -> str:
        token = value.strip().lower()
        mapping = {
            "ru": "Russian",
            "russian": "Russian",
            "en": "English",
            "english": "English",
            "zh": "Chinese",
            "chinese": "Chinese",
            "ja": "Japanese",
            "japanese": "Japanese",
            "ko": "Korean",
            "korean": "Korean",
            "es": "Spanish",
            "spanish": "Spanish",
            "fr": "French",
            "french": "French",
            "de": "German",
            "german": "German",
            "it": "Italian",
            "italian": "Italian",
        }
        return mapping.get(token, value.strip())

    def _guess_audio_content_type(self, output_item: dict) -> str:
        filename = (
            output_item.get("filename")
            or output_item.get("name")
            or output_item.get("path")
            or ""
        )
        suffix = Path(str(filename)).suffix.lower()
        if suffix in {".flac"}:
            return "audio/flac"
        if suffix in {".wav"}:
            return "audio/wav"
        if suffix in {".ogg"}:
            return "audio/ogg"
        if suffix in {".mp3"}:
            return "audio/mpeg"
        guessed = mimetypes.guess_type(str(filename))[0]
        if guessed and guessed.startswith("audio/"):
            return guessed
        return "audio/mpeg"

    def _apply_comfy_voice_inputs(self, workflow: dict, payload: AIVoicePreviewRequest) -> None:
        text = payload.text.strip()
        if not text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Preview text is required.",
            )

        explicit_voice = payload.voice_profile.strip() if payload.voice_profile else ""
        fallback_voice = (self.settings.tts_voice or "").strip()
        voice_prompt = explicit_voice or fallback_voice

        text_node_id = (self.settings.tts_comfy_text_node_id or "").strip()
        voice_node_id = (self.settings.tts_comfy_voice_node_id or "").strip()

        text_applied = False
        voice_applied = not bool(voice_prompt)

        for node_id, node in workflow.items():
            if not isinstance(node, dict):
                continue
            class_type = str(node.get("class_type") or "")
            inputs = node.get("inputs")
            if not isinstance(inputs, dict):
                continue

            if class_type == "PrimitiveStringMultiline":
                meta = node.get("_meta") if isinstance(node.get("_meta"), dict) else {}
                title = str(meta.get("title") or "").strip().lower()
                node_id_str = str(node_id)

                if node_id_str == text_node_id or title in {"speech", "text", "prompt", "utterance"}:
                    inputs["value"] = text
                    text_applied = True
                    continue

                if voice_prompt and (
                    node_id_str == voice_node_id
                    or title in {"voiceprompt", "voice prompt", "voice", "instruct", "style"}
                ):
                    inputs["value"] = voice_prompt
                    voice_applied = True
                    continue

            if class_type == "FB_Qwen3TTSVoiceDesign":
                if payload.language:
                    inputs["language"] = self._normalize_qwen_language(payload.language)

                if self.settings.tts_comfy_model_choice:
                    inputs["model_choice"] = self.settings.tts_comfy_model_choice

                if self.settings.tts_comfy_seed is not None:
                    inputs["seed"] = self.settings.tts_comfy_seed
                elif "seed" in inputs:
                    inputs["seed"] = random.randint(1, 2**63 - 1)

        if not text_applied:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "Comfy voice workflow does not contain a text input node. "
                    "Configure TTS_COMFY_TEXT_NODE_ID or check workflow node titles."
                ),
            )
        if voice_prompt and not voice_applied:
            logger.warning("Voice prompt was provided but no matching node found in Comfy workflow.")

    def _run_comfy_voice_preview(
        self,
        payload: AIVoicePreviewRequest,
        workflow_path: Path,
    ) -> Tuple[bytes, str]:
        if not workflow_path.exists():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Comfy voice workflow not found: {workflow_path}",
            )

        client = build_sd_client()
        if not isinstance(client, ComfySdClient):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "Comfy voice workflow requires Comfy SD provider. "
                    "Set SD_PROVIDER to comfy or comfy_api."
                ),
            )

        workflow, output_nodes = client.load_workflow(
            str(workflow_path),
            output_nodes=self._resolve_comfy_output_nodes(),
        )
        if not output_nodes:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "Comfy voice workflow has no output nodes. "
                    "Add SaveAudio/PreviewAudio or set TTS_COMFY_OUTPUT_NODES."
                ),
            )

        self._apply_comfy_voice_inputs(workflow, payload)
        outputs_by_node = client.run_workflow_outputs(workflow, output_nodes)

        for output_items in outputs_by_node:
            if not output_items:
                continue
            content_type = self._guess_audio_content_type(output_items[0])
            output_bytes = client.fetch_outputs(output_items)
            if output_bytes:
                return output_bytes[0], content_type

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Comfy voice workflow finished without audio output.",
        )

    async def _generate_preview_remote(self, payload: AIVoicePreviewRequest) -> Tuple[bytes, str]:
        url, api_key, model = self._resolve_config()
        text = payload.text.strip()
        if not text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Preview text is required.",
            )
        request_payload = {
            "model": model,
            "input": text,
        }
        format_field = self.settings.tts_format_field or "response_format"
        if self.settings.tts_format:
            request_payload[format_field] = self.settings.tts_format

        voice_profile = payload.voice_profile.strip() if payload.voice_profile else ""
        if self.settings.tts_voice:
            request_payload["voice"] = self.settings.tts_voice
        elif self.settings.tts_use_voice_profile and voice_profile:
            request_payload["voice"] = voice_profile

        if self.settings.tts_voice_prompt_field and voice_profile:
            request_payload[self.settings.tts_voice_prompt_field] = voice_profile
        if self.settings.tts_language_field and payload.language:
            request_payload[self.settings.tts_language_field] = payload.language

        timeout = self.settings.tts_timeout_seconds or self.settings.llm_timeout_seconds or 30.0
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                json=request_payload,
            )

        if response.status_code >= 400:
            preview = (response.text or "").strip()
            if len(preview) > 300:
                preview = f"{preview[:300]}..."
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    f"TTS request failed with {response.status_code} "
                    f"(model={model}, url={url}): {preview}"
                ),
            )

        content_type = response.headers.get("content-type", "")
        if content_type.startswith("application/json"):
            try:
                data = response.json()
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="TTS response was not valid JSON.",
                ) from exc
            audio_b64 = data.get("audio") or data.get("audio_base64") or data.get("data")
            if not audio_b64:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="TTS response did not include audio data.",
                )
            try:
                audio_bytes = base64.b64decode(audio_b64)
            except (TypeError, ValueError) as exc:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="TTS audio payload was not valid base64.",
                ) from exc
            resolved_type = (
                data.get("content_type")
                or data.get("mime_type")
                or data.get("contentType")
                or "audio/mpeg"
            )
            return audio_bytes, resolved_type

        if not content_type.startswith("audio/"):
            content_type = "audio/mpeg"

        return response.content, content_type

    async def generate_preview(self, payload: AIVoicePreviewRequest) -> Tuple[bytes, str]:
        provider = (self.settings.tts_provider or "auto").strip().lower()
        workflow_path = self._resolve_comfy_workflow_path()
        comfy_provider = provider in {"comfy", "comfy_workflow", "workflow", "comfy_api"}

        if comfy_provider or (provider == "auto" and workflow_path is not None):
            if workflow_path is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="TTS_COMFY_WORKFLOW_PATH is required for Comfy workflow TTS provider.",
                )
            return await asyncio.to_thread(self._run_comfy_voice_preview, payload, workflow_path)

        return await self._generate_preview_remote(payload)
