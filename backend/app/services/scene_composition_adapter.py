from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping

from app.infra.translator import get_translator, is_cyrillic


_CROWD_HINTS = (
    "crowd",
    "bystander",
    "bystanders",
    "passerby",
    "passersby",
    "pedestrian",
    "pedestrians",
    "audience",
    "background people",
    "background person",
    "extras",
    "extra people",
    "толпа",
    "прохож",
    "фонов",
    "статист",
)

_CROWD_STRONG_HINTS = (
    "background extras",
    "background people",
    "crowd in the background",
    "busy street with pedestrians",
    "passersby in frame",
    "статисты на фоне",
    "прохожие в кадре",
    "толпа на улице",
    "людная улица",
    "много прохожих",
)

_CROWD_PRESENCE_HINTS = (
    "in frame",
    "on screen",
    "in the background",
    "behind them",
    "around them",
    "around the characters",
    "в кадре",
    "на фоне",
    "позади",
    "вокруг",
)

_POSITION_HINTS = {
    "left": "Place the principal character from this slot on the left side of the frame.",
    "center": "Place the principal character from this slot at the center of the frame.",
    "right": "Place the principal character from this slot on the right side of the frame.",
    "foreground": "Keep this principal character in the foreground plane, closest to the camera.",
    "background": "Keep this principal character behind the foreground subject but still clearly visible and identifiable.",
}

_ACTION_CONTEXT_KEYS = (
    "action",
    "story_action",
    "visual_action",
    "user_prompt",
    "visual",
    "title",
    "exposition",
    "thought",
)

# Backup legacy role wording (kept intentionally for rollback and prompt A/B checks).
LEGACY_IMAGE_ROLE_GUIDANCE = """Always state image roles explicitly:
- image 1: background/lighting/composition (primary context)
- image 2: face/head reference for character 1 (highest priority)
- image 3: body/pose reference for character 1 OR character 2 if two distinct characters are provided"""

# Active role wording: slot-based identities without names.
IMAGE_ROLE_GUIDANCE = """Always state image roles explicitly:
- image 1: immutable background plate (authoritative geometry, camera, and lighting)
- image 2: Character from Image 2 (principal subject A, face/head identity anchor)
- image 3: Character from Image 3 (principal subject B when present; otherwise optional body/pose reference for Character from Image 2)
- Treat Character from Image 2 and Character from Image 3 as different people when both are present.
- Never use character names, aliases, or nicknames; refer only to slot labels."""


@dataclass(frozen=True)
class BackgroundExtrasPolicy:
    allowed: bool
    min_count: int = 0
    max_count: int = 0
    note: str = ""

    @property
    def has_extras(self) -> bool:
        return self.allowed and self.max_count > 0


def _clean_text_fragment(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split()).strip()


def build_slot_character_list(*, principal_count: int) -> str:
    if principal_count <= 0:
        return "no principal character slots are used"
    if principal_count == 1:
        return (
            "image 2: Character from Image 2 (principal subject, face/head identity anchor); "
            "image 3: optional body/pose guidance for Character from Image 2 only"
        )
    return (
        "image 2: Character from Image 2 (principal subject A, distinct identity); "
        "image 3: Character from Image 3 (principal subject B, distinct identity)"
    )


def enforce_slot_identity_labels(
    text: str,
    *,
    slot2_name: str | None = None,
    slot3_name: str | None = None,
) -> str:
    normalized = " ".join((text or "").split())
    if not normalized:
        return normalized

    alias_map = [
        (slot2_name, "Character from Image 2"),
        (slot3_name, "Character from Image 3"),
    ]
    for raw_name, label in alias_map:
        name = _clean_text_fragment(raw_name)
        if not name:
            continue
        pattern = re.compile(rf"(?i)\b{re.escape(name)}(?:['’]s)?\b")
        normalized = pattern.sub(label, normalized)

    normalized = re.sub(r"(?i)\bcharacter\s*1\b", "Character from Image 2", normalized)
    normalized = re.sub(r"(?i)\bfirst character\b", "Character from Image 2", normalized)
    normalized = re.sub(r"(?i)\bcharacter\s*2\b", "Character from Image 3", normalized)
    normalized = re.sub(r"(?i)\bsecond character\b", "Character from Image 3", normalized)
    normalized = re.sub(r"(?i)\bprincipal subject A\b", "Character from Image 2", normalized)
    normalized = re.sub(r"(?i)\bprincipal subject B\b", "Character from Image 3", normalized)
    return " ".join(normalized.split())


def _normalize_position(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    raw = value.strip().lower()
    return raw if raw in _POSITION_HINTS else None


def _join_unique(parts: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in parts:
        normalized = item.strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(normalized)
    return ordered


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            return None
    return None


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        raw = value.strip().lower()
        if raw in {"1", "true", "yes", "y", "on"}:
            return True
        if raw in {"0", "false", "no", "n", "off"}:
            return False
    return None


def _context_mentions_background_people(text: str) -> bool:
    lower = (text or "").lower()
    if not lower:
        return False
    if any(token in lower for token in _CROWD_STRONG_HINTS):
        return True
    has_crowd_token = any(token in lower for token in _CROWD_HINTS)
    if not has_crowd_token:
        return False
    return any(token in lower for token in _CROWD_PRESENCE_HINTS)


def _policy_from_mapping(raw: Mapping[str, Any]) -> BackgroundExtrasPolicy | None:
    allow_keys = (
        "allowed",
        "allow",
        "enabled",
        "allow_background_extras",
        "allow_extras",
        "allow_background_people",
    )
    count_keys = ("count", "background_extras_count", "extras_count", "background_people_count")
    min_keys = ("min", "background_extras_min", "extras_min")
    max_keys = ("max", "background_extras_max", "extras_max")
    note_keys = ("note", "background_extras_note", "extras_note")

    allowed: bool | None = None
    exact_count: int | None = None
    min_count: int | None = None
    max_count: int | None = None
    note = ""

    for key in allow_keys:
        if key in raw:
            parsed = _coerce_bool(raw.get(key))
            if parsed is not None:
                allowed = parsed
                break
    for key in count_keys:
        if key in raw:
            exact_count = _coerce_int(raw.get(key))
            if exact_count is not None:
                break
    for key in min_keys:
        if key in raw:
            min_count = _coerce_int(raw.get(key))
            if min_count is not None:
                break
    for key in max_keys:
        if key in raw:
            max_count = _coerce_int(raw.get(key))
            if max_count is not None:
                break
    for key in note_keys:
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            note = value.strip()
            break

    if exact_count is not None:
        exact_count = max(0, exact_count)
        return BackgroundExtrasPolicy(
            allowed=exact_count > 0 if allowed is None else bool(allowed and exact_count > 0),
            min_count=exact_count,
            max_count=exact_count,
            note=note,
        )

    if min_count is not None or max_count is not None:
        lo = max(0, min_count or 0)
        hi = max(0, max_count if max_count is not None else lo)
        if hi < lo:
            hi = lo
        final_allowed = (hi > 0) if allowed is None else bool(allowed and hi > 0)
        return BackgroundExtrasPolicy(
            allowed=final_allowed,
            min_count=lo if final_allowed else 0,
            max_count=hi if final_allowed else 0,
            note=note,
        )

    if allowed is not None:
        if not allowed:
            return BackgroundExtrasPolicy(allowed=False, min_count=0, max_count=0, note=note)
        return BackgroundExtrasPolicy(allowed=True, min_count=1, max_count=3, note=note)

    return None


def infer_background_extras_policy(
    *,
    slide_context: Mapping[str, Any] | None,
    context_text: str,
    principal_count: int,
    requested_cast_count: int | None = None,
) -> BackgroundExtrasPolicy:
    explicit_allow: bool | None = None
    if isinstance(slide_context, Mapping):
        allow_keys = (
            "allow_background_extras",
            "allow_extras",
            "background_extras_allowed",
            "allow_background_people",
            "allow_crowd",
        )
        for key in allow_keys:
            if key in slide_context:
                parsed = _coerce_bool(slide_context.get(key))
                if parsed is not None:
                    explicit_allow = parsed
                    if not parsed:
                        return BackgroundExtrasPolicy(allowed=False, min_count=0, max_count=0)
                    break

        direct_count_keys = (
            "background_extras_count",
            "extras_count",
            "background_people_count",
            "crowd_count",
        )
        for key in direct_count_keys:
            count = _coerce_int(slide_context.get(key))
            if count is not None:
                count = max(0, count)
                return BackgroundExtrasPolicy(
                    allowed=count > 0,
                    min_count=count,
                    max_count=count,
                )

        range_min = _coerce_int(slide_context.get("background_extras_min")) if "background_extras_min" in slide_context else None
        range_max = _coerce_int(slide_context.get("background_extras_max")) if "background_extras_max" in slide_context else None
        if range_min is not None or range_max is not None:
            lo = max(0, range_min or 0)
            hi = max(0, range_max if range_max is not None else lo)
            if hi < lo:
                hi = lo
            return BackgroundExtrasPolicy(allowed=hi > 0, min_count=lo, max_count=hi)

        for key in ("background_extras", "extras", "background_characters"):
            value = slide_context.get(key)
            if isinstance(value, Mapping):
                parsed = _policy_from_mapping(value)
                if parsed is not None:
                    return parsed
            elif isinstance(value, list):
                count = len(value)
                return BackgroundExtrasPolicy(
                    allowed=count > 0,
                    min_count=count,
                    max_count=count,
                )
            else:
                count = _coerce_int(value)
                if count is not None:
                    count = max(0, count)
                    return BackgroundExtrasPolicy(
                        allowed=count > 0,
                        min_count=count,
                        max_count=count,
                    )

        if explicit_allow is True:
            return BackgroundExtrasPolicy(
                allowed=True,
                min_count=1,
                max_count=3,
                note="Only if story context explicitly requires background people in-frame.",
            )

    cast_total = max(0, requested_cast_count or 0)
    unresolved_cast = max(0, cast_total - max(0, principal_count))
    if unresolved_cast > 0:
        return BackgroundExtrasPolicy(
            allowed=False,
            min_count=0,
            max_count=0,
            note=(
                f"Requested cast ({cast_total}) exceeds available principal slots ({principal_count}); "
                "do not convert unresolved cast into extras."
            ),
        )

    lower_context = (context_text or "").lower()
    if _context_mentions_background_people(lower_context):
        return BackgroundExtrasPolicy(
            allowed=True,
            min_count=1,
            max_count=5,
        )

    return BackgroundExtrasPolicy(allowed=False, min_count=0, max_count=0)


def build_people_constraints(
    *,
    principal_count: int,
    has_location_reference: bool,
    extras_policy: BackgroundExtrasPolicy,
) -> list[str]:
    rules: list[str] = []
    if principal_count <= 0:
        rules.append("Render no principal cast characters in the foreground.")
    elif principal_count == 1:
        rules.append(
            "Render exactly 1 principal character from image 2 (Character from Image 2); do not duplicate this identity."
        )
    else:
        rules.append(
            f"Render exactly {principal_count} principal characters from image slots 2 and 3; Character from Image 2 and Character from Image 3 are different identities; no duplicates."
        )
    if principal_count > 0:
        rules.append("Keep all principal characters clearly visible in frame; no full occlusion.")

    if extras_policy.has_extras:
        if extras_policy.min_count == extras_policy.max_count:
            rules.append(
                f"Allow exactly {extras_policy.max_count} additional background extras; keep them secondary and non-identifiable."
            )
        else:
            rules.append(
                f"Allow only {extras_policy.min_count}-{extras_policy.max_count} background extras; keep them secondary and non-identifiable."
            )
        if extras_policy.note:
            rules.append(extras_policy.note)
    else:
        rules.append("Do not add extra people beyond the principal character count.")
        rules.append("No bystanders, pedestrians, crowd, or silhouette people in frame.")
        rules.append(
            "No additional humans of any kind (including silhouettes, reflections, posters, photos, mannequins)."
        )
        if extras_policy.note:
            rules.append(extras_policy.note)

    if has_location_reference:
        rules.append("Treat image 1 as authoritative for scene geometry and camera layout.")
    else:
        rules.append("Build background only from text; keep composition coherent without random objects.")
    return rules


def build_story_action_hint(
    *,
    slide_context: Mapping[str, Any] | None,
    slide_visual: str | None,
    scene_synopsis: str | None,
) -> str:
    parts: list[str] = []
    if isinstance(slide_context, Mapping):
        for key in _ACTION_CONTEXT_KEYS:
            cleaned = _clean_text_fragment(slide_context.get(key))
            if cleaned:
                parts.append(cleaned)
        dialogue = slide_context.get("dialogue")
        if isinstance(dialogue, list):
            for line in dialogue:
                if not isinstance(line, Mapping):
                    continue
                speaker = _clean_text_fragment(line.get("speaker"))
                text = _clean_text_fragment(line.get("text"))
                if not text:
                    continue
                parts.append(f"{speaker}: {text}" if speaker else text)
    if not parts:
        fallback_visual = _clean_text_fragment(slide_visual)
        if fallback_visual:
            parts.append(fallback_visual)
    synopsis = _clean_text_fragment(scene_synopsis)
    if synopsis:
        parts.append(synopsis)
    joined = "; ".join(_join_unique(parts))
    if len(joined) > 420:
        joined = joined[:420].rstrip(" ,.;:") + "..."
    return ensure_english_prompt(joined) if joined else ""


def build_composition_guardrails(
    *,
    principal_count: int,
    has_location_reference: bool,
    slot_positions: list[str | None] | None,
    action_hint: str | None,
) -> list[str]:
    rules: list[str] = []
    if has_location_reference:
        rules.append(
            "Use image 1 as an immutable background plate; preserve architecture, perspective, camera angle, and lighting layout unchanged."
        )
    else:
        rules.append("Build a coherent background from text and keep camera layout physically consistent.")

    if principal_count > 0:
        rules.append(
            "Integrate principal characters into scene depth as grounded actors in front of image 1; avoid cutout-sticker look and do not fuse characters into walls, floor, props, or distant background."
        )
        rules.append(
            "Use slot labels only for people: Character from Image 2 and Character from Image 3. Never use character names."
        )
        rules.append(
            "Preserve face identity, body proportions, and recognizable silhouette from character reference images."
        )
        rules.append(
            "Maintain continuity of wardrobe, hairstyle, age cues, and signature accessories for each slot identity unless the story beat explicitly changes them."
        )
        rules.append(
            "Maintain realistic contact shadows and depth separation between foreground characters and the background plate."
        )
        rules.append(
            "Characters must perform visible story-driven actions; avoid idle standing, poster-like posing, or static front-facing lineup."
        )
        rules.append(
            "Maintain scene continuity in weather, time-of-day mood, and practical lighting between adjacent shots unless explicitly changed by the story beat."
        )
        if principal_count > 1:
            rules.append(
                "Character from Image 2 and Character from Image 3 must interact through complementary visible actions tied to the story beat."
            )
            rules.append(
                "Keep Character from Image 2 and Character from Image 3 as separate, non-merged identities with distinct appearance."
            )
        else:
            rules.append("Character from Image 2 must perform one clear visible action tied to the story beat.")

    positions = slot_positions or []
    for idx in range(min(principal_count, 2)):
        normalized = _normalize_position(positions[idx] if idx < len(positions) else None)
        if normalized:
            rules.append(f"Image slot {idx + 2}: {_POSITION_HINTS[normalized]}")
        elif principal_count == 1 and idx == 0:
            rules.append("Image slot 2: keep the principal character centered and dominant in frame.")
        elif principal_count > 1:
            if idx == 0:
                rules.append("Image slot 2: keep this character clearly on the left half of the frame.")
            elif idx == 1:
                rules.append("Image slot 3: keep this character clearly on the right half of the frame.")

    hint = _clean_text_fragment(action_hint)
    if hint:
        rules.append(f"Visible actions and interaction must match this story beat: {hint}.")
        rules.append("Assign concrete visible actions to each principal character; avoid neutral waiting poses.")
        rules.append("Do not invent unrelated gestures, poses, or story actions.")
    return rules


def build_composition_negative_prompt(
    *,
    principal_count: int,
    extras_policy: BackgroundExtrasPolicy,
) -> str:
    negative_parts = [
        "identity swap",
        "duplicated person",
        "multiple versions of same character",
        "cloned face",
        "face drift",
        "face changed",
        "age drift",
        "outfit drift",
        "different outfit",
        "hairstyle drift",
        "different hairstyle",
        "different ethnicity",
        "different skin tone",
        "extra limbs",
        "merged body with background",
        "cutout collage",
        "sticker look",
        "character fused into wall",
        "character fused into floor",
        "floating character",
        "incorrect depth",
        "static lineup",
        "idle standing pose",
        "poster pose",
        "front-facing mugshot pose",
        "wrong action",
        "random pose",
    ]
    if principal_count <= 1:
        negative_parts.extend(["two people", "group shot", "crowd"])
    elif principal_count == 2:
        negative_parts.extend(["three people", "large group", "crowd"])
    if not extras_policy.has_extras:
        negative_parts.extend(["background extras", "bystanders", "passersby"])
    return ", ".join(_join_unique(negative_parts))


def normalize_composition_prompt(
    *,
    prompt: str,
    people_constraints_text: str,
    guardrails: list[str],
    gritty: bool,
    principal_count: int,
) -> str:
    cleaned = " ".join((prompt or "").split())
    identity_lock = ""
    if principal_count == 1:
        identity_lock = (
            "Identity lock: Character from Image 2 is a fixed ID anchor; keep face, age, hairstyle, outfit, "
            "skin tone, and signature accessories unchanged."
        )
    elif principal_count > 1:
        identity_lock = (
            "Identity lock: Character from Image 2 and Character from Image 3 are fixed ID anchors; "
            "keep each face, age, hairstyle, outfit, skin tone, and signature accessories unchanged."
        )

    def _split_clauses(text: str) -> list[str]:
        if not text:
            return []
        raw = re.split(r"(?:[.;!?]\s+)|(?:\s*;\s*)", text)
        return _join_unique([item.strip(" .;,!") for item in raw if item and item.strip()])

    def _prioritize_guardrails(items: list[str]) -> list[str]:
        preferred = (
            "immutable background plate",
            "build a coherent background",
            "grounded actors",
            "preserve face identity",
            "keep all principal characters clearly visible",
            "must interact",
            "must perform",
            "slot 2",
            "slot 3",
            "do not invent unrelated",
        )
        selected: list[str] = []
        lowered = [item.lower() for item in items]
        for needle in preferred:
            for idx, low in enumerate(lowered):
                if needle in low:
                    selected.append(items[idx])
                    break
        if not selected:
            selected = items[:4]
        return _join_unique(selected)[:8]

    base_clauses = _split_clauses(cleaned)
    # Prevent over-constrained prompt drift from old/manual slide prompts.
    base_clauses = [
        clause
        for clause in base_clauses
        if clause.lower()
        not in {
            "preserve all unchanged elements exactly",
            "preserve unchanged background elements exactly",
        }
    ][:6]

    normalized_guardrails = [rule.strip() for rule in guardrails if isinstance(rule, str) and rule.strip()]
    mandatory: list[str] = []
    if people_constraints_text:
        mandatory.append(people_constraints_text)
    mandatory.extend(_prioritize_guardrails(normalized_guardrails))
    mandatory.append("High fidelity, seamless blend, photorealistic detail.")
    if gritty:
        mandatory.append("Raw realistic textures, detailed mud and dirt, no smoothing.")
    if principal_count > 0:
        mandatory.append("No extra principal characters.")
        mandatory.append("Characters must perform visible story-driven actions; avoid static lineup poses.")
    mandatory.append("Preserve background plate geometry, perspective, and lighting.")
    mandatory.append("Do not alter architecture or major props.")
    mandatory = _join_unique(mandatory)

    max_chars = 1600
    final_clauses: list[str] = []
    seen: set[str] = set()

    def _append_clause(clause: str) -> None:
        norm = " ".join((clause or "").split()).strip()
        if not norm:
            return
        key = norm.casefold()
        if key in seen:
            return
        candidate = ". ".join(final_clauses + [norm]).strip()
        if len(candidate) > max_chars:
            return
        seen.add(key)
        final_clauses.append(norm)

    if identity_lock:
        _append_clause(identity_lock)
    for clause in base_clauses:
        _append_clause(clause[:320])
    for clause in mandatory:
        _append_clause(clause[:420])

    result = ". ".join(final_clauses).strip()
    return ensure_english_prompt(result or cleaned)


def ensure_english_prompt(text: str) -> str:
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return cleaned
    if not is_cyrillic(cleaned):
        return cleaned
    translated = get_translator().translate(cleaned)
    translated = " ".join((translated or "").split())
    return translated or cleaned
