from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from uuid import uuid4
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from difflib import SequenceMatcher

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import PROJECT_ROOT, get_settings
from app.domain.models import (
    Artifact,
    CharacterPreset,
    LegalConcept,
    Location,
    Project,
    SceneNodeCharacter,
    User,
    WizardSession,
)
from app.infra.ai_backoff import NonRetryableAIError, RetryableAIError, run_with_backoff
from app.infra.llm_client import LLMConfigError, create_chat_completion
from app.schemas.wizard import (
    Step1Data,
    Step2Data,
    Step3Data,
    Step4Data,
    Step5Data,
    Step6Data,
    Step7Data,
    StoryInput,
    WizardDeployResponse,
    WizardExportPackage,
    WizardIssue,
    WizardMeta,
    WizardSessionCreateRequest,
    WizardSessionUpdateRequest,
    WizardStepApproveRequest,
    WizardStep7DeployOverrideRequest,
    WizardStepRunRequest,
)
from app.schemas.projects import ProjectCreate
from app.services.character_lib import get_character_lib
from app.services.character import CharacterService
from app.services.projects import ProjectService
from app.services.scenario import ScenarioService
from app.services.world import WorldService
from app.schemas.scenario import EdgeCreate, SceneNodeCreate, ScenarioGraphCreate
from app.schemas.world import LocationCreate
from app.infra.repositories.character import CharacterPresetRepository


logger = logging.getLogger(__name__)


StepModelMap = {
    1: Step1Data,
    2: Step2Data,
    3: Step3Data,
    4: Step4Data,
    5: Step5Data,
    6: Step6Data,
    7: Step7Data,
}


def _extract_json(text: str) -> Dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {}
    return {}


def _normalize_detail_level(detail: Optional[str]) -> str:
    value = (detail or "standard").strip().lower()
    return value if value in {"narrow", "standard", "detailed"} else "standard"


def _safe_str(value: Any, *, max_len: int = 800) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def _split_list(value: Optional[str]) -> List[str]:
    if not value:
        return []
    parts = re.split(r"[,\n;]+", value)
    return [item.strip() for item in parts if item.strip()]


def _normalize_match_text(value: Optional[str]) -> str:
    raw = (value or "").casefold().replace("ё", "е")
    if not raw:
        return ""
    raw = re.sub(r"[\"'«»()\\[\\]{}]", " ", raw)
    raw = re.sub(r"[^0-9a-zа-я]+", " ", raw)
    return re.sub(r"\s+", " ", raw).strip()


def _tokenize_match_text(value: Optional[str]) -> List[str]:
    normalized = _normalize_match_text(value)
    if not normalized:
        return []
    return [token for token in normalized.split() if len(token) > 2]


def _name_similarity(left: Optional[str], right: Optional[str]) -> float:
    left_norm = _normalize_match_text(left)
    right_norm = _normalize_match_text(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm == right_norm:
        return 1.0
    if left_norm in right_norm or right_norm in left_norm:
        return 0.93
    return SequenceMatcher(None, left_norm, right_norm).ratio()


def _desc_similarity(left: Optional[str], right: Optional[str]) -> float:
    left_tokens = set(_tokenize_match_text(left))
    right_tokens = set(_tokenize_match_text(right))
    if not left_tokens or not right_tokens:
        return 0.0
    common = len(left_tokens & right_tokens)
    if common == 0:
        return 0.0
    return common / min(len(left_tokens), len(right_tokens))


def _character_asset_payload(asset: Any, source: str) -> Dict[str, Any]:
    return {
        "id": getattr(asset, "id", None),
        "name": getattr(asset, "name", None),
        "source": source,
        "description": _safe_str(getattr(asset, "description", None), max_len=320) or "",
        "appearance_prompt": _safe_str(getattr(asset, "appearance_prompt", None), max_len=240) or "",
        "style_tags": getattr(asset, "style_tags", None) or [],
        "character_type": getattr(asset, "character_type", None),
    }


def _score_character_match(
    ch_name: str,
    ch_summary: str,
    ch_role: str,
    asset: Dict[str, Any],
    requested_names: set[str],
) -> Tuple[float, float, float]:
    name_sim = _name_similarity(ch_name, asset.get("name"))
    desc_blob = " ".join(
        [
            ch_summary or "",
            ch_role or "",
        ]
    )
    asset_blob = " ".join(
        [
            asset.get("description") or "",
            asset.get("appearance_prompt") or "",
            " ".join(asset.get("style_tags") or []),
        ]
    )
    desc_sim = _desc_similarity(desc_blob, asset_blob)
    score = name_sim * 0.8 + desc_sim * 0.2
    # Boost strong name matches so exact/partial name hits are not ignored.
    if name_sim >= 0.98:
        score = max(score, 0.93)
    elif name_sim >= 0.92:
        score = max(score, 0.86)
    asset_name_norm = _normalize_match_text(asset.get("name"))
    if asset_name_norm and asset_name_norm in requested_names:
        score += 0.08
    ch_name_norm = _normalize_match_text(ch_name)
    if ch_name_norm and ch_name_norm in requested_names:
        score += 0.05
    if asset.get("source") == "project":
        score += 0.02
    return score, name_sim, desc_sim


def _apply_character_asset_matches(
    step1: Step1Data,
    project_characters: List[CharacterPreset],
    library_characters: List[Any],
    requested_names: List[str],
) -> Step1Data:
    assets: List[Dict[str, Any]] = []
    for asset in project_characters:
        payload = _character_asset_payload(asset, "project")
        if payload.get("id"):
            assets.append(payload)
    for asset in library_characters:
        payload = _character_asset_payload(asset, "library")
        if payload.get("id"):
            assets.append(payload)

    if not assets:
        return step1

    requested_norm = {_normalize_match_text(name) for name in requested_names if _normalize_match_text(name)}
    asset_by_id = {asset["id"]: asset for asset in assets if asset.get("id")}

    for ch in step1.characters:
        if ch.status == "rejected":
            continue
        if ch.existing_asset_id and ch.existing_asset_id in asset_by_id:
            ch.source = "existing"
            continue
        if ch.existing_asset_id and ch.existing_asset_id not in asset_by_id:
            ch.existing_asset_id = None
            if ch.source == "existing":
                ch.source = "new"

        candidates: List[Tuple[float, float, float, Dict[str, Any]]] = []
        for asset in assets:
            if not asset.get("name"):
                continue
            score, name_sim, desc_sim = _score_character_match(
                ch.name or "", ch.summary or "", ch.role or "", asset, requested_norm
            )
            if score <= 0:
                continue
            candidates.append((score, name_sim, desc_sim, asset))

        if not candidates:
            continue

        candidates.sort(key=lambda item: item[0], reverse=True)
        best_score, best_name_sim, _best_desc_sim, best_asset = candidates[0]
        second_score = candidates[1][0] if len(candidates) > 1 else None

        if best_score < 0.82:
            continue
        if second_score is not None and best_score < 0.92 and (best_score - second_score) < 0.05:
            if not ch.notes:
                ch.notes = f"Возможное совпадение: {best_asset.get('name')}"
            continue

        ch.existing_asset_id = best_asset.get("id")
        ch.source = "existing"
        asset_name = best_asset.get("name") or ch.name
        note_prefix = "Автосопоставление"
        if best_asset.get("source") == "library":
            note_prefix = "Автосопоставление с библиотекой"
        elif best_asset.get("source") == "project":
            note_prefix = "Автосопоставление с проектом"
        if not ch.notes:
            ch.notes = f"{note_prefix}: {asset_name}"
        if best_name_sim >= 0.92 and asset_name:
            ch.name = asset_name

    return step1


def _normalize_character_type(value: Optional[str], fallback_role: Optional[str] = None) -> str:
    raw = (value or "").strip().lower()
    if raw in {"protagonist", "antagonist", "supporting", "background"}:
        return raw
    role = (fallback_role or "").strip().lower()
    if "герой" in role or "протагонист" in role:
        return "protagonist"
    if "антагонист" in role:
        return "antagonist"
    if "фон" in role:
        return "background"
    if "второстеп" in role:
        return "supporting"
    return "supporting"


def _first_sentence(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", raw)
    return (parts[0] if parts else raw).strip()


def _issue(
    code: str,
    message: str,
    *,
    field: Optional[str] = None,
    severity: str = "medium",
    hint: Optional[str] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"code": code, "message": message, "severity": severity}
    if field:
        payload["field"] = field
    if hint:
        payload["hint"] = hint
    return payload


def _unwrap_data(payload: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload


def _map_character_role(raw_role: Optional[str]) -> str:
    value = (raw_role or "").strip().lower()
    if value == "protagonist":
        return "главный герой"
    if value == "antagonist":
        return "антагонист"
    if value == "background":
        return "фоновый персонаж"
    if value == "supporting":
        return "второстепенный персонаж"
    return raw_role or "персонаж"


def _appearance_from_profile(profile: Any) -> Dict[str, Optional[str]]:
    if not isinstance(profile, dict):
        return {}
    return {
        "age_group": _safe_str(profile.get("age") or profile.get("age_group"), max_len=120) or None,
        "build": _safe_str(profile.get("build"), max_len=120) or None,
        "face_traits": _safe_str(profile.get("face") or profile.get("face_traits"), max_len=160) or None,
        "hair": _safe_str(profile.get("hair"), max_len=160) or None,
        "accessories": _safe_str(profile.get("accessories"), max_len=160) or None,
        "outfit": _safe_str(profile.get("outfit"), max_len=160) or None,
        "palette": _safe_str(profile.get("palette"), max_len=160) or None,
        "distinctive_features": _safe_str(
            profile.get("distinctive") or profile.get("distinctive_features"), max_len=160
        )
        or None,
        "demeanor": _safe_str(profile.get("demeanor"), max_len=160) or None,
    }


def _fallback_step1(
    *,
    story_input: StoryInput,
    project_characters: List[CharacterPreset],
    project_locations: List[Location],
    legal_concepts: List[LegalConcept],
    library_characters: List[Any],
    max_scenes: Optional[int],
) -> Step1Data:
    characters: List[Dict[str, Any]] = []
    locations: List[Dict[str, Any]] = []
    scenes: List[Dict[str, Any]] = []
    legal_topics: List[Dict[str, Any]] = []

    existing_assets = story_input.existing_assets
    requested_chars = existing_assets.characters if existing_assets else []
    requested_locations = existing_assets.locations if existing_assets else []

    asset_name_map: Dict[str, Any] = {}
    for item in list(project_characters) + list(library_characters):
        name = getattr(item, "name", None)
        if name:
            asset_name_map[name.strip().casefold()] = item

    used_names: set[str] = set()
    char_idx = 1

    def add_character(
        name: str,
        *,
        summary: str,
        role: str,
        source: str,
        existing_asset_id: Optional[str] = None,
        confidence: float = 0.45,
        notes: Optional[str] = None,
    ) -> str:
        nonlocal char_idx
        cid = f"c{char_idx}"
        char_idx += 1
        characters.append(
            {
                "id": cid,
                "name": name,
                "summary": summary or "Описание уточняется.",
                "role": role or "персонаж",
                "confidence": confidence,
                "status": "draft",
                "source": source,
                "existing_asset_id": existing_asset_id,
                "notes": notes,
            }
        )
        used_names.add(name.casefold())
        return cid

    # Respect explicit asset hints first
    for name in requested_chars[:8]:
        clean = name.strip()
        if not clean or clean.casefold() in used_names:
            continue
        asset = asset_name_map.get(clean.casefold())
        if asset is not None:
            summary = _safe_str(getattr(asset, "description", None) or "", max_len=220)
            role = _map_character_role(getattr(asset, "character_type", None))
            add_character(
                clean,
                summary=summary or "Персонаж из существующей библиотеки.",
                role=role,
                source="existing",
                existing_asset_id=getattr(asset, "id", None),
                confidence=0.75,
                notes="Подтвержден как существующий актив.",
            )
        else:
            add_character(
                clean,
                summary="Указан автором.",
                role="персонаж",
                source="new",
                confidence=0.35,
                notes="Требуется подтверждение.",
            )

    # Add a couple of existing assets if nothing was specified
    if not characters:
        for asset in list(project_characters)[:2]:
            name = _safe_str(asset.name, max_len=60) or "Персонаж"
            if name.casefold() in used_names:
                continue
            add_character(
                name,
                summary=_safe_str(asset.description or asset.appearance_prompt, max_len=220),
                role=_map_character_role(asset.character_type),
                source="existing",
                existing_asset_id=asset.id,
                confidence=0.8,
            )

    if not characters:
        add_character(
            "Главный герой",
            summary=_safe_str(_first_sentence(story_input.story_text), max_len=220) or "Главный герой истории.",
            role="главный герой",
            source="new",
            confidence=0.3,
        )

    loc_name_map: Dict[str, Any] = {}
    for loc in project_locations:
        if loc.name:
            loc_name_map[loc.name.strip().casefold()] = loc

    loc_idx = 1

    def add_location(
        name: str,
        *,
        summary: str,
        source: str,
        existing_asset_id: Optional[str] = None,
        confidence: float = 0.45,
        notes: Optional[str] = None,
    ) -> str:
        nonlocal loc_idx
        lid = f"l{loc_idx}"
        loc_idx += 1
        locations.append(
            {
                "id": lid,
                "name": name,
                "summary": summary or "Локация уточняется.",
                "confidence": confidence,
                "status": "draft",
                "source": source,
                "existing_asset_id": existing_asset_id,
                "notes": notes,
                "tags": [],
            }
        )
        return lid

    for name in requested_locations[:8]:
        clean = name.strip()
        if not clean:
            continue
        asset = loc_name_map.get(clean.casefold())
        if asset is not None:
            add_location(
                clean,
                summary=_safe_str(asset.description or asset.visual_reference, max_len=240),
                source="existing",
                existing_asset_id=asset.id,
                confidence=0.7,
                notes="Указан автором.",
            )
        else:
            add_location(
                clean,
                summary="Указана автором.",
                source="new",
                confidence=0.35,
                notes="Требуется подтверждение.",
            )

    if not locations and project_locations:
        for loc in project_locations[:2]:
            add_location(
                _safe_str(loc.name, max_len=80) or "Локация",
                summary=_safe_str(loc.description or loc.visual_reference, max_len=240),
                source="existing",
                existing_asset_id=loc.id,
                confidence=0.8,
            )

    if not locations:
        add_location(
            "Основная локация",
            summary="Ключевое место событий.",
            source="new",
            confidence=0.3,
        )

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", story_input.story_text or "") if s.strip()]
    if not sentences:
        sentences = [_safe_str(story_input.story_text, max_len=200) or "Событие развивается."]
    target_scenes = max_scenes or min(5, max(1, len(sentences)))
    target_scenes = max(1, min(target_scenes, 10))
    location_id = locations[0]["id"] if locations else None
    cast_ids = [c["id"] for c in characters[:2]]
    for idx in range(target_scenes):
        summary = sentences[idx] if idx < len(sentences) else sentences[-1]
        scenes.append(
            {
                "id": f"s{idx + 1}",
                "title": f"Сцена {idx + 1}",
                "summary": _safe_str(summary, max_len=260) or "Сцена уточняется.",
                "location_id": location_id,
                "cast_ids": cast_ids,
                "confidence": 0.35,
                "status": "draft",
            }
        )

    legal_config = story_input.legal_topics
    required_topics = legal_config.required if legal_config else []
    optional_topics = legal_config.optional if legal_config else []
    auto_gen = legal_config.auto_generate_if_empty if legal_config else True

    topic_idx = 1
    for title in required_topics[:6]:
        legal_topics.append(
            {
                "id": f"t{topic_idx}",
                "title": title,
                "summary": "Требуется раскрыть в сюжете.",
                "status": "draft",
            }
        )
        topic_idx += 1

    if not legal_topics and optional_topics:
        for title in optional_topics[:6]:
            legal_topics.append(
                {
                    "id": f"t{topic_idx}",
                    "title": title,
                    "summary": "Можно раскрыть в сюжете.",
                    "status": "draft",
                }
            )
            topic_idx += 1

    if not legal_topics and auto_gen:
        if legal_concepts:
            for concept in legal_concepts[:3]:
                legal_topics.append(
                    {
                        "id": f"t{topic_idx}",
                        "title": concept.title,
                        "summary": _safe_str(concept.description, max_len=240) or "Правовой аспект.",
                        "status": "draft",
                    }
                )
                topic_idx += 1
        else:
            for title in ["Права и обязанности", "Ответственность", "Процедуры и сроки"]:
                legal_topics.append(
                    {
                        "id": f"t{topic_idx}",
                        "title": title,
                        "summary": "Базовый правовой вопрос.",
                        "status": "draft",
                    }
                )
                topic_idx += 1

    return Step1Data.model_validate(
        {
            "characters": characters,
            "locations": locations,
            "scenes": scenes,
            "legal_topics": legal_topics,
        }
    )


def _fallback_step2(
    *,
    step1: Step1Data,
    character_assets: Dict[str, Any],
    location_assets: Dict[str, Any],
) -> Step2Data:
    characters: List[Dict[str, Any]] = []
    locations: List[Dict[str, Any]] = []

    for ch in step1.characters:
        if ch.status == "rejected":
            continue
        asset = character_assets.get(ch.existing_asset_id or "")
        description = (
            _safe_str(getattr(asset, "description", None), max_len=500)
            or _safe_str(ch.summary, max_len=380)
        )
        prompt = _safe_str(getattr(asset, "appearance_prompt", None), max_len=500) or description
        negative_prompt = _safe_str(getattr(asset, "negative_prompt", None), max_len=300) or None
        appearance_profile = _appearance_from_profile(getattr(asset, "appearance_profile", None))
        appearance = {
            "age_group": ch.age or appearance_profile.get("age_group"),
            "build": appearance_profile.get("build"),
            "face_traits": appearance_profile.get("face_traits"),
            "hair": appearance_profile.get("hair"),
            "accessories": appearance_profile.get("accessories"),
            "outfit": appearance_profile.get("outfit"),
            "palette": appearance_profile.get("palette"),
            "distinctive_features": appearance_profile.get("distinctive_features"),
            "demeanor": appearance_profile.get("demeanor"),
        }

        characters.append(
            {
                "id": ch.id,
                "source": ch.source,
                "existing_asset_id": ch.existing_asset_id,
                "name": ch.name,
                "description": description or "Описание уточняется.",
                "role": ch.role,
                "character_type": getattr(asset, "character_type", None),
                "appearance": appearance,
                "voice_profile": _safe_str(getattr(asset, "voice_profile", None), max_len=240) or None,
                "motivation": _safe_str(getattr(asset, "motivation", None), max_len=240) or None,
                "legal_status": _safe_str(getattr(asset, "legal_status", None), max_len=120) or None,
                "competencies": _safe_str(getattr(asset, "competencies", None), max_len=240) or None,
                "style_tags": _safe_str(getattr(asset, "style_tags", None), max_len=240) or None,
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "status": "draft",
                "notes": ch.notes,
            }
        )

    for loc in step1.locations:
        if loc.status == "rejected":
            continue
        asset = location_assets.get(loc.existing_asset_id or "")
        description = (
            _safe_str(getattr(asset, "description", None), max_len=500)
            or _safe_str(loc.summary, max_len=380)
        )
        visual_reference = (
            _safe_str(getattr(asset, "visual_reference", None), max_len=400) or description
        )
        negative_prompt = _safe_str(getattr(asset, "negative_prompt", None), max_len=240) or None
        locations.append(
            {
                "id": loc.id,
                "source": loc.source,
                "existing_asset_id": loc.existing_asset_id,
                "name": loc.name,
                "description": description or "Описание уточняется.",
                "location_type": loc.type,
                "tags": ", ".join(loc.tags) if loc.tags else None,
                "visual_reference": visual_reference or loc.name,
                "negative_prompt": negative_prompt,
                "status": "draft",
                "notes": loc.notes,
            }
        )

    return Step2Data.model_validate({"characters": characters, "locations": locations})


def _fallback_step3(
    *,
    step1: Step1Data,
    detail_level: str,
) -> Step3Data:
    scenes_payload: List[Dict[str, Any]] = []
    char_name_map = {c.id: c.name for c in step1.characters}

    slide_count = {"narrow": 1, "standard": 2, "detailed": 3}[detail_level]
    for scene in step1.scenes:
        slides: List[Dict[str, Any]] = []
        for idx in range(slide_count):
            slide_id = f"{scene.id}_{idx + 1}"
            exposition = scene.summary if idx == 0 else None
            dialogue: List[Dict[str, Any]] = []
            if idx == 0 and scene.cast_ids:
                speaker_id = scene.cast_ids[0]
                speaker = char_name_map.get(speaker_id, speaker_id)
                dialogue.append(
                    {
                        "speaker": speaker,
                        "text": "Нужно разобраться в ситуации.",
                    }
                )
            visual = _safe_str(scene.summary, max_len=320)
            framing = "full" if idx == 0 else ("half" if idx == 1 else "portrait")
            framing_hint = {
                "full": "full body shot, showing entire figure",
                "half": "waist-up shot, half body",
                "portrait": "close-up portrait, head and shoulders",
            }.get(framing, "full body shot")
            visual_lc = (visual or "").lower()
            gritty = any(
                token in visual_lc
                for token in (
                    "mud",
                    "dirt",
                    "grime",
                    "filth",
                    "sweat",
                    "blood",
                    "nsfw",
                    "nude",
                    "naked",
                    "sex",
                    "erotic",
                    "гряз",
                    "мокр",
                    "пот",
                    "кров",
                    "обнажен",
                    "эрот",
                    "секс",
                )
            )
            composition_prompt = None
            background_extras_count = 0
            if scene.cast_ids and len(scene.cast_ids) > 2:
                background_extras_count = len(scene.cast_ids) - 2
            if scene.cast_ids:
                parts = [
                    "Use image 1 as the background and lighting reference; preserve its layout unchanged.",
                    f"Use this story beat for visible actions: {visual or scene.summary}.",
                    f"Stage Character from Image 2 as an active actor; exact match for face/head; {framing_hint}.",
                ]
                if len(scene.cast_ids) > 1:
                    parts.append(
                        "Stage Character from Image 3 as an active actor; preserve body proportions and silhouette."
                    )
                    parts.append(
                        "Character from Image 2 and Character from Image 3 are different people; do not merge or swap identities."
                    )
                    parts.append(
                        "Character from Image 2 and Character from Image 3 must interact through complementary visible actions; avoid static lineup or idle posing."
                    )
                else:
                    parts.append(
                        "If image 3 is provided, use it only as optional body/pose guidance for Character from Image 2."
                    )
                    parts.append(
                        "Character from Image 2 must perform one clear visible action tied to the story beat; avoid idle standing."
                    )
                if background_extras_count > 0:
                    parts.append(
                        f"Allow exactly {background_extras_count} additional background extras; keep them secondary and non-identifiable."
                    )
                else:
                    parts.append("Do not add extra people beyond the principal character count.")
                parts.append("High fidelity, seamless blend, photorealistic detail.")
                if gritty:
                    parts.append("Raw realistic textures, detailed mud and dirt, no smoothing.")
                parts.append("Preserve unchanged background elements exactly.")
                composition_prompt = " ".join(parts)
            slides.append(
                {
                    "id": slide_id,
                    "order": idx + 1,
                    "title": None,
                    "exposition": exposition,
                    "thought": None,
                    "dialogue": dialogue,
                    "visual": visual or "Кадр сцены.",
                    "composition_prompt": composition_prompt,
                    "cast_ids": scene.cast_ids,
                    "location_id": scene.location_id,
                    "framing": framing,
                    "allow_background_extras": background_extras_count > 0,
                    "background_extras_count": background_extras_count if background_extras_count > 0 else None,
                }
            )
        scenes_payload.append({"scene_id": scene.id, "slides": slides})

    return Step3Data.model_validate({"scenes": scenes_payload})


def _fallback_step4(
    *,
    step1: Optional[Step1Data],
    step2: Step2Data,
) -> Step4Data:
    assets: List[Dict[str, Any]] = []
    idx = 1
    char_usage: Counter[str] = Counter()
    loc_usage: Counter[str] = Counter()
    if step1:
        for scene in step1.scenes:
            for cid in scene.cast_ids:
                char_usage[cid] += 1
            if scene.location_id:
                loc_usage[scene.location_id] += 1

    for ch in step2.characters:
        action = "update" if ch.source == "existing" else "create"
        priority = "high" if (ch.character_type == "protagonist" or char_usage.get(ch.id, 0) > 1) else "medium"
        if action == "update" and char_usage.get(ch.id, 0) == 0:
            priority = "low"
        assets.append(
            {
                "id": f"a{idx}",
                "type": "character",
                "source_id": ch.id,
                "action": action,
                "priority": priority,
                "dependencies": [],
                "reason": "Базовый план подготовки персонажа.",
                "status": "draft",
            }
        )
        idx += 1

    for loc in step2.locations:
        action = "update" if loc.source == "existing" else "create"
        priority = "high" if loc_usage.get(loc.id, 0) > 1 else "medium"
        if action == "update" and loc_usage.get(loc.id, 0) == 0:
            priority = "low"
        assets.append(
            {
                "id": f"a{idx}",
                "type": "location",
                "source_id": loc.id,
                "action": action,
                "priority": priority,
                "dependencies": [],
                "reason": "Базовый план подготовки локации.",
                "status": "draft",
            }
        )
        idx += 1

    return Step4Data.model_validate({"assets": assets})


def _fallback_step5(
    *,
    step1: Step1Data,
    branching: bool,
) -> Step5Data:
    if not branching:
        return Step5Data.model_validate({"branches": []})

    scene_id = step1.scenes[-1].id if step1.scenes else None
    next_scene_id = step1.scenes[1].id if len(step1.scenes) > 1 else (step1.scenes[0].id if step1.scenes else "")
    branches = [
        {
            "id": "b1",
            "scene_id": scene_id,
            "choice_key": "choice_1",
            "choice_prompt": "Как поступить дальше?",
            "options": [
                {
                    "id": "b1o1",
                    "label": "Следовать закону",
                    "summary": "Герой выбирает правовой путь и получает поддержку.",
                    "is_mainline": True,
                    "next_scenes": [next_scene_id] if next_scene_id else [],
                    "notes": None,
                },
                {
                    "id": "b1o2",
                    "label": "Рискнуть",
                    "summary": "Герой пробует альтернативный путь и сталкивается с последствиями.",
                    "is_mainline": False,
                    "next_scenes": [next_scene_id] if next_scene_id else [],
                    "notes": "Ветка требует дополнительных сцен.",
                },
            ],
        }
    ]
    return Step5Data.model_validate({"branches": branches})


def _fallback_step6(*, step3: Step3Data) -> Step6Data:
    links: List[Dict[str, Any]] = []
    for scene in step3.scenes:
        for slide in scene.slides:
            links.append(
                {
                    "scene_id": scene.scene_id,
                    "slide_id": slide.id,
                    "character_ids": slide.cast_ids,
                    "location_id": slide.location_id,
                    "framing": slide.framing,
                    "notes": None,
                }
            )
    return Step6Data.model_validate({"links": links})


def _normalize_step7_data(data: Step7Data) -> Step7Data:
    for issue in data.issues:
        issue.blocking = bool(issue.blocking or issue.severity == "high")
    if any((issue.severity == "high" or issue.blocking) and not issue.resolved for issue in data.issues):
        data.verdict = "revise"
    return data


def _fallback_step7(
    *,
    story_input: StoryInput,
    step1: Step1Data,
    step2: Step2Data,
    step3: Step3Data,
    step4: Step4Data,
    step5: Step5Data,
    step6: Step6Data,
) -> Step7Data:
    issues: List[Dict[str, Any]] = []

    def add_issue(
        *,
        severity: str,
        title: str,
        description: str,
        recommendation: str,
        affected_steps: List[int],
        affected_ids: Optional[List[str]] = None,
        evidence: Optional[str] = None,
    ) -> None:
        issue_id = f"i{len(issues) + 1}"
        issues.append(
            {
                "id": issue_id,
                "severity": severity,
                "title": title,
                "description": description,
                "recommendation": recommendation,
                "affected_steps": affected_steps,
                "affected_ids": affected_ids or [],
                "evidence": evidence,
                "blocking": severity == "high",
                "resolved": False,
                "resolution_note": None,
            }
        )

    scene_ids = {scene.id for scene in step1.scenes if scene.status != "rejected"}
    slide_pairs: set[Tuple[str, str]] = set()
    step3_char_ids: set[str] = set()
    step3_loc_ids: set[str] = set()
    for scene in step3.scenes:
        for slide in scene.slides:
            slide_pairs.add((scene.scene_id, slide.id))
            for cast_id in slide.cast_ids:
                step3_char_ids.add(cast_id)
            if slide.location_id:
                step3_loc_ids.add(slide.location_id)

    link_pairs: set[Tuple[str, str]] = set()
    for link in step6.links:
        if link.slide_id:
            link_pairs.add((link.scene_id, link.slide_id))

    if not scene_ids:
        add_issue(
            severity="high",
            title="Нет подтвержденных сцен",
            description="В шаге 1 отсутствуют пригодные сцены, сценарий не может быть развернут.",
            recommendation="Сформируйте минимум одну полноценную сцену в шаге 1 и пересчитайте шаги 3 и 6.",
            affected_steps=[1, 3, 6],
        )

    if slide_pairs and len(link_pairs) < len(slide_pairs):
        missing_links = sorted(slide_pairs - link_pairs)
        add_issue(
            severity="high",
            title="Не все слайды связаны с ассетами",
            description=(
                "Часть слайдов из раскадровки не имеет линковки в шаге 6, "
                "что нарушает целостность сценарной сборки."
            ),
            recommendation=(
                "Пересчитайте шаг 6 и убедитесь, что каждый слайд имеет соответствующую запись link."
            ),
            affected_steps=[3, 6],
            affected_ids=[f"{scene_id}:{slide_id}" for scene_id, slide_id in missing_links[:12]],
            evidence=f"Связано {len(link_pairs)} из {len(slide_pairs)} слайдов.",
        )

    known_char_ids = {char.id for char in step2.characters if char.status != "rejected"}
    unknown_chars = sorted(step3_char_ids - known_char_ids)
    if unknown_chars:
        add_issue(
            severity="medium",
            title="В слайдах используются неизвестные персонажи",
            description="Часть cast_ids в шаге 3 отсутствует в детализированном списке персонажей шага 2.",
            recommendation="Синхронизируйте cast_ids в шаге 3 с персонажами шага 2.",
            affected_steps=[2, 3],
            affected_ids=unknown_chars[:20],
            evidence=f"Неизвестных id: {len(unknown_chars)}",
        )

    known_loc_ids = {loc.id for loc in step2.locations if loc.status != "rejected"}
    unknown_locations = sorted(step3_loc_ids - known_loc_ids)
    if unknown_locations:
        add_issue(
            severity="medium",
            title="В слайдах используются неизвестные локации",
            description="Часть location_id в шаге 3 отсутствует в детализированном списке локаций шага 2.",
            recommendation="Проверьте location_id в шаге 3 и согласуйте его с шагом 2.",
            affected_steps=[2, 3],
            affected_ids=unknown_locations[:20],
            evidence=f"Неизвестных id: {len(unknown_locations)}",
        )

    if story_input.preferences and story_input.preferences.branching and len(step5.branches) == 0:
        add_issue(
            severity="medium",
            title="Ветвления включены, но не описаны",
            description="В настройках указан branching=true, но шаг 5 не содержит веток.",
            recommendation="Добавьте хотя бы одну осмысленную точку выбора в шаге 5.",
            affected_steps=[5],
        )

    actionable_assets = [asset for asset in step4.assets if asset.action != "skip" and asset.status != "rejected"]
    if not actionable_assets:
        add_issue(
            severity="medium",
            title="План ассетов не содержит действий",
            description="В шаге 4 отсутствуют ассеты с action=create/update.",
            recommendation="Отметьте ключевые персонажи и локации для создания или обновления.",
            affected_steps=[4],
        )

    required_legal = story_input.legal_topics.required if story_input.legal_topics else []
    if required_legal and not step1.legal_topics:
        add_issue(
            severity="medium",
            title="Потеряны обязательные правовые темы",
            description="Во входе заданы обязательные темы, но в шаге 1 они не отражены.",
            recommendation="Пересчитайте шаг 1 и проверьте блок legal_topics.",
            affected_steps=[1],
            evidence=f"Ожидалось тем: {len(required_legal)}",
        )

    checks: List[Dict[str, Any]] = []
    missing_link_count = max(0, len(slide_pairs) - len(link_pairs))
    checks.append(
        {
            "id": "continuity",
            "title": "Непрерывность сцен и слайдов",
            "status": "fail" if missing_link_count > 0 else "pass",
            "note": (
                f"Связано {len(link_pairs)} из {len(slide_pairs)} слайдов."
                if slide_pairs
                else "Слайды отсутствуют, непрерывность проверить нельзя."
            ),
        }
    )
    checks.append(
        {
            "id": "characters",
            "title": "Согласованность персонажей",
            "status": "warn" if unknown_chars else "pass",
            "note": "Проверены cast_ids между шагами 2 и 3.",
        }
    )
    checks.append(
        {
            "id": "locations",
            "title": "Согласованность локаций",
            "status": "warn" if unknown_locations else "pass",
            "note": "Проверены location_id между шагами 2 и 3.",
        }
    )
    checks.append(
        {
            "id": "branching",
            "title": "Корректность ветвлений",
            "status": "warn" if (story_input.preferences and story_input.preferences.branching and not step5.branches) else "pass",
            "note": "Проверено соответствие preferences.branching и шага 5.",
        }
    )
    checks.append(
        {
            "id": "assets",
            "title": "Готовность ассетов",
            "status": "warn" if not actionable_assets else "pass",
            "note": "Проверен план create/update в шаге 4.",
        }
    )
    checks.append(
        {
            "id": "legal",
            "title": "Юридическая полнота",
            "status": "warn" if (required_legal and not step1.legal_topics) else "pass",
            "note": "Сопоставлены обязательные темы из входа и декомпозиции.",
        }
    )

    high_count = sum(1 for issue in issues if issue["severity"] == "high")
    medium_count = sum(1 for issue in issues if issue["severity"] == "medium")
    low_count = sum(1 for issue in issues if issue["severity"] == "low")
    score = max(0, 92 - high_count * 25 - medium_count * 10 - low_count * 4)
    verdict = "revise" if high_count > 0 else ("revise" if score < 75 else "pass")

    if not issues:
        overall_summary = (
            "Критических нарушений целостности не выявлено. "
            "Структура шагов согласована и готова к развёртыванию."
        )
    else:
        overall_summary = (
            f"Найдены замечания: high={high_count}, medium={medium_count}, low={low_count}. "
            "Перед развёртыванием рекомендуется устранить значимые расхождения."
        )

    data = Step7Data.model_validate(
        {
            "overall_summary": overall_summary,
            "verdict": verdict,
            "continuity_score": score,
            "checks": checks,
            "issues": issues,
        }
    )
    return _normalize_step7_data(data)


def _build_step7_prompt(
    *,
    story_input: StoryInput,
    step1: Step1Data,
    step2: Step2Data,
    step3: Step3Data,
    step4: Step4Data,
    step5: Step5Data,
    step6: Step6Data,
    language: str,
    detail_level: str,
    critic_system_prompt: str,
) -> Tuple[str, str]:
    detail_hint = {
        "narrow": "Focus only on major consistency risks and blockers.",
        "standard": "Balanced review: blockers plus meaningful medium risks.",
        "detailed": "Deep review: blockers, medium issues, and hidden weak points.",
    }[detail_level]

    user_payload = {
        "goal": "step7_consistency_critic",
        "language": language,
        "detail_level": detail_level,
        "detail_hint": detail_hint,
        "story_input": story_input.model_dump(),
        "materials": {
            "step1": step1.model_dump(),
            "step2": step2.model_dump(),
            "step3": step3.model_dump(),
            "step4": step4.model_dump(),
            "step5": step5.model_dump(),
            "step6": step6.model_dump(),
        },
        "blocking_policy": {
            "substantial_is_high": True,
            "do_not_ignore_high": True,
            "block_deploy_if_unresolved_high": True,
        },
        "output_schema": {
            "overall_summary": "string",
            "verdict": "pass|revise",
            "continuity_score": 0,
            "checks": [
                {
                    "id": "string",
                    "title": "string",
                    "status": "pass|warn|fail",
                    "note": "string",
                }
            ],
            "issues": [
                {
                    "id": "string",
                    "severity": "low|medium|high",
                    "title": "string",
                    "description": "string",
                    "recommendation": "string",
                    "affected_steps": [1, 2],
                    "affected_ids": ["optional ids"],
                    "evidence": "optional string",
                    "blocking": True,
                    "resolved": False,
                    "resolution_note": None,
                }
            ],
        },
    }
    return critic_system_prompt, json.dumps(user_payload, ensure_ascii=False)


def _build_step1_prompt(
    *,
    story_input: StoryInput,
    language: str,
    detail_level: str,
    max_scenes: Optional[int],
    project: Optional[Project],
    project_characters: List[CharacterPreset],
    project_locations: List[Location],
    legal_concepts: List[LegalConcept],
    library_characters: List[Any],
) -> Tuple[str, str]:
    detail_hint = {
        "narrow": "Короткие формулировки, минимум деталей.",
        "standard": "Кратко, но достаточно для понимания сцен.",
        "detailed": "Более подробные описания без лишней воды.",
    }[detail_level]

    project_context = {}
    if story_input.project_context is not None:
        project_context.update(story_input.project_context.model_dump())
    if project is not None:
        project_context.update(
            {
                "project_name": project.name,
                "story_outline": _safe_str(project.story_outline or project.description, max_len=1400) or None,
            }
        )
        style_bible = getattr(project, "style_bible", None)
        if style_bible is not None:
            project_context["tone"] = _safe_str(style_bible.tone, max_len=120) or project_context.get("tone")
            project_context["constraints"] = style_bible.constraints or project_context.get("constraints")
            project_context["narrative_rules"] = _safe_str(style_bible.narrative_rules, max_len=600) or None

    existing_assets = story_input.existing_assets

    def _serialize_character(asset: Any, source: str) -> Dict[str, Any]:
        return {
            "id": getattr(asset, "id", None),
            "name": getattr(asset, "name", None),
            "source": source,
            "role": getattr(asset, "character_type", None),
            "description": _safe_str(getattr(asset, "description", None), max_len=240) or None,
            "appearance_prompt": _safe_str(getattr(asset, "appearance_prompt", None), max_len=200) or None,
            "style_tags": getattr(asset, "style_tags", None),
        }

    def _serialize_location(asset: Location) -> Dict[str, Any]:
        return {
            "id": asset.id,
            "name": asset.name,
            "description": _safe_str(asset.description, max_len=240) or None,
            "visual_reference": _safe_str(asset.visual_reference, max_len=200) or None,
            "tags": asset.tags,
        }

    project_chars_payload = [_serialize_character(c, "project") for c in project_characters[:40]]
    library_chars_payload = [_serialize_character(c, "library") for c in library_characters[:30]]
    locations_payload = [_serialize_location(l) for l in project_locations[:30]]
    legal_payload = [
        {
            "id": lc.id,
            "code": lc.code,
            "title": lc.title,
            "description": _safe_str(lc.description, max_len=220) or None,
        }
        for lc in legal_concepts[:30]
    ]

    system = (
        "Ты — ассистент мастера-редактора. "
        "Разбиваешь входной сюжет на персонажей, локации, сцены и правовые темы. "
        "Верни ТОЛЬКО валидный JSON без markdown. "
        f"Все нарративные строки должны быть на языке: {language}. "
        "Используй id с префиксами: c1.. для персонажей, l1.. для локаций, "
        "s1.. для сцен, t1.. для правовых тем. "
        "Статус всегда 'draft'. Поля вне схемы не добавляй."
    )

    user_payload = {
        "goal": "step1_decomposition",
        "language": language,
        "detail_level": detail_level,
        "detail_hint": detail_hint,
        "max_scenes": max_scenes or 8,
        "story": {
            "input_type": story_input.input_type,
            "text": _safe_str(story_input.story_text, max_len=2400),
        },
        "project_context": project_context or None,
        "legal_topics": {
            "required": (story_input.legal_topics.required if story_input.legal_topics else []),
            "optional": (story_input.legal_topics.optional if story_input.legal_topics else []),
            "auto_generate_if_empty": bool(
                story_input.legal_topics.auto_generate_if_empty if story_input.legal_topics else True
            ),
            "catalog": legal_payload,
        },
        "assets": {
            "requested_character_names": existing_assets.characters if existing_assets else [],
            "requested_location_names": existing_assets.locations if existing_assets else [],
            "existing_characters": project_chars_payload,
            "library_characters": library_chars_payload,
            "existing_locations": locations_payload,
        },
        "output_schema": {
            "characters": [
                {
                    "id": "c1",
                    "name": "string",
                    "summary": "string",
                    "role": "string",
                    "age": "optional string",
                    "notes": "optional string",
                    "confidence": 0.7,
                    "status": "draft",
                    "source": "new|existing",
                    "existing_asset_id": "optional id",
                }
            ],
            "locations": [
                {
                    "id": "l1",
                    "name": "string",
                    "summary": "string",
                    "type": "optional string",
                    "tags": ["string"],
                    "notes": "optional string",
                    "confidence": 0.7,
                    "status": "draft",
                    "source": "new|existing",
                    "existing_asset_id": "optional id",
                }
            ],
            "scenes": [
                {
                    "id": "s1",
                    "title": "string",
                    "summary": "string",
                    "location_id": "optional location id",
                    "cast_ids": ["character ids"],
                    "notes": "optional string",
                    "confidence": 0.7,
                    "status": "draft",
                }
            ],
            "legal_topics": [
                {"id": "t1", "title": "string", "summary": "string", "status": "draft"}
            ],
        },
        "notes": [
            "Если персонаж/локация уже есть в списках активов, пометь source='existing' и укажи existing_asset_id.",
            "Если required правовые темы пустые и auto_generate_if_empty=true, предложи 2-4 темы.",
            "Старайся использовать уже существующие активы, если они подходят по смыслу.",
        ],
    }

    return system, json.dumps(user_payload, ensure_ascii=False)


def _build_step2_prompt(
    *,
    step1: Step1Data,
    language: str,
    detail_level: str,
    project: Optional[Project],
    project_characters: List[CharacterPreset],
    project_locations: List[Location],
    library_characters: List[Any],
) -> Tuple[str, str]:
    detail_hint = {
        "narrow": "Короткие практичные описания.",
        "standard": "Достаточно деталей для генерации.",
        "detailed": "Более насыщенные описания без лишней воды.",
    }[detail_level]

    def _serialize_character(asset: Any, source: str) -> Dict[str, Any]:
        return {
            "id": getattr(asset, "id", None),
            "name": getattr(asset, "name", None),
            "source": source,
            "description": _safe_str(getattr(asset, "description", None), max_len=260) or None,
            "appearance_prompt": _safe_str(getattr(asset, "appearance_prompt", None), max_len=220) or None,
            "negative_prompt": _safe_str(getattr(asset, "negative_prompt", None), max_len=200) or None,
            "character_type": getattr(asset, "character_type", None),
            "voice_profile": _safe_str(getattr(asset, "voice_profile", None), max_len=200) or None,
            "style_tags": getattr(asset, "style_tags", None),
        }

    def _serialize_location(asset: Location) -> Dict[str, Any]:
        return {
            "id": asset.id,
            "name": asset.name,
            "description": _safe_str(asset.description, max_len=260) or None,
            "visual_reference": _safe_str(asset.visual_reference, max_len=220) or None,
            "negative_prompt": _safe_str(asset.negative_prompt, max_len=200) or None,
            "tags": asset.tags,
        }

    chars_payload = [_serialize_character(c, "project") for c in project_characters[:40]]
    libs_payload = [_serialize_character(c, "library") for c in library_characters[:30]]
    locs_payload = [_serialize_location(l) for l in project_locations[:30]]

    step1_chars = [
        {
            "id": c.id,
            "name": c.name,
            "summary": c.summary,
            "role": c.role,
            "age": c.age,
            "source": c.source,
            "existing_asset_id": c.existing_asset_id,
            "notes": c.notes,
        }
        for c in step1.characters
        if c.status != "rejected"
    ]
    step1_locs = [
        {
            "id": l.id,
            "name": l.name,
            "summary": l.summary,
            "type": l.type,
            "tags": l.tags,
            "source": l.source,
            "existing_asset_id": l.existing_asset_id,
            "notes": l.notes,
        }
        for l in step1.locations
        if l.status != "rejected"
    ]

    style_profile = getattr(project, "style_profile", None) if project else None
    style_context = None
    if style_profile is not None:
        style_context = {
            "base_prompt": _safe_str(style_profile.base_prompt, max_len=220) or None,
            "negative_prompt": _safe_str(style_profile.negative_prompt, max_len=200) or None,
            "palette": style_profile.palette,
            "forbidden": style_profile.forbidden,
        }

    system = (
        "Ты — ассистент по подготовке активов. "
        "Нужно детально описать персонажей и локации для последующей генерации. "
        "Верни ТОЛЬКО валидный JSON без markdown. "
        f"Все нарративные строки должны быть на языке: {language}. "
        "Поля prompt/negative_prompt/visual_reference/advanced_prompt можно писать SD-тегами на английском. "
        "Используй те же id, что в шаге 1. Поля вне схемы не добавляй."
    )

    user_payload = {
        "goal": "step2_detail",
        "language": language,
        "detail_level": detail_level,
        "detail_hint": detail_hint,
        "step1_characters": step1_chars,
        "step1_locations": step1_locs,
        "available_assets": {
            "project_characters": chars_payload,
            "library_characters": libs_payload,
            "project_locations": locs_payload,
        },
        "style_profile": style_context,
        "output_schema": {
            "characters": [
                {
                    "id": "c1",
                    "source": "new|existing",
                    "existing_asset_id": "optional id",
                    "name": "string",
                    "description": "string",
                    "role": "string",
                    "character_type": "protagonist|antagonist|supporting|background",
                    "appearance": {
                        "age_group": "optional",
                        "build": "optional",
                        "face_traits": "optional",
                        "hair": "optional",
                        "accessories": "optional",
                        "outfit": "optional",
                        "palette": "optional",
                        "distinctive_features": "optional",
                        "demeanor": "optional",
                    },
                    "voice_profile": "optional",
                    "motivation": "optional",
                    "legal_status": "optional",
                    "competencies": "optional",
                    "taboo": "optional",
                    "style_tags": "optional",
                    "prompt": "optional",
                    "negative_prompt": "optional",
                    "status": "draft",
                    "notes": "optional",
                }
            ],
            "locations": [
                {
                    "id": "l1",
                    "source": "new|existing",
                    "existing_asset_id": "optional id",
                    "name": "string",
                    "description": "string",
                    "location_type": "optional",
                    "interior_exterior": "optional",
                    "era": "optional",
                    "time_of_day": "optional",
                    "style": "optional",
                    "materials": "optional",
                    "mood": "optional",
                    "props": "optional",
                    "tags": "optional",
                    "notes": "optional",
                    "visual_reference": "string",
                    "negative_prompt": "optional",
                    "advanced_prompt": "optional",
                    "status": "draft",
                }
            ],
        },
        "notes": [
            "Для существующих активов используй их описания как основу, но адаптируй под сюжет.",
            "prompt/visual_reference должны быть пригодны для генерации иллюстраций.",
            "Не создавай новых id.",
        ],
    }

    return system, json.dumps(user_payload, ensure_ascii=False)


def _build_step3_prompt(
    *,
    step1: Step1Data,
    step2: Optional[Step2Data],
    language: str,
    detail_level: str,
) -> Tuple[str, str]:
    detail_hint = {
        "narrow": "1-2 слайда на сцену.",
        "standard": "2-4 слайда на сцену.",
        "detailed": "4-6 слайдов на сцену, если нужно.",
    }[detail_level]

    scenes_payload = [
        {
            "id": s.id,
            "title": s.title,
            "summary": s.summary,
            "location_id": s.location_id,
            "cast_ids": s.cast_ids,
        }
        for s in step1.scenes
        if s.status != "rejected"
    ]

    characters_payload = []
    locations_payload = []
    if step2 is not None:
        characters_payload = [
            {
                "id": c.id,
                "name": c.name,
                "role": c.role,
                "description": _safe_str(c.description, max_len=280),
                "prompt": _safe_str(c.prompt, max_len=240) or None,
                "negative_prompt": _safe_str(c.negative_prompt, max_len=200) or None,
            }
            for c in step2.characters
            if c.status != "rejected"
        ]
        locations_payload = [
            {
                "id": l.id,
                "name": l.name,
                "description": _safe_str(l.description, max_len=280),
                "visual_reference": _safe_str(l.visual_reference, max_len=220),
                "negative_prompt": _safe_str(l.negative_prompt, max_len=200) or None,
            }
            for l in step2.locations
            if l.status != "rejected"
        ]

    legal_payload = [
        {"id": t.id, "title": t.title, "summary": t.summary} for t in step1.legal_topics
    ]

    system = (
        "Ты — ассистент раскадровки. "
        "Нужно разделить сцены на слайды с репликами/мыслями и описанием кадра. "
        "Верни ТОЛЬКО валидный JSON без markdown. "
        f"Все нарративные строки должны быть на языке: {language}. "
        "Поле visual можно писать SD-тегами на английском. "
        "Поле composition_prompt (если используешь) должно быть на английском и короткими императивными фразами "
        "(без длинного повествования), фокус на композиции и видимых действиях в кадре: камера, ракурс, расстановка, свет, кто что делает. "
        "Структура composition_prompt: команда → правила сохранения → роли референсов → бустеры качества → якорь. "
        "Всегда указывай роли: image 1 = фон/сцена/свет (основной контекст), "
        "image 2 = Character from Image 2 (главный персонаж, face/head identity anchor), "
        "image 3 = Character from Image 3 (второй главный персонаж при наличии, либо опциональный body/pose reference для Character from Image 2). "
        "Если заданы image 2 и image 3, трактуй их как двух разных людей. "
        "Не используй имена/псевдонимы в composition_prompt — только slot-лейблы Character from Image 2 / Character from Image 3. "
        "Запрещай статичную расстановку и коллажный стиль: персонажи должны действовать и взаимодействовать по сюжетному биту. "
        "Явно соблюдай количество людей в кадре: не добавляй лишних главных персонажей. "
        "Для фоновых статистов используй только поля allow_background_extras/background_extras_count/background_extras_min/background_extras_max/background_extras_note. "
        "Используй формулировки: 'exact match', 'no changes to X', 'preserve X unchanged'; "
        "избегай повторов и фраз вроде 'as identical as possible'. "
        "Добавляй 'high fidelity, seamless blend, photorealistic detail'; "
        "если упомянуты грязь/сырость/жесткая фактура/NSFW, добавляй "
        "'raw realistic textures, detailed mud and dirt, no smoothing'. "
        "Длина 80–150 токенов. Всегда заканчивай 'Preserve unchanged background elements exactly.' "
        "Используй существующие id сцен/персонажей/локаций."
    )

    user_payload = {
        "goal": "step3_slides",
        "language": language,
        "detail_level": detail_level,
        "detail_hint": detail_hint,
        "scenes": scenes_payload,
        "characters": characters_payload,
        "locations": locations_payload,
        "legal_topics": legal_payload,
        "output_schema": {
            "scenes": [
                {
                    "scene_id": "s1",
                    "slides": [
                        {
                            "id": "s1_1",
                            "order": 1,
                            "title": "optional",
                            "exposition": "optional",
                            "thought": "optional",
                              "dialogue": [{"speaker": "string", "text": "string"}],
                              "visual": "string",
                              "composition_prompt": "string",
                              "cast_ids": ["character ids"],
                              "location_id": "optional location id",
                              "framing": "full|half|portrait",
                              "allow_background_extras": "optional boolean",
                              "background_extras_count": "optional integer >= 0",
                              "background_extras_min": "optional integer >= 0",
                              "background_extras_max": "optional integer >= 0",
                              "background_extras_note": "optional string",
                          }
                    ],
                }
            ]
        },
          "notes": [
              "На каждом слайде должно быть хотя бы одно из: exposition, thought или dialogue.",
              "Включай правовые темы в диалоги или экспозицию по возможности.",
              "Идентификаторы слайдов можно строить как {scene_id}_{номер}.",
              "composition_prompt: английский, короткие императивы (80–150 токенов), без длинного пересказа сюжета, "
              "с явными ролями image 1/2/3 и правилами сохранения; обязательно укажи видимые действия персонажей в кадре. "
              "Порядок: команда → preserve/no changes/exact match → роли референсов → "
              "high fidelity/seamless blend/photorealistic detail → якорь "
              "'Preserve unchanged background elements exactly.'",
              "По умолчанию не добавляй фоновых людей. Если нужны статисты, укажи allow_background_extras=true и их количество через background_extras_count (или диапазон min/max).",
          ],
      }

    return system, json.dumps(user_payload, ensure_ascii=False)


def _build_step4_prompt(
    *,
    step1: Optional[Step1Data],
    step2: Step2Data,
    language: str,
    detail_level: str,
) -> Tuple[str, str]:
    detail_hint = {
        "narrow": "Минимальный план ассетов.",
        "standard": "Практичный план ассетов с приоритетами.",
        "detailed": "Более подробный план с обоснованием.",
    }[detail_level]

    char_usage: Counter[str] = Counter()
    loc_usage: Counter[str] = Counter()
    if step1:
        for scene in step1.scenes:
            for cid in scene.cast_ids:
                char_usage[cid] += 1
            if scene.location_id:
                loc_usage[scene.location_id] += 1

    characters_payload = [
        {
            "id": c.id,
            "name": c.name,
            "source": c.source,
            "existing_asset_id": c.existing_asset_id,
            "role": c.role,
            "character_type": c.character_type,
            "usage_count": char_usage.get(c.id, 0),
        }
        for c in step2.characters
        if c.status != "rejected"
    ]
    locations_payload = [
        {
            "id": l.id,
            "name": l.name,
            "source": l.source,
            "existing_asset_id": l.existing_asset_id,
            "usage_count": loc_usage.get(l.id, 0),
        }
        for l in step2.locations
        if l.status != "rejected"
    ]

    system = (
        "Ты — ассистент по планированию ассетов. "
        "Нужно определить, какие ассеты создавать/обновлять/пропустить. "
        "Верни ТОЛЬКО валидный JSON без markdown. "
        f"Все пояснения должны быть на языке: {language}. "
        "Используй только существующие id из шага 2. Поля вне схемы не добавляй."
    )

    user_payload = {
        "goal": "step4_assets",
        "language": language,
        "detail_level": detail_level,
        "detail_hint": detail_hint,
        "characters": characters_payload,
        "locations": locations_payload,
        "output_schema": {
            "assets": [
                {
                    "id": "a1",
                    "type": "character|location",
                    "source_id": "id from step2",
                    "action": "create|update|skip",
                    "priority": "high|medium|low",
                    "dependencies": ["asset ids"],
                    "reason": "optional",
                    "status": "draft",
                }
            ]
        },
        "notes": [
            "Если source=existing, чаще всего action=update.",
            "Если source=new, обычно action=create.",
            "Редко используемые ассеты можно пометить action=skip и priority=low.",
        ],
    }

    return system, json.dumps(user_payload, ensure_ascii=False)


def _build_step6_prompt(
    *,
    step1: Optional[Step1Data],
    step2: Optional[Step2Data],
    step3: Step3Data,
    language: str,
    detail_level: str,
) -> Tuple[str, str]:
    detail_hint = {
        "narrow": "Простая линковка по слайдам.",
        "standard": "Линковка с уточнением состава и локаций.",
        "detailed": "Максимально аккуратная линковка кадров.",
    }[detail_level]

    scenes_payload = []
    if step1:
        for s in step1.scenes:
            if s.status == "rejected":
                continue
            scenes_payload.append(
                {
                    "id": s.id,
                    "title": s.title,
                    "location_id": s.location_id,
                    "cast_ids": s.cast_ids,
                }
            )

    characters_payload = []
    locations_payload = []
    if step2:
        characters_payload = [
            {"id": c.id, "name": c.name, "role": c.role}
            for c in step2.characters
            if c.status != "rejected"
        ]
        locations_payload = [
            {"id": l.id, "name": l.name}
            for l in step2.locations
            if l.status != "rejected"
        ]

    slides_payload = [
        {
            "scene_id": s.scene_id,
            "slides": [
                {
                    "id": slide.id,
                    "order": slide.order,
                    "cast_ids": slide.cast_ids,
                    "location_id": slide.location_id,
                    "framing": slide.framing,
                    "visual": _safe_str(slide.visual, max_len=200),
                }
                for slide in s.slides
            ],
        }
        for s in step3.scenes
    ]

    system = (
        "Ты — ассистент по линковке кадров. "
        "Нужно связать каждый слайд со списком персонажей и локацией. "
        "Верни ТОЛЬКО валидный JSON без markdown. "
        f"Все пояснения должны быть на языке: {language}. "
        "Используй только существующие id. Поля вне схемы не добавляй."
    )

    user_payload = {
        "goal": "step6_linking",
        "language": language,
        "detail_level": detail_level,
        "detail_hint": detail_hint,
        "scenes": scenes_payload,
        "characters": characters_payload,
        "locations": locations_payload,
        "slides": slides_payload,
        "output_schema": {
            "links": [
                {
                    "scene_id": "s1",
                    "slide_id": "s1_1",
                    "character_ids": ["c1", "c2"],
                    "location_id": "l1",
                    "framing": "full|half|portrait",
                    "notes": "optional",
                }
            ]
        },
        "notes": [
            "Если у слайда уже есть cast_ids/location_id, используй их как основу.",
            "Если location_id не указан, можно взять из сцены.",
            "Если персонажи не нужны — оставь character_ids пустым массивом.",
        ],
    }

    return system, json.dumps(user_payload, ensure_ascii=False)


def _build_step5_prompt(
    *,
    step1: Step1Data,
    language: str,
    detail_level: str,
) -> Tuple[str, str]:
    detail_hint = {
        "narrow": "1-2 развилки.",
        "standard": "2-3 развилки с кратким описанием.",
        "detailed": "до 4 развилок, но без перегруза.",
    }[detail_level]

    scenes_payload = [
        {"id": s.id, "title": s.title, "summary": s.summary} for s in step1.scenes if s.status != "rejected"
    ]

    system = (
        "Ты — ассистент по ветвлению сюжета. "
        "Нужно предложить точки выбора и варианты. "
        "Верни ТОЛЬКО валидный JSON без markdown. "
        f"Все строки должны быть на языке: {language}."
    )

    user_payload = {
        "goal": "step5_branching",
        "language": language,
        "detail_level": detail_level,
        "detail_hint": detail_hint,
        "scenes": scenes_payload,
        "output_schema": {
            "branches": [
                {
                    "id": "b1",
                    "scene_id": "optional scene id",
                    "choice_key": "string",
                    "choice_prompt": "string",
                    "options": [
                        {
                            "id": "b1o1",
                            "label": "string",
                            "summary": "string",
                            "is_mainline": True,
                            "next_scenes": ["scene ids or placeholders"],
                            "notes": "optional",
                        }
                    ],
                }
            ]
        },
        "notes": [
            "Один вариант должен оставлять игрока на магистральной линии (is_mainline=true).",
            "Если для ветки нужны новые сцены, укажи placeholder id (например, x1, x2).",
        ],
    }

    return system, json.dumps(user_payload, ensure_ascii=False)


class WizardService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()

    def _load_step7_critic_system_prompt(self, language: str) -> str:
        fallback = (
            "You are a strict narrative critic for an interactive legal quest. "
            "Return JSON only. "
            "All human-readable output must be in {{LANGUAGE}}. "
            "Find continuity, logic, motivation, timeline, branching, and legal plausibility issues. "
            "Mark truly blocking issues as severity=high and blocking=true."
        )
        prompt_path = self.settings.wizard_critic_prompt_path
        template = fallback
        try:
            if prompt_path.exists():
                loaded = prompt_path.read_text(encoding="utf-8").strip()
                if loaded:
                    template = loaded
        except Exception as exc:
            logger.warning("Failed to read wizard critic prompt file %s: %s", prompt_path, exc)

        resolved_language = (language or "ru").strip() or "ru"
        return template.replace("{{LANGUAGE}}", resolved_language)

    @staticmethod
    def _step7_unresolved_blockers(step7: Step7Data) -> List[Any]:
        return [
            issue
            for issue in step7.issues
            if (issue.severity == "high" or issue.blocking) and not issue.resolved
        ]

    @staticmethod
    def _extract_domain_ids_from_text(text: str) -> List[str]:
        if not text:
            return []
        return re.findall(r"\b[cslb][a-z0-9_:-]*\b", text.lower())

    @staticmethod
    def _wizard_entity_label_map(
        step1: Step1Data,
        step2: Step2Data,
        step3: Step3Data,
        step5: Step5Data,
    ) -> Dict[str, str]:
        labels: Dict[str, str] = {}
        for ch in step1.characters:
            labels[ch.id.lower()] = f"персонаж «{ch.name}»"
        for ch in step2.characters:
            labels[ch.id.lower()] = f"персонаж «{ch.name}»"
        for loc in step1.locations:
            labels[loc.id.lower()] = f"локация «{loc.name}»"
        for scene in step1.scenes:
            labels[scene.id.lower()] = f"сцена «{scene.title}»"
        for scene in step3.scenes:
            labels[scene.scene_id.lower()] = labels.get(scene.scene_id.lower(), f"сцена «{scene.scene_id}»")
            for slide in scene.slides:
                slide_title = _safe_str(slide.title, max_len=80) or f"слайд {slide.id}"
                labels[slide.id.lower()] = f"слайд «{slide_title}»"
        for branch in step5.branches:
            prompt = _safe_str(branch.choice_prompt, max_len=80) or branch.choice_key
            labels[branch.id.lower()] = f"ветка «{prompt}»"
            for option in branch.options:
                labels[option.id.lower()] = f"вариант «{_safe_str(option.label, max_len=80)}»"
        return labels

    @classmethod
    def _issue_to_author_explanation(cls, issue: Any, labels: Dict[str, str]) -> str:
        title = _safe_str(getattr(issue, "title", None), max_len=200).lower()
        description = _safe_str(getattr(issue, "description", None), max_len=260)
        recommendation = _safe_str(getattr(issue, "recommendation", None), max_len=220)

        raw_ids: List[str] = []
        raw_ids.extend(getattr(issue, "affected_ids", None) or [])
        raw_ids.extend(cls._extract_domain_ids_from_text(_safe_str(getattr(issue, "title", None), max_len=300)))
        raw_ids.extend(
            cls._extract_domain_ids_from_text(_safe_str(getattr(issue, "description", None), max_len=500))
        )

        normalized_ids: List[str] = []
        for item in raw_ids:
            token = _safe_str(item, max_len=64).lower()
            if token and token not in normalized_ids:
                normalized_ids.append(token)

        char_labels = [labels[i] for i in normalized_ids if i.startswith("c") and i in labels]
        scene_labels = [labels[i] for i in normalized_ids if i.startswith("s") and i in labels]
        branch_labels = [labels[i] for i in normalized_ids if i.startswith("b") and i in labels]
        affected_labels = [labels[i] for i in normalized_ids if i in labels]

        if "конфликт рол" in title and char_labels:
            return (
                f"{char_labels[0]} ведёт себя как разные роли в разных эпизодах. "
                "Игроку будет непонятно, кто этот герой и зачем он действует именно так."
            )
        if ("дублирование" in title and "сцен" in title) or ("duplicate" in title and "scene" in title):
            target = ", ".join(scene_labels[:2]) if scene_labels else "сцены"
            return (
                f"В структуре истории повторяются идентификаторы ({target}). "
                "Из-за этого переходы могут вести не в тот эпизод."
            )
        if ("дублирование" in title and "вет" in title) or ("duplicate" in title and "branch" in title):
            target = ", ".join(branch_labels[:2]) if branch_labels else "ветки выбора"
            return (
                f"Ветвления пересекаются по ID ({target}). "
                "Игрок может увидеть неправильные варианты выбора или потерять нужный путь."
            )

        if affected_labels:
            return (
                f"Проблема затрагивает: {', '.join(affected_labels[:3])}. "
                f"{description or recommendation or 'Нужно уточнить логику и связи.'}"
            )
        if description:
            return description
        if recommendation:
            return recommendation
        return _safe_str(getattr(issue, "title", None), max_len=200) or "Найдена проблема целостности сюжета."

    @classmethod
    def _author_blocker_hints(
        cls,
        blockers: List[Any],
        *,
        step1: Step1Data,
        step2: Step2Data,
        step3: Step3Data,
        step5: Step5Data,
        limit: int = 3,
    ) -> List[str]:
        labels = cls._wizard_entity_label_map(step1, step2, step3, step5)
        hints: List[str] = []
        for issue in blockers[:limit]:
            hint = cls._issue_to_author_explanation(issue, labels)
            if hint:
                hints.append(hint)
        return hints

    @staticmethod
    def _step7_override_from_meta(meta_map: Dict[str, Any]) -> Dict[str, Any]:
        raw = meta_map.get("step7_deploy_override")
        if not isinstance(raw, dict):
            return {"enabled": False}
        return {
            "enabled": bool(raw.get("enabled")),
            "reason": _safe_str(raw.get("reason"), max_len=1000) or None,
            "updated_at": _safe_str(raw.get("updated_at"), max_len=80) or None,
            "updated_by": _safe_str(raw.get("updated_by"), max_len=80) or None,
            "unresolved_blockers": int(raw.get("unresolved_blockers") or 0),
            "blocker_titles": [
                _safe_str(item, max_len=160)
                for item in (raw.get("blocker_titles") or [])
                if _safe_str(item, max_len=160)
            ],
            "critic_generated_at": _safe_str(raw.get("critic_generated_at"), max_len=80) or None,
            "project_description_file": _safe_str(raw.get("project_description_file"), max_len=400) or None,
        }

    def _project_description_path(self, project_id: str) -> Path:
        return self.settings.generated_assets_path / "projects" / project_id / "project_description.json"

    def _write_project_description_override(
        self,
        *,
        wizard: WizardSession,
        step7: Step7Data,
        override_state: Dict[str, Any],
        source: str,
        used_in_deploy: bool = False,
    ) -> Optional[str]:
        if not wizard.project_id:
            return None
        path = self._project_description_path(wizard.project_id)
        payload: Dict[str, Any] = {}
        if path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    payload = loaded
            except Exception:
                payload = {}

        now_iso = datetime.utcnow().isoformat()
        unresolved_blockers = self._step7_unresolved_blockers(step7)
        wizard_payload = payload.get("wizard")
        if not isinstance(wizard_payload, dict):
            wizard_payload = {}

        state = dict(override_state)
        state["source"] = source
        if used_in_deploy:
            state["used_in_deploy_at"] = now_iso

        wizard_payload.update(
            {
                "session_id": wizard.id,
                "updated_at": now_iso,
                "step7": {
                    "verdict": step7.verdict,
                    "continuity_score": step7.continuity_score,
                    "issues_total": len(step7.issues),
                    "unresolved_blockers": len(unresolved_blockers),
                },
                "step7_manual_override": state,
            }
        )

        payload["project_id"] = wizard.project_id
        payload["updated_at"] = now_iso
        payload["wizard"] = wizard_payload
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)

    def _log_invalid_payload(self, *, step: int, payload: Any, error: Exception) -> None:
        try:
            root = PROJECT_ROOT if isinstance(PROJECT_ROOT, Path) else Path(PROJECT_ROOT)
        except Exception:
            root = Path(".")
        log_dir = root / "log" / "wizard"
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            logger.warning("Wizard invalid payload log dir create failed | step=%s dir=%s", step, log_dir)
            return

        record = {
            "ts": datetime.utcnow().isoformat(),
            "step": step,
            "error": _safe_str(error, max_len=4000),
            "payload": payload,
        }
        log_path = log_dir / "invalid_payloads.jsonl"
        try:
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=True) + "\n")
        except Exception as exc:
            logger.warning("Wizard invalid payload log write failed | step=%s error=%s", step, exc)
            return
        logger.warning("Wizard invalid payload logged | step=%s path=%s", step, log_path)

    async def create_session(self, payload: WizardSessionCreateRequest) -> WizardSession:
        wizard = WizardSession(
            project_id=payload.project_id,
            status="active",
            current_step=1,
            input_payload=payload.story_input.model_dump(),
            drafts={},
            approvals={},
            meta={},
        )
        self.session.add(wizard)
        await self.session.commit()
        await self.session.refresh(wizard)
        return wizard

    async def get_session(self, session_id: str) -> Optional[WizardSession]:
        return await self.session.get(WizardSession, session_id)

    async def get_latest_session(self, project_id: Optional[str]) -> Optional[WizardSession]:
        if not project_id:
            return None
        result = await self.session.execute(
            select(WizardSession)
            .where(WizardSession.project_id == project_id)
            .order_by(WizardSession.updated_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    def _get_step_data(self, drafts: Dict[str, Any], step: int) -> Any:
        raw = drafts.get(str(step))
        if raw is None:
            raise HTTPException(status_code=409, detail=f"Step {step} is missing in drafts")
        model = StepModelMap[step]
        return model.model_validate(raw)

    def build_export_package(self, wizard: WizardSession) -> WizardExportPackage:
        drafts, approvals, meta = self._get_payload_maps(wizard)
        summary = {
            "steps": sorted(list(drafts.keys())),
            "counts": {
                "step1_characters": len((drafts.get("1") or {}).get("characters", [])),
                "step1_locations": len((drafts.get("1") or {}).get("locations", [])),
                "step1_scenes": len((drafts.get("1") or {}).get("scenes", [])),
                "step2_characters": len((drafts.get("2") or {}).get("characters", [])),
                "step2_locations": len((drafts.get("2") or {}).get("locations", [])),
                "step3_scenes": len((drafts.get("3") or {}).get("scenes", [])),
                "step4_assets": len((drafts.get("4") or {}).get("assets", [])),
                "step5_branches": len((drafts.get("5") or {}).get("branches", [])),
                "step6_links": len((drafts.get("6") or {}).get("links", [])),
                "step7_issues": len((drafts.get("7") or {}).get("issues", [])),
                "step7_blockers_unresolved": len(
                    [
                        issue
                        for issue in (drafts.get("7") or {}).get("issues", [])
                        if (
                            isinstance(issue, dict)
                            and (issue.get("severity") == "high" or bool(issue.get("blocking")))
                            and not bool(issue.get("resolved"))
                        )
                    ]
                ),
            },
        }
        story_input = None
        try:
            story_input = StoryInput.model_validate(wizard.input_payload or {})
        except Exception:
            story_input = None
        return WizardExportPackage(
            session_id=wizard.id,
            project_id=wizard.project_id,
            generated_at=datetime.utcnow().isoformat(),
            story_input=story_input,
            steps=drafts,
            meta=meta,
            approvals=approvals,
            summary=summary,
        )

    async def deploy_to_project(
        self,
        session_id: str,
        *,
        author_id: Optional[str] = None,
    ) -> WizardDeployResponse:
        wizard = await self.get_session(session_id)
        if wizard is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wizard session not found")
        if not wizard.project_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Wizard session has no project_id")

        drafts, _approvals, _meta = self._get_payload_maps(wizard)
        step1 = self._get_step_data(drafts, 1)
        step2 = self._get_step_data(drafts, 2)
        step3 = self._get_step_data(drafts, 3)
        step4 = self._get_step_data(drafts, 4)
        step5 = self._get_step_data(drafts, 5)
        step6 = self._get_step_data(drafts, 6)
        step7 = self._get_step_data(drafts, 7)
        unresolved_blockers = self._step7_unresolved_blockers(step7)
        override_state = self._step7_override_from_meta(_meta)
        step7_meta = _meta.get("7") if isinstance(_meta.get("7"), dict) else {}
        critic_generated_at = _safe_str(step7_meta.get("generated_at"), max_len=80) or None
        override_matches_critic = (
            bool(override_state.get("enabled"))
            and bool(override_state.get("critic_generated_at"))
            and override_state.get("critic_generated_at") == critic_generated_at
        )
        deploy_override_active = bool(override_state.get("enabled")) and (
            critic_generated_at is None or override_matches_critic
        )
        author_hints = self._author_blocker_hints(
            unresolved_blockers,
            step1=step1,
            step2=step2,
            step3=step3,
            step5=step5,
        )
        if unresolved_blockers and not deploy_override_active:
            blocker_titles = ", ".join(
                _safe_str(issue.title, max_len=80) for issue in unresolved_blockers[:3] if getattr(issue, "title", "")
            )
            message = (
                f"Шаг 7 обнаружил существенные замечания ({len(unresolved_blockers)}). "
                "Исправьте их и пересчитайте шаг 7 перед развёртыванием."
            )
            if blocker_titles:
                message = f"{message} Ключевые замечания: {blocker_titles}"
            if author_hints:
                message = f"{message} Расшифровка для автора: {'; '.join(author_hints[:2])}"
            if bool(override_state.get("enabled")) and not override_matches_critic:
                message = (
                    f"{message} Ручная разблокировка устарела после нового прогона критики. "
                    "Подтвердите разблокировку заново."
                )
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)

        project = await self._load_project(wizard.project_id)
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

        effective_author_id = author_id or project.owner_id
        if not effective_author_id:
            result = await self.session.execute(select(User.id).limit(1))
            effective_author_id = result.scalar_one_or_none()
        if not effective_author_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project owner not found")
        project_actor = await self.session.get(User, effective_author_id)
        if project_actor is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project owner not found")
        warnings: List[WizardIssue] = []
        if unresolved_blockers and deploy_override_active:
            warnings.append(
                WizardIssue(
                    code="step7_manual_override",
                    message=(
                        f"Развёртывание продолжено с ручным снятием блокировки критики "
                        f"(нерешённых замечаний: {len(unresolved_blockers)})."
                    ),
                    severity="high",
                    hint="Проверьте логическую целостность вручную перед публикацией.",
                )
            )
            try:
                used_state = dict(override_state)
                used_state["enabled"] = True
                self._write_project_description_override(
                    wizard=wizard,
                    step7=step7,
                    override_state=used_state,
                    source="deploy",
                    used_in_deploy=True,
                )
            except Exception as exc:
                logger.warning("Failed to record step7 override usage in project description file: %s", exc)
        character_report: List[Dict[str, Any]] = []
        location_report: List[Dict[str, Any]] = []
        characters_imported = 0
        characters_reused = 0
        locations_imported = 0
        locations_reused = 0

        def _upsert_report(target: List[Dict[str, Any]], payload: Dict[str, Any]) -> None:
            item_id = payload.get("id")
            if item_id:
                for existing in target:
                    if existing.get("id") == item_id:
                        existing.update(payload)
                        return
            target.append(payload)

        project_service = ProjectService(self.session)
        scenario_service = ScenarioService(self.session)
        world_service = WorldService(self.session)
        character_service = CharacterService(self.session)
        char_repo = CharacterPresetRepository(self.session)

        # Graph
        story_title = _first_sentence((wizard.input_payload or {}).get("story_text", "")) if wizard.input_payload else ""
        graph_title = story_title or f"Wizard Graph — {project.name}"
        graph_title = _safe_str(graph_title, max_len=255)
        if not graph_title:
            graph_title = _safe_str(f"Wizard Graph — {project.name}", max_len=255)
        graph_payload = {
            "project_id": project.id,
            "title": graph_title,
            "description": _safe_str((wizard.input_payload or {}).get("story_text"), max_len=400) if wizard.input_payload else None,
        }
        graph = await project_service.create_graph(
            project.id,
            ScenarioGraphCreate(**graph_payload),
            actor=project_actor,
        )
        if graph is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to create graph")

        async def _deploy_with_graph() -> WizardDeployResponse:
            nonlocal effective_author_id, characters_imported, characters_reused, locations_imported, locations_reused
            # Build asset allowlists from step4
            plan_assets = step4.assets or []
            allowed_char_ids = {
                item.source_id for item in plan_assets if item.type == "character" and item.action != "skip"
            }
            allowed_loc_ids = {
                item.source_id for item in plan_assets if item.type == "location" and item.action != "skip"
            }
            if not allowed_char_ids:
                allowed_char_ids = {c.id for c in step2.characters}
            if not allowed_loc_ids:
                allowed_loc_ids = {l.id for l in step2.locations}

            # Build cross-step existing asset hints (step1 -> step2)
            step1_existing_chars = {
                c.id: c.existing_asset_id
                for c in step1.characters
                if c.existing_asset_id
            }
            step1_existing_locs = {
                l.id: l.existing_asset_id
                for l in step1.locations
                if l.existing_asset_id
            }

            # Create locations
            location_id_map: Dict[str, str] = {}
            locations_created = 0
            for loc in step2.locations:
                if loc.status == "rejected":
                    _upsert_report(location_report, 
                        {
                            "id": loc.id,
                            "name": loc.name,
                            "action": "skipped",
                            "note": "rejected",
                        }
                    )
                    continue
                if loc.id not in allowed_loc_ids:
                    _upsert_report(location_report, 
                        {
                            "id": loc.id,
                            "name": loc.name,
                            "action": "skipped",
                            "note": "not_allowed",
                        }
                    )
                    continue
                existing_loc_id = loc.existing_asset_id or step1_existing_locs.get(loc.id)
                if existing_loc_id:
                    loc.existing_asset_id = existing_loc_id
                if (loc.source == "existing" or loc.existing_asset_id) and loc.existing_asset_id:
                    existing = await world_service.get_location(loc.existing_asset_id)
                    if existing and existing.project_id == project.id:
                        location_id_map[loc.id] = existing.id
                        locations_reused += 1
                        _upsert_report(location_report, 
                            {
                                "id": loc.id,
                                "name": loc.name,
                                "action": "reused",
                                "asset_id": existing.id,
                                "source": "project",
                            }
                        )
                        continue
                    if existing:
                        try:
                            imported = await world_service.import_location(project.id, existing.id, effective_author_id)
                            if imported:
                                location_id_map[loc.id] = imported.id
                                locations_imported += 1
                                _upsert_report(location_report, 
                                    {
                                        "id": loc.id,
                                        "name": loc.name,
                                        "action": "imported",
                                        "asset_id": imported.id,
                                        "source": "library" if existing.project_id is None else "project",
                                    }
                                )
                                continue
                        except Exception as exc:
                            warnings.append(WizardIssue(code="location_import_failed", message=_safe_str(exc, max_len=200)))
                            _upsert_report(location_report, 
                                {
                                    "id": loc.id,
                                    "name": loc.name,
                                    "action": "missing",
                                    "note": "import_failed",
                                }
                            )
                    # fallthrough -> create new

                tags = _split_list(loc.tags)
                metadata = {
                    "location_type": loc.location_type,
                    "interior_exterior": loc.interior_exterior,
                    "era": loc.era,
                    "time_of_day": loc.time_of_day,
                    "style": loc.style,
                    "materials": loc.materials,
                    "mood": loc.mood,
                    "props": loc.props,
                    "advanced_prompt": loc.advanced_prompt,
                }
                payload = {
                    "name": loc.name,
                    "description": loc.description,
                    "visual_reference": loc.visual_reference,
                    "negative_prompt": loc.negative_prompt,
                    "tags": tags or None,
                    "location_metadata": {k: v for k, v in metadata.items() if v},
                }
                created = await world_service.create_location(project.id, LocationCreate(**payload))
                if created:
                    location_id_map[loc.id] = created.id
                    locations_created += 1
                    _upsert_report(location_report, 
                        {
                            "id": loc.id,
                            "name": loc.name,
                            "action": "created",
                            "asset_id": created.id,
                            "source": "wizard",
                        }
                    )
                else:
                    warnings.append(
                        WizardIssue(code="location_create_failed", message=f"Не удалось создать локацию {loc.name}")
                    )
                    _upsert_report(location_report, 
                        {
                            "id": loc.id,
                            "name": loc.name,
                            "action": "missing",
                            "note": "create_failed",
                        }
                    )

            # Create characters
            character_id_map: Dict[str, str] = {}
            characters_created = 0
            if not effective_author_id:
                result = await self.session.execute(select(User.id).order_by(User.created_at.asc()).limit(1))
                fallback_id = result.scalar_one_or_none()
                if fallback_id:
                    effective_author_id = fallback_id
                    warnings.append(
                        WizardIssue(
                            code="author_fallback",
                            message="Не удалось определить автора проекта; использован первый доступный пользователь.",
                        )
                    )
                else:
                    warnings.append(
                        WizardIssue(code="author_missing", message="Не удалось определить автора для создания персонажей.")
                    )
            for ch in step2.characters:
                if ch.status == "rejected":
                    _upsert_report(character_report, 
                        {
                            "id": ch.id,
                            "name": ch.name,
                            "action": "skipped",
                            "note": "rejected",
                        }
                    )
                    continue
                if ch.id not in allowed_char_ids:
                    _upsert_report(character_report, 
                        {
                            "id": ch.id,
                            "name": ch.name,
                            "action": "skipped",
                            "note": "not_allowed",
                        }
                    )
                    continue
                existing_char_id = ch.existing_asset_id or step1_existing_chars.get(ch.id)
                if existing_char_id:
                    ch.existing_asset_id = existing_char_id
                if (ch.source == "existing" or ch.existing_asset_id) and ch.existing_asset_id:
                    existing = await char_repo.get_by_id(ch.existing_asset_id)
                    if existing and existing.project_id == project.id:
                        character_id_map[ch.id] = existing.id
                        characters_reused += 1
                        _upsert_report(character_report, 
                            {
                                "id": ch.id,
                                "name": ch.name,
                                "action": "reused",
                                "asset_id": existing.id,
                                "source": "project",
                            }
                        )
                        continue
                    if existing and effective_author_id:
                        try:
                            imported = await character_service.import_preset(
                                project.id, existing.id, effective_author_id
                            )
                            if imported:
                                character_id_map[ch.id] = imported.id
                                characters_imported += 1
                                _upsert_report(character_report, 
                                    {
                                        "id": ch.id,
                                        "name": ch.name,
                                        "action": "imported",
                                        "asset_id": imported.id,
                                        "source": "library" if existing.project_id is None else "project",
                                    }
                                )
                                continue
                        except Exception as exc:
                            warnings.append(
                                WizardIssue(code="character_import_failed", message=_safe_str(exc, max_len=200))
                            )
                            _upsert_report(character_report, 
                                {
                                    "id": ch.id,
                                    "name": ch.name,
                                    "action": "missing",
                                    "note": "import_failed",
                                }
                            )
                    elif existing is None:
                        warnings.append(
                            WizardIssue(
                                code="character_missing",
                                message=f"Персонаж {ch.name} не найден для импорта.",
                            )
                        )
                        _upsert_report(character_report, 
                            {
                                "id": ch.id,
                                "name": ch.name,
                                "action": "missing",
                                "note": "not_found",
                            }
                        )
                if not effective_author_id:
                    _upsert_report(character_report, 
                        {
                            "id": ch.id,
                            "name": ch.name,
                            "action": "skipped",
                            "note": "author_missing",
                        }
                    )
                    continue

                existing = await char_repo.get_by_name(ch.name, effective_author_id, project_id=project.id)
                if existing:
                    character_id_map[ch.id] = existing.id
                    characters_reused += 1
                    _upsert_report(character_report, 
                        {
                            "id": ch.id,
                            "name": ch.name,
                            "action": "reused",
                            "asset_id": existing.id,
                            "source": "project",
                            "note": "matched_by_name",
                        }
                    )
                    continue

                appearance_profile = ch.appearance.model_dump(exclude_none=True) if ch.appearance else None
                appearance_prompt = (ch.prompt or "").strip()
                if not appearance_prompt:
                    appearance_prompt = ", ".join(
                        [p for p in [
                            ch.description,
                            ch.appearance.face_traits if ch.appearance else None,
                            ch.appearance.hair if ch.appearance else None,
                            ch.appearance.outfit if ch.appearance else None,
                        ] if p]
                    )
                if not appearance_prompt or len(appearance_prompt) < 10:
                    appearance_prompt = f"{ch.name}, {ch.description or 'character'}"

                preset = CharacterPreset(
                    name=ch.name,
                    description=ch.description,
                    character_type=_normalize_character_type(ch.character_type, ch.role),
                    appearance_prompt=appearance_prompt,
                    negative_prompt=ch.negative_prompt,
                    anchor_token=f"wlchar_{uuid4().hex[:8]}",
                    appearance_profile=appearance_profile,
                    reference_images=None,
                    lora_models=None,
                    embeddings=None,
                    style_tags=_split_list(ch.style_tags) or None,
                    default_pose=None,
                    voice_profile=ch.voice_profile,
                    motivation=ch.motivation,
                    legal_status=ch.legal_status,
                    competencies=_split_list(ch.competencies),
                    relationships=None,
                    artifact_refs=None,
                    is_public=False,
                    author_id=effective_author_id,
                    project_id=project.id,
                    source_preset_id=None,
                    source_version=None,
                    version=1,
                )
                created = await char_repo.create(preset)
                character_id_map[ch.id] = created.id
                characters_created += 1
                _upsert_report(character_report, 
                    {
                        "id": ch.id,
                        "name": ch.name,
                        "action": "created",
                        "asset_id": created.id,
                        "source": "wizard",
                    }
                )

            # Build slide link map from step6
            slide_links: Dict[str, dict] = {}
            for link in step6.links:
                if link.slide_id:
                    slide_links[link.slide_id] = {
                        "character_ids": link.character_ids,
                        "location_id": link.location_id,
                        "framing": link.framing,
                    }

            branch_scene_ids = {b.scene_id for b in step5.branches if b.scene_id}
            branch_by_scene = {b.scene_id: b for b in step5.branches if b.scene_id}
            step1_scene_by_id = {s.id: s for s in step1.scenes}

            scene_id_map: Dict[str, str] = {}
            created_scene_order: List[str] = []
            scene_defaults_by_source: Dict[str, Dict[str, Any]] = {}
            scenes_created = 0
            for idx, scene in enumerate(step1.scenes):
                if scene.status == "rejected":
                    continue
                sequence = {"slides": []}
                seq_slides = []
                scene_cast_ids: List[str] = []
                scene_location_id: Optional[str] = None
                for scene_block in step3.scenes:
                    if scene_block.scene_id != scene.id:
                        continue
                    for slide in sorted(scene_block.slides, key=lambda s: s.order):
                        slide_cast = [
                            character_id_map.get(cid)
                            for cid in (slide.cast_ids or [])
                            if character_id_map.get(cid)
                        ]
                        slide_loc = location_id_map.get(slide.location_id) if slide.location_id else None
                        if slide.id in slide_links:
                            link = slide_links[slide.id]
                            linked_chars = [
                                character_id_map.get(cid)
                                for cid in (link.get("character_ids") or [])
                                if character_id_map.get(cid)
                            ]
                            if linked_chars:
                                slide_cast = linked_chars
                            if link.get("location_id"):
                                slide_loc = location_id_map.get(link.get("location_id")) or slide_loc
                            if link.get("framing"):
                                slide.framing = link.get("framing")

                        dialogue_payload = []
                        for line in slide.dialogue or []:
                            if hasattr(line, "model_dump"):
                                dialogue_payload.append(line.model_dump())
                            else:
                                dialogue_payload.append(line)

                        for preset_id in slide_cast:
                            if preset_id and preset_id not in scene_cast_ids:
                                scene_cast_ids.append(preset_id)
                        if slide_loc and not scene_location_id:
                            scene_location_id = slide_loc

                        seq_slides.append(
                            {
                                "id": slide.id,
                                "title": slide.title,
                                "exposition": slide.exposition,
                                "thought": slide.thought,
                                "dialogue": dialogue_payload,
                                "user_prompt": slide.visual,
                                "composition_prompt": slide.composition_prompt,
                                "cast_ids": slide_cast,
                                "location_id": slide_loc,
                                "framing": slide.framing,
                            }
                        )
                if seq_slides:
                    sequence["slides"] = seq_slides
                branch = branch_by_scene.get(scene.id)
                if branch:
                    sequence["choice_key"] = branch.choice_key
                    sequence["choice_prompt"] = branch.choice_prompt

                context = {"sequence": sequence, "wizard": {"session_id": wizard.id, "scene_id": scene.id}}
                location_id = location_id_map.get(scene.location_id) if scene.location_id else None
                if not location_id and scene_location_id:
                    location_id = scene_location_id
                scene_type = "decision" if scene.id in branch_scene_ids else "story"
                created_scene = await scenario_service.add_scene(
                    graph.id,
                    SceneNodeCreate(
                        title=scene.title,
                        content=scene.summary,
                        synopsis=scene.summary,
                        scene_type=scene_type,
                        order_index=idx + 1,
                        context=context,
                        location_id=location_id,
                    ),
                )
                if created_scene is None:
                    warnings.append(
                        WizardIssue(code="scene_create_failed", message=f"Не удалось создать сцену {scene.title}")
                    )
                    continue
                scene_id_map[scene.id] = created_scene.id
                created_scene_order.append(created_scene.id)
                scenes_created += 1

                # Attach scene characters (from step1)
                source_cast = scene.cast_ids or []
                if not source_cast and scene_cast_ids:
                    source_cast = scene_cast_ids
                cast_ids = [character_id_map.get(cid) for cid in source_cast if character_id_map.get(cid)]
                for preset_id in cast_ids:
                    link = SceneNodeCharacter(
                        scene_id=created_scene.id,
                        character_preset_id=preset_id,
                        scene_context=None,
                        position=None,
                        importance=1.0,
                        seed_override=None,
                        in_frame=True,
                        material_set_id=None,
                    )
                    self.session.add(link)
                if cast_ids:
                    await self.session.commit()

                scene_defaults_by_source[scene.id] = {
                    "scene_id": created_scene.id,
                    "title": scene.title,
                    "cast_ids": cast_ids,
                    "location_id": location_id,
                }

            # Update root scene if available
            if graph and scene_id_map:
                root_scene_id = scene_id_map.get(step1.scenes[0].id) if step1.scenes else None
                if root_scene_id:
                    graph.root_scene_id = root_scene_id
                    await self.session.commit()

            # Materialize branch placeholders (e.g. x1/x2) into concrete scene nodes.
            branch_scenes_created = 0
            for branch in step5.branches:
                if not branch.scene_id:
                    continue
                if branch.scene_id not in scene_id_map:
                    warnings.append(
                        WizardIssue(
                            code="branch_source_scene_missing",
                            message=f"Ветка {branch.id} ссылается на отсутствующую сцену {branch.scene_id}.",
                            severity="medium",
                        )
                    )
                    continue

                source_defaults = scene_defaults_by_source.get(branch.scene_id, {})
                source_scene = step1_scene_by_id.get(branch.scene_id)
                source_title = _safe_str(source_scene.title if source_scene else branch.scene_id, max_len=120) or branch.scene_id
                inherited_cast_ids: List[str] = list(source_defaults.get("cast_ids") or [])
                inherited_location_id = source_defaults.get("location_id")

                for option_idx, option in enumerate(branch.options):
                    target_keys: List[str] = []
                    for raw_target in option.next_scenes or []:
                        target = str(raw_target).strip()
                        if target:
                            target_keys.append(target)
                    if not target_keys:
                        target_keys = [f"auto_{branch.id}_{option.id or option_idx + 1}"]

                    resolved_targets: List[str] = []
                    for target_key in target_keys:
                        if target_key in scene_id_map:
                            resolved_targets.append(target_key)
                            continue

                        option_label = _safe_str(option.label, max_len=120) or f"Вариант {option_idx + 1}"
                        option_summary = _safe_str(option.summary, max_len=1200) or (
                            f"Развитие ветки после выбора «{option_label}»."
                        )
                        option_notes = _safe_str(option.notes, max_len=400) if option.notes else ""
                        branch_title = _safe_str(
                            f"{option_label} — после «{source_title}»",
                            max_len=255,
                        ) or option_label
                        branch_content = _safe_str(
                            " ".join(part for part in [option_summary, option_notes] if part),
                            max_len=2000,
                        ) or option_summary

                        safe_slide_token = re.sub(r"[^a-zA-Z0-9_\\-]+", "_", target_key).strip("_")
                        if not safe_slide_token:
                            safe_slide_token = f"branch_{uuid4().hex[:8]}"
                        slide_id = f"{safe_slide_token}_1"

                        principal_count = len(inherited_cast_ids)
                        framing = "full"
                        framing_hint = "full body shot, showing entire figure"
                        composition_parts = [
                            "Use image 1 as the background and lighting reference; preserve its layout unchanged.",
                            f"Use this story beat for visible actions: {option_summary}.",
                        ]
                        if principal_count <= 0:
                            composition_parts.append("Do not place principal cast characters in the frame.")
                        elif principal_count == 1:
                            composition_parts.append(
                                f"Stage Character from Image 2 as an active actor; exact match for face/head; {framing_hint}."
                            )
                            composition_parts.append(
                                "Character from Image 2 must perform one clear visible action tied to the story beat; avoid idle standing."
                            )
                        else:
                            composition_parts.append(
                                f"Stage Character from Image 2 as an active actor; exact match for face/head; {framing_hint}."
                            )
                            composition_parts.append(
                                "Stage Character from Image 3 as an active actor; preserve body proportions and silhouette."
                            )
                            composition_parts.append(
                                "Character from Image 2 and Character from Image 3 are different people; do not merge or swap identities."
                            )
                            composition_parts.append(
                                "Character from Image 2 and Character from Image 3 must interact through complementary visible actions; avoid static lineup or idle posing."
                            )
                        composition_parts.append("Do not add extra people beyond the principal character count.")
                        composition_parts.append("High fidelity, seamless blend, photorealistic detail.")
                        composition_parts.append("Preserve unchanged background elements exactly.")
                        composition_prompt = " ".join(composition_parts)

                        branch_sequence = {
                            "slides": [
                                {
                                    "id": slide_id,
                                    "title": option_label,
                                    "exposition": option_summary,
                                    "thought": None,
                                    "dialogue": [],
                                    "user_prompt": option_summary,
                                    "composition_prompt": composition_prompt,
                                    "cast_ids": inherited_cast_ids,
                                    "location_id": inherited_location_id,
                                    "framing": framing,
                                }
                            ]
                        }
                        branch_context = {
                            "sequence": branch_sequence,
                            "wizard": {
                                "session_id": wizard.id,
                                "generated_from_branch": True,
                                "source_scene_id": branch.scene_id,
                                "branch_id": branch.id,
                                "option_id": option.id,
                                "placeholder_scene_id": target_key,
                            },
                            "branch": {
                                "choice_key": branch.choice_key,
                                "choice_prompt": branch.choice_prompt,
                                "option_label": option.label,
                                "option_summary": option.summary,
                                "is_mainline": bool(option.is_mainline),
                            },
                        }
                        order_index = len(created_scene_order) + 1
                        created_branch_scene = await scenario_service.add_scene(
                            graph.id,
                            SceneNodeCreate(
                                title=branch_title,
                                content=branch_content,
                                synopsis=option_summary,
                                scene_type="story",
                                order_index=order_index,
                                context=branch_context,
                                location_id=inherited_location_id,
                            ),
                        )
                        if created_branch_scene is None:
                            warnings.append(
                                WizardIssue(
                                    code="branch_scene_create_failed",
                                    message=f"Не удалось создать сцену для ветки {branch.id}:{option.id}",
                                    severity="medium",
                                )
                            )
                            continue

                        scene_id_map[target_key] = created_branch_scene.id
                        created_scene_order.append(created_branch_scene.id)
                        scenes_created += 1
                        branch_scenes_created += 1
                        resolved_targets.append(target_key)

                        for preset_id in inherited_cast_ids:
                            self.session.add(
                                SceneNodeCharacter(
                                    scene_id=created_branch_scene.id,
                                    character_preset_id=preset_id,
                                    scene_context=None,
                                    position=None,
                                    importance=1.0,
                                    seed_override=None,
                                    in_frame=True,
                                    material_set_id=None,
                                )
                            )
                        if inherited_cast_ids:
                            await self.session.commit()

                    option.next_scenes = resolved_targets

            # Build edges
            edges_created = 0
            edge_keys = set()
            # Linear edges
            ordered_scene_ids = [s.id for s in step1.scenes if s.status != "rejected" and s.id in scene_id_map]
            for idx in range(len(ordered_scene_ids) - 1):
                from_id = scene_id_map[ordered_scene_ids[idx]]
                to_id = scene_id_map[ordered_scene_ids[idx + 1]]
                key = (from_id, to_id, None)
                if key in edge_keys:
                    continue
                edge = await scenario_service.add_edge(
                    graph.id,
                    EdgeCreate(from_scene_id=from_id, to_scene_id=to_id, choice_label=None, condition=None),
                )
                if edge:
                    edge_keys.add(key)
                    edges_created += 1

            # Branch edges
            for branch in step5.branches:
                if not branch.scene_id or branch.scene_id not in scene_id_map:
                    continue
                from_id = scene_id_map[branch.scene_id]
                for option in branch.options:
                    for next_scene in option.next_scenes:
                        if next_scene not in scene_id_map:
                            continue
                        to_id = scene_id_map[next_scene]
                        key = (from_id, to_id, option.label)
                        if key in edge_keys:
                            continue
                        edge = await scenario_service.add_edge(
                            graph.id,
                            EdgeCreate(
                                from_scene_id=from_id,
                                to_scene_id=to_id,
                                choice_label=option.label,
                                condition=None,
                                edge_metadata={
                                    "choice_key": branch.choice_key,
                                    "option_id": option.id,
                                    "is_mainline": option.is_mainline,
                                    "summary": option.summary,
                                },
                            ),
                        )
                        if edge:
                            edge_keys.add(key)
                            edges_created += 1

            if edges_created == 0 and len(created_scene_order) > 1:
                warnings.append(
                    WizardIssue(
                        code="edges_fallback",
                        message="Не удалось создать связи по сценам; построены линейные связи по порядку.",
                    )
                )
                for idx in range(len(created_scene_order) - 1):
                    from_id = created_scene_order[idx]
                    to_id = created_scene_order[idx + 1]
                    key = (from_id, to_id, None)
                    if key in edge_keys:
                        continue
                    edge = await scenario_service.add_edge(
                        graph.id,
                        EdgeCreate(from_scene_id=from_id, to_scene_id=to_id, choice_label=None, condition=None),
                    )
                    if edge:
                        edge_keys.add(key)
                        edges_created += 1

            if branch_scenes_created > 0:
                warnings.append(
                    WizardIssue(
                        code="branch_scenes_materialized",
                        message=(
                            f"Для ветвлений автоматически создано дополнительных сцен: {branch_scenes_created}."
                        ),
                        severity="low",
                    )
                )

            return WizardDeployResponse(
                graph_id=graph.id,
                graph_title=graph.title,
                scenes_created=scenes_created,
                edges_created=edges_created,
                characters_created=characters_created,
                characters_imported=characters_imported,
                characters_reused=characters_reused,
                locations_created=locations_created,
                locations_imported=locations_imported,
                locations_reused=locations_reused,
                warnings=warnings,
                report={
                    "characters": character_report,
                    "locations": location_report,
                },
            )

        try:
            return await _deploy_with_graph()
        except Exception:
            logger.exception("Wizard deploy failed; cleaning up graph %s", graph.id)
            try:
                await self.session.rollback()
            except Exception:
                logger.exception("Wizard deploy rollback failed for graph %s", graph.id)
            try:
                await self.session.delete(graph)
                await self.session.commit()
            except Exception:
                logger.exception("Wizard deploy cleanup failed for graph %s", graph.id)
            raise


    async def reset_project(
        self,
        session_id: str,
        *,
        author_id: Optional[str] = None,
    ) -> Project:
        wizard = await self.get_session(session_id)
        if wizard is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wizard session not found")
        if not wizard.project_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Wizard session has no project_id")

        old_project_id = wizard.project_id
        project = await self.session.get(Project, old_project_id)

        # Resolve owner for the recreated project
        effective_owner_id = author_id or (project.owner_id if project is not None else None)
        if not effective_owner_id:
            result = await self.session.execute(select(User.id).limit(1))
            effective_owner_id = result.scalar_one_or_none()
        if not effective_owner_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project owner not found")
        project_actor = await self.session.get(User, effective_owner_id)
        if project_actor is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project owner not found")

        story_text = (wizard.input_payload or {}).get("story_text", "")
        story_outline = _safe_str(story_text, max_len=2000) if story_text else None

        # If project missing, still recreate from story input.
        if project is None:
            name = _safe_str(_first_sentence(story_text), max_len=255) or "Wizard Project"
            project_service = ProjectService(self.session)
            new_project = await project_service.create_project(
                ProjectCreate(
                    name=name,
                    description=None,
                    story_outline=story_outline,
                    owner_id=effective_owner_id,
                ),
                actor=project_actor,
            )
            wizard.project_id = new_project.id
            await self.session.commit()
            await self.session.refresh(wizard)
            return new_project

        project_service = ProjectService(self.session)
        new_project = await project_service.create_project(
            ProjectCreate(
                name=project.name,
                description=project.description,
                story_outline=project.story_outline or story_outline,
                owner_id=effective_owner_id,
            ),
            actor=project_actor,
        )

        # Rebind current session to the new project and detach other sessions.
        wizard.project_id = new_project.id
        await self.session.execute(
            update(WizardSession)
            .where(WizardSession.project_id == old_project_id, WizardSession.id != wizard.id)
            .values(project_id=None)
        )

        # Delete old project after detaching sessions.
        old_project = await self.session.get(Project, old_project_id)
        if old_project is not None:
            await self.session.delete(old_project)

        await self.session.commit()
        await self.session.refresh(wizard)
        return new_project

    async def update_session(
        self,
        session_id: str,
        payload: WizardSessionUpdateRequest,
    ) -> Optional[WizardSession]:
        wizard = await self.get_session(session_id)
        if wizard is None:
            return None
        if payload.story_input is not None:
            wizard.input_payload = payload.story_input.model_dump()
        await self.session.commit()
        await self.session.refresh(wizard)
        return wizard

    async def delete_session(self, session_id: str) -> bool:
        wizard = await self.get_session(session_id)
        if wizard is None:
            return False
        await self.session.delete(wizard)
        await self.session.commit()
        return True

    def _resolve_step_model(self, step: int):
        model = StepModelMap.get(step)
        if model is None:
            raise HTTPException(status_code=400, detail="Unsupported step")
        return model

    def _get_payload_maps(self, wizard: WizardSession) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
        # Return shallow copies so we always assign new objects back to SQLAlchemy,
        # ensuring JSON columns are marked dirty.
        drafts = dict(wizard.drafts or {})
        approvals = dict(wizard.approvals or {})
        meta = dict(wizard.meta or {})
        return drafts, approvals, meta

    async def _load_project(self, project_id: str) -> Optional[Project]:
        result = await self.session.execute(
            select(Project)
            .options(selectinload(Project.style_bible), selectinload(Project.style_profile))
            .where(Project.id == project_id)
        )
        return result.scalar_one_or_none()

    async def _load_project_characters(self, project_id: str) -> List[CharacterPreset]:
        result = await self.session.execute(
            select(CharacterPreset)
            .where(CharacterPreset.project_id == project_id)
            .order_by(CharacterPreset.updated_at.desc())
        )
        return list(result.scalars().all())

    async def _load_project_locations(self, project_id: str) -> List[Location]:
        result = await self.session.execute(
            select(Location)
            .where(Location.project_id == project_id)
            .order_by(Location.updated_at.desc())
        )
        return list(result.scalars().all())

    async def _load_project_artifacts(self, project_id: str) -> List[Artifact]:
        result = await self.session.execute(
            select(Artifact)
            .where(Artifact.project_id == project_id)
            .order_by(Artifact.updated_at.desc())
        )
        return list(result.scalars().all())

    async def _load_legal_concepts(self) -> List[LegalConcept]:
        result = await self.session.execute(select(LegalConcept).order_by(LegalConcept.title.asc()))
        return list(result.scalars().all())

    async def _call_llm_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
        model: Optional[str] = None,
        strict: bool,
        warnings: List[Dict[str, Any]],
        context: Optional[str] = None,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        ctx = context or "wizard"
        system_len = len(system_prompt or "")
        user_len = len(user_prompt or "")
        started_at = time.perf_counter()
        logger.info(
            "Wizard LLM request start | ctx=%s temp=%.2f max_tokens=%s system_chars=%s user_chars=%s",
            ctx,
            temperature,
            max_tokens,
            system_len,
            user_len,
        )

        async def _call() -> dict:
            return await create_chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                model=model,
            )

        try:
            response = await run_with_backoff(
                _call,
                retries=self.settings.llm_max_retries,
                base_delay=self.settings.llm_backoff_base,
                max_delay=self.settings.llm_backoff_max,
                retry_on=(RetryableAIError, httpx.RequestError),
            )
        except LLMConfigError as exc:
            logger.warning("Wizard LLM config error | ctx=%s error=%s", ctx, exc)
            if strict:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
            warnings.append(_issue("llm_config", "LLM не настроен, использован fallback.", severity="high"))
            return None, None
        except RetryableAIError as exc:
            logger.warning("Wizard LLM retryable error | ctx=%s error=%s", ctx, exc)
            if strict:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"LLM request failed after retries: {exc}",
                )
            warnings.append(_issue("llm_retry", "LLM временно недоступен, использован fallback.", severity="high"))
            return None, None
        except NonRetryableAIError as exc:
            logger.warning("Wizard LLM non-retryable error | ctx=%s error=%s", ctx, exc)
            if strict:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"LLM request failed: {exc}")
            warnings.append(_issue("llm_error", "LLM вернул ошибку, использован fallback.", severity="high"))
            return None, None
        except httpx.RequestError as exc:
            logger.warning("Wizard LLM network error | ctx=%s error=%s", ctx, exc)
            if strict:
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"LLM request error: {exc}")
            warnings.append(_issue("llm_network", "Сетевая ошибка LLM, использован fallback.", severity="high"))
            return None, None

        content = (
            response.get("choices", [{}])[0].get("message", {}).get("content", "") if response else ""
        )
        content = (content or "").strip()
        llm_meta = {
            "model": response.get("model") if response else None,
            "usage": response.get("usage") if response else None,
            "request_id": response.get("id") if response else None,
        }
        duration_ms = (time.perf_counter() - started_at) * 1000
        logger.info(
            "Wizard LLM response | ctx=%s duration_ms=%.2f model=%s content_chars=%s request_id=%s",
            ctx,
            duration_ms,
            llm_meta.get("model"),
            len(content),
            llm_meta.get("request_id"),
        )

        if not content:
            if strict:
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="LLM returned an empty response")
            warnings.append(_issue("llm_empty", "LLM вернул пустой ответ, использован fallback."))
            return None, llm_meta

        payload = _extract_json(content)
        if not payload:
            if strict:
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="LLM returned invalid JSON")
            warnings.append(_issue("llm_invalid_json", "LLM вернул невалидный JSON, использован fallback."))
            logger.warning("Wizard LLM invalid JSON: %s", content[:500])
            return None, llm_meta

        return payload, llm_meta

    async def get_step(self, session_id: str, step: int) -> Optional[Dict[str, Any]]:
        wizard = await self.get_session(session_id)
        if wizard is None:
            return None
        drafts, _approvals, meta = self._get_payload_maps(wizard)
        step_key = str(step)
        if step_key not in drafts:
            return None
        return {"data": drafts.get(step_key), "meta": meta.get(step_key)}

    async def save_step(
        self,
        session_id: str,
        step: int,
        data: Dict[str, Any],
        meta: Optional[WizardMeta | Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        wizard = await self.get_session(session_id)
        if wizard is None:
            return None

        model = self._resolve_step_model(step)
        validated = model.model_validate(data)
        drafts, approvals, meta_map = self._get_payload_maps(wizard)

        step_key = str(step)
        drafts[step_key] = validated.model_dump()
        if meta is not None:
            meta_map[step_key] = WizardMeta.model_validate(meta).model_dump()
        wizard.drafts = drafts
        wizard.approvals = approvals
        wizard.meta = meta_map
        wizard.current_step = max(wizard.current_step or 1, step)
        await self.session.commit()
        await self.session.refresh(wizard)
        return {"data": drafts.get(step_key), "meta": meta_map.get(step_key)}

    async def approve_step(
        self,
        session_id: str,
        step: int,
        payload: WizardStepApproveRequest,
    ) -> Optional[Dict[str, Any]]:
        wizard = await self.get_session(session_id)
        if wizard is None:
            return None
        drafts, approvals, meta_map = self._get_payload_maps(wizard)
        step_key = str(step)
        approvals[step_key] = payload.model_dump()
        wizard.approvals = approvals
        await self.session.commit()
        await self.session.refresh(wizard)
        return {"data": drafts.get(step_key), "meta": meta_map.get(step_key), "approval": approvals.get(step_key)}

    async def set_step7_deploy_override(
        self,
        *,
        session_id: str,
        payload: WizardStep7DeployOverrideRequest,
        actor_user_id: Optional[str] = None,
    ) -> Optional[WizardSession]:
        wizard = await self.get_session(session_id)
        if wizard is None:
            return None

        drafts, approvals, meta_map = self._get_payload_maps(wizard)
        step7_raw = drafts.get("7")
        if step7_raw is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Сначала выполните шаг 7, затем можно управлять ручной блокировкой.",
            )
        step7 = Step7Data.model_validate(step7_raw)
        unresolved_blockers = self._step7_unresolved_blockers(step7)
        step7_meta = meta_map.get("7") if isinstance(meta_map.get("7"), dict) else {}
        critic_generated_at = _safe_str(step7_meta.get("generated_at"), max_len=80) or None

        override_state = {
            "enabled": bool(payload.enabled),
            "reason": _safe_str(payload.reason, max_len=1000) or None,
            "updated_at": datetime.utcnow().isoformat(),
            "updated_by": actor_user_id,
            "unresolved_blockers": len(unresolved_blockers),
            "blocker_titles": [
                _safe_str(issue.title, max_len=160) for issue in unresolved_blockers if _safe_str(issue.title)
            ][:6],
            "critic_generated_at": critic_generated_at,
        }

        description_file_path = None
        try:
            description_file_path = self._write_project_description_override(
                wizard=wizard,
                step7=step7,
                override_state=override_state,
                source="manual_toggle",
            )
        except Exception as exc:
            logger.warning("Failed to update project description file for step7 override: %s", exc)

        if description_file_path:
            override_state["project_description_file"] = description_file_path

        meta_map["step7_deploy_override"] = override_state
        wizard.drafts = drafts
        wizard.approvals = approvals
        wizard.meta = meta_map
        await self.session.commit()
        await self.session.refresh(wizard)
        return wizard

    async def run_step(
        self,
        session_id: str,
        step: int,
        payload: WizardStepRunRequest,
    ) -> Dict[str, Any]:
        wizard = await self.get_session(session_id)
        if wizard is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wizard session not found")

        self._resolve_step_model(step)
        drafts, _approvals, meta_map = self._get_payload_maps(wizard)
        step_key = str(step)
        if step_key in drafts and not payload.force:
            return {"data": drafts.get(step_key), "meta": meta_map.get(step_key)}

        try:
            story_input = StoryInput.model_validate(wizard.input_payload or {})
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Wizard story_input is invalid: {exc}")

        language = (
            payload.language or (story_input.preferences.language if story_input.preferences else None) or "ru"
        ).strip()
        if not language:
            language = "ru"
        detail_level = _normalize_detail_level(payload.detail_level)
        strict = bool(payload.strict)
        max_scenes = story_input.preferences.max_scenes if story_input.preferences else None
        branching_enabled = story_input.preferences.branching if story_input.preferences else True

        warnings: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []

        project: Optional[Project] = None
        project_characters: List[CharacterPreset] = []
        project_locations: List[Location] = []
        legal_concepts: List[LegalConcept] = []
        library_characters: List[Any] = []

        if wizard.project_id:
            project = await self._load_project(wizard.project_id)
            if project is None:
                if strict:
                    raise HTTPException(status_code=404, detail="Project not found")
                warnings.append(_issue("project_missing", "Проект не найден, контекст ограничен.", severity="high"))
            else:
                project_characters = await self._load_project_characters(project.id)
                project_locations = await self._load_project_locations(project.id)

        try:
            legal_concepts = await self._load_legal_concepts()
        except Exception:
            warnings.append(_issue("legal_catalog", "Не удалось загрузить справочник правовых тем.", severity="low"))

        if self.settings.character_lib_enabled:
            try:
                lib = get_character_lib()
                lib_list = lib.list_characters(
                    page=1,
                    page_size=200,
                    author_id=wizard.owner_id,
                    include_public=True,
                )
                library_characters = list(lib_list.items)
            except Exception:
                warnings.append(_issue("character_lib", "Не удалось загрузить библиотеку персонажей.", severity="low"))

        required_steps: Dict[int, List[int]] = {
            2: [1],
            3: [1],
            4: [2],
            5: [1],
            6: [3],
            7: [1, 2, 3, 4, 5, 6],
        }
        missing = [s for s in required_steps.get(step, []) if str(s) not in drafts]
        if missing:
            raise HTTPException(
                status_code=409,
                detail=f"Required steps missing before step {step}: {', '.join(str(s) for s in missing)}",
            )

        def _get_step_data(step_num: int):
            raw = drafts.get(str(step_num))
            if raw is None:
                return None
            return StepModelMap[step_num].model_validate(raw)

        step1_data = _get_step_data(1)
        step2_data = _get_step_data(2)
        step3_data = _get_step_data(3)
        step4_data = _get_step_data(4)
        step5_data = _get_step_data(5)
        step6_data = _get_step_data(6)

        llm_meta: Optional[Dict[str, Any]] = None
        data_model: Any = None

        if step == 1:
            system_prompt, user_prompt = _build_step1_prompt(
                story_input=story_input,
                language=language,
                detail_level=detail_level,
                max_scenes=max_scenes,
                project=project,
                project_characters=project_characters,
                project_locations=project_locations,
                legal_concepts=legal_concepts,
                library_characters=library_characters,
            )
            payload_json, llm_meta = await self._call_llm_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.4,
                max_tokens=1200,
                strict=strict,
                warnings=warnings,
                context="step1",
            )
            payload_json = _unwrap_data(payload_json) if payload_json else None
            if payload_json:
                try:
                    data_model = Step1Data.model_validate(payload_json)
                except Exception as exc:
                    if strict:
                        raise HTTPException(status_code=502, detail=f"LLM payload invalid: {exc}")
                    self._log_invalid_payload(step=step, payload=payload_json, error=exc)
                    warnings.append(
                        _issue(
                            "validation_failed",
                            "LLM вернул данные, не прошедшие проверку; использован fallback.",
                            severity="high",
                            hint=_safe_str(exc, max_len=200),
                        )
                    )
            if data_model is None:
                data_model = _fallback_step1(
                    story_input=story_input,
                    project_characters=project_characters,
                    project_locations=project_locations,
                    legal_concepts=legal_concepts,
                    library_characters=library_characters,
                    max_scenes=max_scenes,
                )
            if data_model is not None:
                requested_names = (
                    story_input.existing_assets.characters
                    if story_input.existing_assets is not None
                    else []
                )
                data_model = _apply_character_asset_matches(
                    data_model,
                    project_characters,
                    library_characters,
                    requested_names,
                )

        elif step == 2:
            if step1_data is None:
                raise HTTPException(status_code=409, detail="Step 1 data is required for step 2")

            system_prompt, user_prompt = _build_step2_prompt(
                step1=step1_data,
                language=language,
                detail_level=detail_level,
                project=project,
                project_characters=project_characters,
                project_locations=project_locations,
                library_characters=library_characters,
            )
            payload_json, llm_meta = await self._call_llm_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.5,
                max_tokens=1400,
                strict=strict,
                warnings=warnings,
                context="step2",
            )
            payload_json = _unwrap_data(payload_json) if payload_json else None
            if payload_json:
                try:
                    data_model = Step2Data.model_validate(payload_json)
                except Exception as exc:
                    if strict:
                        raise HTTPException(status_code=502, detail=f"LLM payload invalid: {exc}")
                    self._log_invalid_payload(step=step, payload=payload_json, error=exc)
                    warnings.append(
                        _issue(
                            "validation_failed",
                            "LLM вернул данные, не прошедшие проверку; использован fallback.",
                            severity="high",
                            hint=_safe_str(exc, max_len=200),
                        )
                    )
            if data_model is None:
                char_assets = {c.id: c for c in project_characters}
                for lc in library_characters:
                    cid = getattr(lc, "id", None)
                    if cid:
                        char_assets[cid] = lc
                loc_assets = {l.id: l for l in project_locations}
                data_model = _fallback_step2(
                    step1=step1_data,
                    character_assets=char_assets,
                    location_assets=loc_assets,
                )

        elif step == 3:
            if step1_data is None:
                raise HTTPException(status_code=409, detail="Step 1 data is required for step 3")

            system_prompt, user_prompt = _build_step3_prompt(
                step1=step1_data,
                step2=step2_data,
                language=language,
                detail_level=detail_level,
            )
            payload_json, llm_meta = await self._call_llm_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.6,
                max_tokens=1600,
                strict=strict,
                warnings=warnings,
                context="step3",
            )
            payload_json = _unwrap_data(payload_json) if payload_json else None
            if payload_json:
                try:
                    data_model = Step3Data.model_validate(payload_json)
                except Exception as exc:
                    if strict:
                        raise HTTPException(status_code=502, detail=f"LLM payload invalid: {exc}")
                    self._log_invalid_payload(step=step, payload=payload_json, error=exc)
                    warnings.append(
                        _issue(
                            "validation_failed",
                            "LLM вернул данные, не прошедшие проверку; использован fallback.",
                            severity="high",
                            hint=_safe_str(exc, max_len=200),
                        )
                    )
            if data_model is None:
                data_model = _fallback_step3(step1=step1_data, detail_level=detail_level)

        elif step == 4:
            if step2_data is None:
                raise HTTPException(status_code=409, detail="Step 2 data is required for step 4")
            system_prompt, user_prompt = _build_step4_prompt(
                step1=step1_data,
                step2=step2_data,
                language=language,
                detail_level=detail_level,
            )
            payload_json, llm_meta = await self._call_llm_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.4,
                max_tokens=1200,
                strict=strict,
                warnings=warnings,
                context="step4",
            )
            payload_json = _unwrap_data(payload_json) if payload_json else None
            if payload_json:
                try:
                    data_model = Step4Data.model_validate(payload_json)
                except Exception as exc:
                    if strict:
                        raise HTTPException(status_code=502, detail=f"LLM payload invalid: {exc}")
                    self._log_invalid_payload(step=step, payload=payload_json, error=exc)
                    warnings.append(
                        _issue(
                            "validation_failed",
                            "LLM вернул данные, не прошедшие проверку; использован fallback.",
                            severity="high",
                            hint=_safe_str(exc, max_len=200),
                        )
                    )
            if data_model is None:
                data_model = _fallback_step4(step1=step1_data, step2=step2_data)

        elif step == 5:
            if step1_data is None:
                raise HTTPException(status_code=409, detail="Step 1 data is required for step 5")
            if not branching_enabled:
                warnings.append(_issue("branching_disabled", "Ветвления отключены в настройках.", severity="low"))
                data_model = _fallback_step5(step1=step1_data, branching=False)
            else:
                system_prompt, user_prompt = _build_step5_prompt(
                    step1=step1_data,
                    language=language,
                    detail_level=detail_level,
                )
                payload_json, llm_meta = await self._call_llm_json(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=0.5,
                    max_tokens=1200,
                    strict=strict,
                    warnings=warnings,
                    context="step5",
                )
                payload_json = _unwrap_data(payload_json) if payload_json else None
                if payload_json:
                    try:
                        data_model = Step5Data.model_validate(payload_json)
                    except Exception as exc:
                        if strict:
                            raise HTTPException(status_code=502, detail=f"LLM payload invalid: {exc}")
                        self._log_invalid_payload(step=step, payload=payload_json, error=exc)
                        warnings.append(
                            _issue(
                                "validation_failed",
                                "LLM вернул данные, не прошедшие проверку; использован fallback.",
                                severity="high",
                                hint=_safe_str(exc, max_len=200),
                            )
                        )
                if data_model is None:
                    data_model = _fallback_step5(step1=step1_data, branching=branching_enabled)

        elif step == 6:
            if step3_data is None:
                raise HTTPException(status_code=409, detail="Step 3 data is required for step 6")
            system_prompt, user_prompt = _build_step6_prompt(
                step1=step1_data,
                step2=step2_data,
                step3=step3_data,
                language=language,
                detail_level=detail_level,
            )
            payload_json, llm_meta = await self._call_llm_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.4,
                max_tokens=1200,
                strict=strict,
                warnings=warnings,
                context="step6",
            )
            payload_json = _unwrap_data(payload_json) if payload_json else None
            if payload_json:
                try:
                    data_model = Step6Data.model_validate(payload_json)
                except Exception as exc:
                    if strict:
                        raise HTTPException(status_code=502, detail=f"LLM payload invalid: {exc}")
                    self._log_invalid_payload(step=step, payload=payload_json, error=exc)
                    warnings.append(
                        _issue(
                            "validation_failed",
                            "LLM вернул данные, не прошедшие проверку; использован fallback.",
                            severity="high",
                            hint=_safe_str(exc, max_len=200),
                        )
                    )
            if data_model is None:
                data_model = _fallback_step6(step3=step3_data)

        elif step == 7:
            if any(item is None for item in [step1_data, step2_data, step3_data, step4_data, step5_data, step6_data]):
                raise HTTPException(status_code=409, detail="Steps 1-6 are required for step 7")
            critic_system_prompt = self._load_step7_critic_system_prompt(language)
            system_prompt, user_prompt = _build_step7_prompt(
                story_input=story_input,
                step1=step1_data,
                step2=step2_data,
                step3=step3_data,
                step4=step4_data,
                step5=step5_data,
                step6=step6_data,
                language=language,
                detail_level=detail_level,
                critic_system_prompt=critic_system_prompt,
            )
            payload_json, llm_meta = await self._call_llm_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.2,
                max_tokens=1700,
                model=self.settings.wizard_critic_model,
                strict=strict,
                warnings=warnings,
                context="step7_critic",
            )
            payload_json = _unwrap_data(payload_json) if payload_json else None
            if payload_json:
                try:
                    data_model = _normalize_step7_data(Step7Data.model_validate(payload_json))
                except Exception as exc:
                    if strict:
                        raise HTTPException(status_code=502, detail=f"LLM payload invalid: {exc}")
                    self._log_invalid_payload(step=step, payload=payload_json, error=exc)
                    warnings.append(
                        _issue(
                            "validation_failed",
                            "LLM вернул данные, не прошедшие проверку; использован fallback.",
                            severity="high",
                            hint=_safe_str(exc, max_len=200),
                        )
                    )
            if data_model is None:
                data_model = _fallback_step7(
                    story_input=story_input,
                    step1=step1_data,
                    step2=step2_data,
                    step3=step3_data,
                    step4=step4_data,
                    step5=step5_data,
                    step6=step6_data,
                )
                warnings.append(
                    _issue(
                        "critic_fallback",
                        "Шаг 7 выполнен fallback-анализом (без полноценного LLM-ответа).",
                        severity="medium",
                    )
                )
            unresolved_blockers = self._step7_unresolved_blockers(data_model)
            if unresolved_blockers:
                author_hints = self._author_blocker_hints(
                    unresolved_blockers,
                    step1=step1_data,
                    step2=step2_data,
                    step3=step3_data,
                    step5=step5_data,
                )
                errors.append(
                    _issue(
                        "critic_blockers",
                        (
                            f"Обнаружены существенные замечания: {len(unresolved_blockers)}. "
                            + (f"Расшифровка: {'; '.join(author_hints[:2])}" if author_hints else "")
                        ).strip(),
                        severity="high",
                        hint="Пока они не устранены, развёртывание в проект будет заблокировано.",
                    )
                )
            elif data_model.issues:
                warnings.append(
                    _issue(
                        "critic_issues",
                        f"Обнаружены замечания: {len(data_model.issues)}.",
                        severity="medium",
                    )
                )

        else:
            raise HTTPException(status_code=400, detail="Unsupported step")

        usage: Optional[Dict[str, Any]] = None
        trace_id = None
        if llm_meta:
            usage = {"model": llm_meta.get("model")}
            llm_usage = llm_meta.get("usage")
            if isinstance(llm_usage, dict):
                if "prompt_tokens" in llm_usage:
                    usage["tokens_in"] = llm_usage.get("prompt_tokens")
                if "completion_tokens" in llm_usage:
                    usage["tokens_out"] = llm_usage.get("completion_tokens")
            trace_id = llm_meta.get("request_id")

        meta = {
            "step": step,
            "mode": "draft",
            "status": "error" if errors else ("warning" if warnings else "ok"),
            "warnings": warnings,
            "errors": errors,
            "usage": usage,
            "trace_id": trace_id,
            "generated_at": datetime.utcnow().isoformat(),
        }

        result = await self.save_step(session_id, step, data_model.model_dump(), meta=meta)
        if result is None:
            raise HTTPException(status_code=404, detail="Wizard session not found")
        if step == 7:
            wizard_after = await self.get_session(session_id)
            if wizard_after is not None:
                drafts_after, approvals_after, meta_after = self._get_payload_maps(wizard_after)
                current_override = self._step7_override_from_meta(meta_after)
                if current_override.get("enabled"):
                    step7_saved = Step7Data.model_validate((drafts_after.get("7") or {}))
                    step7_meta_saved = meta_after.get("7") if isinstance(meta_after.get("7"), dict) else {}
                    current_override["enabled"] = False
                    current_override["updated_at"] = datetime.utcnow().isoformat()
                    current_override["reason"] = (
                        "Автоматически отключено после нового прогона шага 7. "
                        "Подтвердите ручную разблокировку заново при необходимости."
                    )
                    current_override["critic_generated_at"] = (
                        _safe_str(step7_meta_saved.get("generated_at"), max_len=80) or None
                    )
                    meta_after["step7_deploy_override"] = current_override
                    wizard_after.drafts = drafts_after
                    wizard_after.approvals = approvals_after
                    wizard_after.meta = meta_after
                    await self.session.commit()
                    try:
                        self._write_project_description_override(
                            wizard=wizard_after,
                            step7=step7_saved,
                            override_state=current_override,
                            source="step7_rerun",
                        )
                    except Exception as exc:
                        logger.warning(
                            "Failed to sync project description file after step7 override invalidation: %s",
                            exc,
                        )
                    await self.session.refresh(wizard_after)
                    result = {
                        "data": drafts_after.get("7"),
                        "meta": meta_after.get("7"),
                    }
        return result
