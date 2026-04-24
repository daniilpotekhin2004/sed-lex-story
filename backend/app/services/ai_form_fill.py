from __future__ import annotations

import json
import logging
import math
import re
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4

import httpx
from fastapi import HTTPException, status

from app.core.config import get_settings
from app.services.character_lib import get_character_lib
from app.infra.ai_backoff import NonRetryableAIError, RetryableAIError, run_with_backoff
from app.infra.llm_client import LLMConfigError, create_chat_completion
from app.schemas.ai import AIFieldSpec, AIFormFillRequest, AIFormFillResponse

logger = logging.getLogger(__name__)

_SEQUENCE_TEXT_LIMITS = {
    "title": 160,
    "exposition": 400,
    "thought": 240,
    "user_prompt": 320,
    "visual": 320,
}

_DIALOGUE_TEXT_LIMIT = 220
_DIALOGUE_SPEAKER_LIMIT = 80
_CROWD_HINT_TERMS = (
    "crowd",
    "bystander",
    "bystanders",
    "passerby",
    "passersby",
    "pedestrian",
    "pedestrians",
    "extras",
    "background people",
    "толпа",
    "статист",
    "прохож",
    "много людей",
    "людно",
)
_CROWD_STRONG_PHRASES = (
    "background extras",
    "crowd in the background",
    "busy street with pedestrians",
    "passersby in frame",
    "статисты на фоне",
    "прохожие в кадре",
    "толпа на улице",
    "людная улица",
)
_CROWD_PRESENCE_TERMS = (
    "in frame",
    "on screen",
    "in the background",
    "behind them",
    "around them",
    "в кадре",
    "на фоне",
    "позади",
    "вокруг",
)


def _normalize_for_log(value: Any, *, max_items: int = 200, max_text: int = 40000, depth: int = 0) -> Any:
    if depth >= 8:
        return "<max_depth>"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if len(value) <= max_text:
            return value
        return value[:max_text] + f"...<truncated:{len(value) - max_text}>"
    if isinstance(value, list):
        items = value[:max_items]
        normalized = [
            _normalize_for_log(item, max_items=max_items, max_text=max_text, depth=depth + 1)
            for item in items
        ]
        if len(value) > max_items:
            normalized.append(f"<truncated_items:{len(value) - max_items}>")
        return normalized
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for idx, (key, item) in enumerate(value.items()):
            if idx >= max_items:
                normalized["<truncated_items>"] = len(value) - max_items
                break
            normalized[str(key)] = _normalize_for_log(
                item,
                max_items=max_items,
                max_text=max_text,
                depth=depth + 1,
            )
        return normalized
    try:
        return str(value)
    except Exception:
        return "<unserializable>"


def _append_sequence_debug_log(event: dict[str, Any]) -> None:
    settings = get_settings()
    if not settings.ai_sequence_debug_log_enabled:
        return
    path = settings.ai_sequence_debug_log_path
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(_normalize_for_log(event), ensure_ascii=False))
            stream.write("\n")
    except Exception:
        logger.exception("Failed to append scene sequence AI debug log to %s", path)


def _count_slides(value: Any) -> int:
    if not isinstance(value, dict):
        return 0
    slides = value.get("slides")
    if not isinstance(slides, list):
        return 0
    return len(slides)


def _extract_json(text: str) -> Dict[str, Any]:
    raw = text.strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    candidates: list[dict[str, Any]] = []
    idx = 0
    raw_len = len(raw)
    while idx < raw_len:
        start = raw.find("{", idx)
        if start < 0:
            break
        try:
            parsed, consumed = decoder.raw_decode(raw[start:])
        except json.JSONDecodeError:
            idx = start + 1
            continue
        if isinstance(parsed, dict):
            candidates.append(parsed)
        idx = start + max(consumed, 1)

    if candidates:
        for candidate in reversed(candidates):
            if isinstance(candidate.get("sequence"), dict):
                return candidate
        return candidates[-1]

    return {}


def _extract_message_text(response: dict[str, Any]) -> tuple[str, str]:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return "", "missing"
    first = choices[0] if isinstance(choices[0], dict) else {}
    message = first.get("message")
    if not isinstance(message, dict):
        return "", type(message).__name__

    content = message.get("content")
    content_type = type(content).__name__
    if isinstance(content, str):
        return content.strip(), content_type
    if content is None:
        refusal = message.get("refusal")
        if isinstance(refusal, str):
            return refusal.strip(), "refusal"
        return "", content_type
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                if item.strip():
                    parts.append(item.strip())
                continue
            if not isinstance(item, dict):
                continue

            text_value = item.get("text")
            if isinstance(text_value, str) and text_value.strip():
                parts.append(text_value.strip())
            elif isinstance(text_value, dict):
                nested_value = text_value.get("value")
                if isinstance(nested_value, str) and nested_value.strip():
                    parts.append(nested_value.strip())

            for key in ("content", "value", "output_text"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    parts.append(value.strip())

        return "\n".join(parts).strip(), content_type

    return str(content).strip(), content_type


def _normalize_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = []
        for item in value:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                items.append(text)
        return items
    if isinstance(value, str):
        parts = re.split(r"[,\n]", value)
        return [part.strip() for part in parts if part.strip()]
    return [str(value)]


def _coerce_value(spec: AIFieldSpec, value: Any, current: Any) -> Any:
    if value is None:
        return current
    field_type = (spec.type or "string").lower()

    if field_type in {"string", "text"}:
        return str(value)

    if field_type in {"number", "float"}:
        try:
            return float(value)
        except (TypeError, ValueError):
            return current

    if field_type in {"integer", "int"}:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return current

    if field_type in {"boolean", "bool"}:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "yes", "1", "on"}:
                return True
            if lowered in {"false", "no", "0", "off"}:
                return False
        return current

    if field_type == "array":
        return _normalize_list(value)

    if field_type == "object":
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                return current
        return current

    return value


def _is_empty_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, list):
        return len(value) == 0
    if isinstance(value, dict):
        if len(value) == 0:
            return True
        return all(_is_empty_value(item) for item in value.values())
    if isinstance(value, float) and math.isnan(value):
        return True
    return False


def _extract_context_character_ids(context: str | None) -> list[str]:
    text = context or ""
    if not text:
        return []
    ids: list[str] = []
    # Typical format in context: "(id: <character_id>; ...)"
    for raw in re.findall(r"\bid:\s*([A-Za-z0-9_-]{8,64})", text):
        token = str(raw).strip()
        if token and token not in ids:
            ids.append(token)
    return ids


def _context_has_crowd_hints(context: str | None) -> bool:
    text = (context or "").lower()
    if not text:
        return False
    if any(h in text for h in _CROWD_STRONG_PHRASES):
        return True
    has_hint_term = any(h in text for h in _CROWD_HINT_TERMS)
    if not has_hint_term:
        return False
    return any(h in text for h in _CROWD_PRESENCE_TERMS)


def _trim_text(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    cleaned = " ".join(value.split()).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip(" ,.;:") + "..."


def _normalize_scene_sequence_payload(
    sequence: Any,
    *,
    context: str | None,
) -> Any:
    if not isinstance(sequence, dict):
        return sequence
    slides = sequence.get("slides")
    if not isinstance(slides, list):
        return sequence

    allowed_ids = set(_extract_context_character_ids(context))
    has_crowd_hints = _context_has_crowd_hints(context)
    normalized_slides: list[dict[str, Any]] = []
    cast_tuples: list[tuple[str, ...]] = []
    cast_freq: dict[tuple[str, ...], int] = {}

    for raw_slide in slides:
        if not isinstance(raw_slide, dict):
            continue
        slide = dict(raw_slide)
        cast_raw = slide.get("cast_ids")
        cast_ids: list[str] = []
        if isinstance(cast_raw, list):
            for value in cast_raw:
                token = str(value).strip()
                if not token:
                    continue
                if allowed_ids and token not in allowed_ids:
                    continue
                if token not in cast_ids:
                    cast_ids.append(token)
        elif isinstance(cast_raw, str):
            token = cast_raw.strip()
            if token and (not allowed_ids or token in allowed_ids):
                cast_ids = [token]

        if cast_ids:
            cast_key = tuple(cast_ids)
            cast_tuples.append(cast_key)
            cast_freq[cast_key] = cast_freq.get(cast_key, 0) + 1
            slide["cast_ids"] = cast_ids
        else:
            slide["cast_ids"] = []
        normalized_slides.append(slide)

    dominant_cast: list[str] = []
    if cast_freq:
        best_cast, best_count = max(cast_freq.items(), key=lambda item: item[1])
        if best_count >= 2:
            dominant_cast = list(best_cast)
        elif cast_tuples:
            dominant_cast = list(cast_tuples[-1])

    previous_cast: list[str] = []
    for slide in normalized_slides:
        cast_ids = slide.get("cast_ids") if isinstance(slide.get("cast_ids"), list) else []
        if not cast_ids:
            # Keep cast continuity in multi-beat sequences when the model omitted cast_ids.
            if previous_cast:
                cast_ids = list(previous_cast)
            elif dominant_cast:
                cast_ids = list(dominant_cast)
            if cast_ids:
                slide["cast_ids"] = cast_ids
        if cast_ids:
            previous_cast = list(cast_ids)

        pipeline = slide.get("pipeline")
        if isinstance(pipeline, dict):
            next_pipeline = dict(pipeline)
        else:
            next_pipeline = {}
        if cast_ids:
            next_pipeline["mode"] = "controlnet"
            next_pipeline["identity_mode"] = "ip_adapter"
        else:
            next_pipeline.setdefault("mode", "standard")
        slide["pipeline"] = next_pipeline

        for key, limit in _SEQUENCE_TEXT_LIMITS.items():
            if key in slide:
                trimmed = _trim_text(slide.get(key), limit)
                if trimmed:
                    slide[key] = trimmed
                elif isinstance(slide.get(key), str):
                    slide[key] = ""

        dialogue = slide.get("dialogue")
        if isinstance(dialogue, list):
            normalized_dialogue: list[dict[str, str]] = []
            for line in dialogue:
                if not isinstance(line, dict):
                    continue
                speaker = _trim_text(line.get("speaker"), _DIALOGUE_SPEAKER_LIMIT)
                text = _trim_text(line.get("text"), _DIALOGUE_TEXT_LIMIT)
                if not text:
                    continue
                entry: dict[str, str] = {"text": text}
                if speaker:
                    entry["speaker"] = speaker
                normalized_dialogue.append(entry)
            slide["dialogue"] = normalized_dialogue

        allow_extras = bool(slide.get("allow_background_extras"))
        if allow_extras and not has_crowd_hints:
            allow_extras = False
        slide["allow_background_extras"] = allow_extras
        if allow_extras:
            count = slide.get("background_extras_count")
            if not isinstance(count, int) or count < 0:
                slide["background_extras_count"] = 1
        else:
            slide.pop("background_extras_count", None)
            slide.pop("background_extras_min", None)
            slide.pop("background_extras_max", None)
            slide.pop("background_extras_note", None)

    result = dict(sequence)
    result["slides"] = normalized_slides
    return result


def _normalize_detail_level(detail: str | None) -> str:
    detail_value = (detail or "standard").strip().lower()
    if detail_value in {"narrow", "standard", "detailed"}:
        return detail_value
    return "standard"


def _build_prompt(payload: AIFormFillRequest) -> tuple[str, str]:
    language = payload.language or "ru"
    context = payload.context.strip() if payload.context else ""
    extra = payload.extra_context.strip() if payload.extra_context else ""
    detail_level = _normalize_detail_level(payload.detail_level)
    detail_hints = {
        "narrow": "Use short, minimal phrases. Avoid extra adjectives.",
        "standard": "Use concise, practical descriptions.",
        "detailed": "Add richer descriptive detail while staying consistent with given facts.",
    }
    fill_only_empty = payload.fill_only_empty

    field_specs = [spec.dict() for spec in payload.fields]
    current_values = payload.current_values or {}

    system = (
        "You are an assistant that fills structured forms for a legal narrative platform. "
        f"Write string fields in {language}. "
        "Return only valid JSON with the requested keys. "
        "If unsure, keep the current value or return an empty string."
    )
    if fill_only_empty:
        system += " Never change non-empty fields; only fill missing or empty values."
    if payload.form_type == "scene_sequence":
        system += (
            " For scene_sequence output, return a clean JSON object only. "
            "Do not output markdown, code fences, bullet lists, commentary, analysis, or repeated filler text. "
            "Strict contract: return exactly one top-level JSON object with key 'sequence'. "
            "The value of 'sequence' must be an object containing 'slides' as an array. "
            "Each slide must contain coherent narrative text in exposition/thought/dialogue/title and must not include placeholders."
        )

    user_lines = [
        f"Form type: {payload.form_type}",
        f"Detail level: {detail_level}. {detail_hints[detail_level]}",
        "Field specs (JSON):",
        json.dumps(field_specs, ensure_ascii=False),
        "Current values (JSON):",
        json.dumps(current_values, ensure_ascii=False),
    ]
    if context:
        user_lines.append("Context:\n" + context)
    if extra:
        user_lines.append("Additional guidance:\n" + extra)
    if payload.form_type == "scene_sequence":
        user_lines.append(
            "Sequence guidance: build a slide sequence that covers the full scene. "
            "Split into multiple slides when there are multiple beats, actions, or new character appearances "
            "(aim for 3-8 slides for long scenes). Keep the order chronological. "
            "Each slide should include at least one text field (exposition, thought, or dialogue). "
            "Use exposition for off-screen narration/voiceover, thought for inner voice, and dialogue for spoken lines. "
            "Keep these separated and in chronological order. "
            "Use animation values from [fade, rise, float, none]. "
            "For each slide, you MAY include: "
            "cast_ids (array of character ids), framing (full|half|portrait), user_prompt (visual notes), "
            "allow_background_extras (boolean), background_extras_count (integer), "
            "background_extras_min/background_extras_max (integer range), background_extras_note (string), "
            "and pipeline {mode: standard|controlnet, identity_mode: ip_adapter|reference, pose_image_url?}. "
            "If cast_ids is non-empty, prefer pipeline.mode=controlnet and identity_mode=ip_adapter. "
            "By default, keep allow_background_extras=false and do not add extra people. "
            "Enable extras only when the scene explicitly needs background people/statists. "
            "If no characters are shown, omit cast_ids or set it to an empty array and use pipeline.mode=standard. "
            "Use only character ids that appear in the provided context (do not invent ids). "
            "Leave image_url empty unless a specific URL is provided."
        )
        user_lines.append(
            "Continuity lock: unless the context explicitly states a transition, keep location, time of day, weather, "
            "lighting mood, and key props consistent across adjacent slides. "
            "Keep each character's identity, age, body build, hairstyle, and wardrobe consistent across slides."
        )
        settings = get_settings()
        if settings.character_lib_enabled:
            try:
                lib = get_character_lib()
                items = lib.list_characters(page=1, page_size=30, include_public=True).items
            except Exception:
                items = []
            if items:
                user_lines.append("Prefer scene-linked characters when available; use library characters only if they fit the scene.")
                lib_lines = []
                for char in items:
                    desc = f"; {char.description}" if getattr(char, "description", None) else ""
                    prompt = f"; appearance: {char.appearance_prompt}" if getattr(char, "appearance_prompt", None) else ""
                    tags = ""
                    if getattr(char, "style_tags", None):
                        try:
                            tag_list = [str(t) for t in char.style_tags if t]
                            if tag_list:
                                tags = f"; tags: {', '.join(tag_list[:6])}"
                        except Exception:
                            pass
                    lib_lines.append(f"- {char.name} (id: {char.id}{desc}{prompt}{tags})")
                user_lines.append(
                    "Available library characters (use ids for cast_ids):\n" + "\n".join(lib_lines)
                )
    user_lines.append("Guidance: Keep new values consistent with existing data and context.")
    if payload.form_type == "scene_sequence":
        user_lines.append(
            "Strict output contract: return ONLY one JSON object with key 'sequence'. "
            "The 'sequence.slides' array must contain 3-8 slides for long scenes (at least 1 for short scenes). "
            "Every slide must have meaningful coherent text in exposition/thought/dialogue/title. "
            "No markdown, no backticks, no placeholders, no repeated fragments."
        )

    user_lines.append(
        "Return JSON object with keys exactly matching the field specs. "
        "Use arrays for type 'array', numbers for 'number', booleans for 'boolean', and objects for 'object'."
    )

    return system, "\n".join(user_lines)


class AIFormFillService:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def generate_form_fill(self, payload: AIFormFillRequest) -> AIFormFillResponse:
        system_prompt, user_prompt = _build_prompt(payload)
        is_sequence_draft = payload.form_type == "scene_sequence"
        debug_id = uuid4().hex
        llm_attempts: list[dict[str, Any]] = [{"tag": "default", "config": {}, "llm_kwargs": {}}]
        if is_sequence_draft:
            primary_model = (self.settings.ai_sequence_model or "").strip() or None
            primary_config = {
                "tag": "primary",
                "model": primary_model,
                "temperature": float(self.settings.ai_sequence_temperature),
                "top_p": float(self.settings.ai_sequence_top_p),
                "frequency_penalty": float(self.settings.ai_sequence_frequency_penalty),
                "presence_penalty": float(self.settings.ai_sequence_presence_penalty),
            }
            primary_kwargs = {
                key: value
                for key, value in {
                    "model": primary_config["model"],
                    "temperature": primary_config["temperature"],
                    "top_p": primary_config["top_p"],
                    "frequency_penalty": primary_config["frequency_penalty"],
                    "presence_penalty": primary_config["presence_penalty"],
                }.items()
                if value is not None
            }
            llm_attempts = [{"tag": "primary", "config": primary_config, "llm_kwargs": primary_kwargs}]

            fallback_model = (self.settings.ai_sequence_fallback_model or "").strip() or primary_model
            fallback_config = {
                "tag": "fallback",
                "model": fallback_model,
                "temperature": 0.7,
                "top_p": 0.9,
                "frequency_penalty": 0.0,
                "presence_penalty": 0.0,
            }
            primary_signature = (
                (primary_config["model"] or "").lower(),
                primary_config["temperature"],
                primary_config["top_p"],
                primary_config["frequency_penalty"],
                primary_config["presence_penalty"],
            )
            fallback_signature = (
                (fallback_config["model"] or "").lower(),
                fallback_config["temperature"],
                fallback_config["top_p"],
                fallback_config["frequency_penalty"],
                fallback_config["presence_penalty"],
            )
            if fallback_signature != primary_signature:
                fallback_kwargs = {
                    key: value
                    for key, value in {
                        "model": fallback_config["model"],
                        "temperature": fallback_config["temperature"],
                        "top_p": fallback_config["top_p"],
                        "frequency_penalty": fallback_config["frequency_penalty"],
                        "presence_penalty": fallback_config["presence_penalty"],
                    }.items()
                    if value is not None
                }
                llm_attempts.append(
                    {"tag": "fallback", "config": fallback_config, "llm_kwargs": fallback_kwargs}
                )
        request_snapshot = {
            "form_type": payload.form_type,
            "detail_level": payload.detail_level,
            "fill_only_empty": payload.fill_only_empty,
            "language": payload.language,
            "fields": [field.dict() for field in payload.fields],
            "current_values": payload.current_values or {},
            "context": payload.context,
            "extra_context": payload.extra_context,
            "sequence_model": self.settings.ai_sequence_model if is_sequence_draft else None,
            "sequence_fallback_model": (
                self.settings.ai_sequence_fallback_model if is_sequence_draft else None
            ),
            "sequence_temperature": self.settings.ai_sequence_temperature if is_sequence_draft else None,
            "sequence_top_p": self.settings.ai_sequence_top_p if is_sequence_draft else None,
            "sequence_frequency_penalty": self.settings.ai_sequence_frequency_penalty if is_sequence_draft else None,
            "sequence_presence_penalty": self.settings.ai_sequence_presence_penalty if is_sequence_draft else None,
            "sequence_attempts": (
                [attempt.get("config", {}) for attempt in llm_attempts] if is_sequence_draft else None
            ),
        }
        if is_sequence_draft:
            _append_sequence_debug_log(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "event": "scene_sequence_request_start",
                    "debug_id": debug_id,
                    "request": request_snapshot,
                    "system_prompt": system_prompt,
                    "user_prompt": user_prompt,
                }
            )

        async def _call_llm(llm_kwargs: dict[str, Any]) -> dict:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            try:
                return await create_chat_completion(
                    messages=messages,
                    response_format={"type": "json_object"},
                    **llm_kwargs,
                )
            except NonRetryableAIError as exc:
                text = str(exc).lower()
                if "response_format" in text and (
                    "unsupported" in text or "unknown" in text or "invalid" in text
                ):
                    logger.warning("LLM endpoint rejected response_format; retrying without json mode.")
                    return await create_chat_completion(messages=messages, **llm_kwargs)
                raise

        for attempt_index, attempt in enumerate(llm_attempts, start=1):
            llm_kwargs = dict(attempt.get("llm_kwargs") or {})
            attempt_config = dict(attempt.get("config") or {})
            attempt_meta = {
                "attempt_index": attempt_index,
                "attempt_total": len(llm_attempts),
                "attempt_tag": attempt.get("tag"),
                "attempt_model": attempt_config.get("model"),
                "attempt_temperature": attempt_config.get("temperature"),
                "attempt_top_p": attempt_config.get("top_p"),
                "attempt_frequency_penalty": attempt_config.get("frequency_penalty"),
                "attempt_presence_penalty": attempt_config.get("presence_penalty"),
            }

            if is_sequence_draft:
                _append_sequence_debug_log(
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "event": "scene_sequence_attempt_start",
                        "debug_id": debug_id,
                        **attempt_meta,
                    }
                )

            try:
                response = await run_with_backoff(
                    lambda: _call_llm(llm_kwargs),
                    retries=self.settings.llm_max_retries,
                    base_delay=self.settings.llm_backoff_base,
                    max_delay=self.settings.llm_backoff_max,
                    retry_on=(RetryableAIError, httpx.RequestError),
                )
            except LLMConfigError as exc:
                if is_sequence_draft:
                    _append_sequence_debug_log(
                        {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "event": "llm_config_error",
                            "debug_id": debug_id,
                            **attempt_meta,
                            "error_type": exc.__class__.__name__,
                            "error": str(exc),
                            "request": request_snapshot,
                            "system_prompt": system_prompt,
                            "user_prompt": user_prompt,
                        }
                    )
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
            except RetryableAIError as exc:
                has_retry_attempt = is_sequence_draft and attempt_index < len(llm_attempts)
                if is_sequence_draft:
                    _append_sequence_debug_log(
                        {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "event": "llm_retryable_error",
                            "debug_id": debug_id,
                            **attempt_meta,
                            "will_retry_with_fallback": has_retry_attempt,
                            "error_type": exc.__class__.__name__,
                            "error": str(exc),
                            "status_code": getattr(exc, "status_code", None),
                            "request": request_snapshot,
                            "system_prompt": system_prompt,
                            "user_prompt": user_prompt,
                        }
                    )
                if has_retry_attempt:
                    continue
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"LLM request failed after retries: {exc}",
                )
            except NonRetryableAIError as exc:
                has_retry_attempt = is_sequence_draft and attempt_index < len(llm_attempts)
                if is_sequence_draft:
                    _append_sequence_debug_log(
                        {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "event": "llm_non_retryable_error",
                            "debug_id": debug_id,
                            **attempt_meta,
                            "will_retry_with_fallback": has_retry_attempt,
                            "error_type": exc.__class__.__name__,
                            "error": str(exc),
                            "status_code": getattr(exc, "status_code", None),
                            "request": request_snapshot,
                            "system_prompt": system_prompt,
                            "user_prompt": user_prompt,
                        }
                    )
                if has_retry_attempt:
                    continue
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"LLM request failed: {exc}",
                )
            except httpx.RequestError as exc:
                has_retry_attempt = is_sequence_draft and attempt_index < len(llm_attempts)
                if is_sequence_draft:
                    _append_sequence_debug_log(
                        {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "event": "llm_request_error",
                            "debug_id": debug_id,
                            **attempt_meta,
                            "will_retry_with_fallback": has_retry_attempt,
                            "error_type": exc.__class__.__name__,
                            "error": str(exc),
                            "request": request_snapshot,
                            "system_prompt": system_prompt,
                            "user_prompt": user_prompt,
                        }
                    )
                if has_retry_attempt:
                    continue
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"LLM request error: {exc}")

            content, content_type = _extract_message_text(response)

            if not content:
                has_retry_attempt = is_sequence_draft and attempt_index < len(llm_attempts)
                if is_sequence_draft:
                    _append_sequence_debug_log(
                        {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "event": "llm_empty_content",
                            "debug_id": debug_id,
                            **attempt_meta,
                            "content_type": content_type,
                            "will_retry_with_fallback": has_retry_attempt,
                            "request": request_snapshot,
                            "system_prompt": system_prompt,
                            "user_prompt": user_prompt,
                            "llm_response": response,
                        }
                    )
                if has_retry_attempt:
                    continue
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="LLM returned an empty response",
                )

            parsed = _extract_json(content)
            if is_sequence_draft:
                sequence_candidate = parsed.get("sequence") if isinstance(parsed, dict) else None
                if not isinstance(sequence_candidate, dict):
                    has_retry_attempt = attempt_index < len(llm_attempts)
                    _append_sequence_debug_log(
                        {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "event": "scene_sequence_invalid_json",
                            "debug_id": debug_id,
                            **attempt_meta,
                            "will_retry_with_fallback": has_retry_attempt,
                            "request": request_snapshot,
                            "system_prompt": system_prompt,
                            "user_prompt": user_prompt,
                            "llm_response": response,
                            "llm_content": content,
                            "parsed": parsed,
                        }
                    )
                    if has_retry_attempt:
                        continue
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=f"LLM returned invalid JSON for scene sequence (debug_id={debug_id})",
                    )

            values: dict = {}
            current_values = payload.current_values or {}
            fill_only_empty = payload.fill_only_empty

            for spec in payload.fields:
                current = current_values.get(spec.key)
                preserve_current = fill_only_empty and not _is_empty_value(current)
                if (
                    preserve_current
                    and is_sequence_draft
                    and spec.key == "sequence"
                    and _count_slides(current) == 0
                ):
                    preserve_current = False
                if preserve_current:
                    values[spec.key] = current
                    continue
                raw_value = parsed.get(spec.key)
                values[spec.key] = _coerce_value(spec, raw_value, current)

            if is_sequence_draft:
                sequence_data = values.get("sequence")
                sequence_data = _normalize_scene_sequence_payload(
                    sequence_data,
                    context=payload.context,
                )
                values["sequence"] = sequence_data
                slide_count = _count_slides(sequence_data)
                if slide_count == 0:
                    has_retry_attempt = attempt_index < len(llm_attempts)
                    _append_sequence_debug_log(
                        {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "event": "scene_sequence_empty_slides",
                            "debug_id": debug_id,
                            **attempt_meta,
                            "will_retry_with_fallback": has_retry_attempt,
                            "request": request_snapshot,
                            "system_prompt": system_prompt,
                            "user_prompt": user_prompt,
                            "llm_response": response,
                            "llm_content": content,
                            "parsed": parsed,
                            "values": values,
                        }
                    )
                    if has_retry_attempt:
                        continue
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=f"LLM returned no slides for scene sequence (debug_id={debug_id})",
                    )

                _append_sequence_debug_log(
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "event": "scene_sequence_success",
                        "debug_id": debug_id,
                        **attempt_meta,
                        "slide_count": slide_count,
                        "llm_request_id": response.get("id"),
                        "model": response.get("model"),
                        "usage": response.get("usage"),
                    }
                )

            return AIFormFillResponse(
                values=values,
                model=response.get("model"),
                usage=response.get("usage"),
                request_id=response.get("id"),
            )

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM returned no valid scene sequence (debug_id={debug_id})",
        )
