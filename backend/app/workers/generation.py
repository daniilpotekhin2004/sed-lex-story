import random
import base64
import asyncio
import json
import logging
import re
import time
import threading
from datetime import datetime
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload

from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.core.telemetry import track_event
from app.domain.models.generation_job import GenerationTaskType

from app.domain.models import (
    Artifact,
    CharacterPreset,
    GenerationJob,
    GenerationStatus,
    ImageVariant,
    Location,
    MaterialSet,
    SceneNode,
    SceneNodeCharacter,
)
from app.infra.db import SessionLocal
from app.infra.db import SyncSessionLocal
from app.infra.sd_request_layer import get_sd_layer, sd_provider_context
from app.infra.llm_client import create_chat_completion
from app.utils.sd_provider import SDProviderOverrides
from app.infra.storage import LocalImageStorage
from app.schemas.characters import CharacterRenderRequest
from app.schemas.generation_overrides import GenerationOverrides
from app.services.character import CHARACTER_REFERENCE_SLOTS, CharacterService
from app.services.character_lib import get_character_lib
from app.schemas.character_lib import ReferenceImageType
from app.services.scene_composition_adapter import (
    IMAGE_ROLE_GUIDANCE,
    LEGACY_IMAGE_ROLE_GUIDANCE,
    build_slot_character_list,
    build_composition_guardrails,
    build_composition_negative_prompt,
    build_people_constraints,
    build_story_action_hint,
    enforce_slot_identity_labels,
    ensure_english_prompt,
    infer_background_extras_policy,
    normalize_composition_prompt,
)
from app.services.world import WorldService

logger = logging.getLogger(__name__)

# Cache for ControlNet models
_controlnet_models_cache: list[str] | None = None


def _get_controlnet_models() -> list[str]:
    """Get list of available ControlNet models from SD API."""
    global _controlnet_models_cache
    if _controlnet_models_cache is not None:
        return _controlnet_models_cache
    try:
        sd_layer = get_sd_layer()
        _controlnet_models_cache = sd_layer.get_controlnet_models()
        logger.info(f"Loaded ControlNet models: {_controlnet_models_cache}")
        return _controlnet_models_cache
    except Exception as e:
        logger.warning(f"Failed to get ControlNet models: {e}")
        return []


def _find_controlnet_model(base_name: str) -> str | None:
    """
    Find a ControlNet model by base name, handling hash suffixes.
    
    SD Forge returns model names like "control_v11p_sd15_openpose [cab727d4]"
    but config might have just "control_v11p_sd15_openpose".
    """
    models = _get_controlnet_models()
    if not models:
        return None
    
    # First try exact match
    if base_name in models:
        return base_name
    
    # Try to find model that starts with base_name
    base_lower = base_name.lower()
    for model in models:
        model_lower = model.lower()
        # Match "control_v11p_sd15_openpose" in "control_v11p_sd15_openpose [cab727d4]"
        if model_lower.startswith(base_lower) or base_lower in model_lower:
            logger.info(f"Matched ControlNet model: {base_name} -> {model}")
            return model
    
    # Try partial match on key parts
    key_parts = base_name.lower().replace("control_", "").replace("_sd15", "").replace("v11p", "").replace("v11f1p", "")
    for model in models:
        if key_parts in model.lower():
            logger.info(f"Partial matched ControlNet model: {base_name} -> {model}")
            return model
    
    logger.warning(f"No ControlNet model found for: {base_name}, available: {models}")
    return None


def _encode_image_bytes(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _resolve_asset_path(url: str, assets_root: Path) -> Path | None:
    if not url or not url.startswith("/api/assets/"):
        return None
    rel = url[len("/api/assets/") :]
    return assets_root / rel


def _load_asset_bytes(url: str, assets_root: Path) -> bytes | None:
    path = _resolve_asset_path(url, assets_root)
    if not path or not path.exists():
        return None
    try:
        return path.read_bytes()
    except OSError:
        return None


def _merge_job_runtime_metadata(job: GenerationJob, key: str, value: dict) -> None:
    """Persist debug/runtime metadata into job.config without breaking existing keys."""
    config = dict(job.config) if isinstance(job.config, dict) else {}
    runtime = config.get("runtime_metadata")
    runtime_metadata = dict(runtime) if isinstance(runtime, dict) else {}
    runtime_metadata[key] = value
    config["runtime_metadata"] = runtime_metadata
    job.config = config


def _pick_reference_urls(preset: CharacterPreset) -> list[str]:
    urls: list[str] = []
    for ref in preset.reference_images or []:
        if not isinstance(ref, dict):
            continue
        url = ref.get("url") or ref.get("thumb_url") or ref.get("thumbnail_url")
        if url:
            urls.append(str(url))
    if preset.preview_image_url:
        urls.append(preset.preview_image_url)
    if preset.preview_thumbnail_url:
        urls.append(preset.preview_thumbnail_url)
    # Deduplicate while preserving order
    seen: set[str] = set()
    ordered: list[str] = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        ordered.append(url)
    return ordered


def _pick_location_reference_urls(location: Location) -> list[str]:
    urls: list[str] = []
    for ref in location.reference_images or []:
        if not isinstance(ref, dict):
            continue
        url = ref.get("url") or ref.get("thumb_url") or ref.get("thumbnail_url")
        if url:
            urls.append(str(url))
    if getattr(location, "preview_image_url", None):
        urls.append(str(location.preview_image_url))
    # Deduplicate while preserving order
    seen: set[str] = set()
    ordered: list[str] = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        ordered.append(url)
    return ordered


def _find_slide_context(scene: SceneNode, slide_id: str) -> dict | None:
    if not slide_id:
        return None
    context = scene.context if isinstance(scene.context, dict) else {}
    sequence = context.get("sequence") if isinstance(context.get("sequence"), dict) else {}
    slides = sequence.get("slides") if isinstance(sequence.get("slides"), list) else []
    for slide in slides:
        if isinstance(slide, dict) and slide.get("id") == slide_id:
            return slide
    return None


def _build_scene_composition_prompt(
    *,
    scene: SceneNode | None,
    slide_context: dict | None,
    character_notes: list[tuple[str, str]],
    location: Location | None,
    framing: str | None,
    has_location_reference: bool,
    slot_positions: list[str | None] | None = None,
    action_hint: str | None = None,
    requested_cast_count: int | None = None,
) -> str:
    """Generate composition-only prompt that references image slots (image 1/2/3)."""
    slide_visual = ""
    if isinstance(slide_context, dict):
        for key in ("user_prompt", "visual", "title"):
            value = slide_context.get(key)
            if isinstance(value, str) and value.strip():
                slide_visual = value.strip()
                break
    if not slide_visual and scene:
        slide_visual = scene.title or ""
    if not slide_visual:
        slide_visual = "Scene composition"

    location_desc = "the background scene"
    if location:
        location_desc = location.name or location_desc
        if location.description:
            location_desc += f" — {location.description[:150]}"

    framing_hint = {
        "full": "full body shot, showing entire figure",
        "half": "waist-up shot, half body",
        "portrait": "close-up portrait, head and shoulders",
    }.get(framing or "full", "full body shot")

    slot2_name = character_notes[0][0] if character_notes else None
    slot3_name = character_notes[1][0] if len(character_notes) > 1 else None
    principal_count = len(character_notes)
    char_list = build_slot_character_list(principal_count=principal_count)
    context_text = " ".join(
        [
            slide_visual or "",
            scene.synopsis if scene and scene.synopsis else "",
        ]
    ).lower()
    extras_policy = infer_background_extras_policy(
        slide_context=slide_context,
        context_text=context_text,
        principal_count=principal_count,
        requested_cast_count=requested_cast_count,
    )
    people_constraints = build_people_constraints(
        principal_count=principal_count,
        has_location_reference=has_location_reference,
        extras_policy=extras_policy,
    )
    people_constraints_text = " ".join(people_constraints)
    guardrails = build_composition_guardrails(
        principal_count=principal_count,
        has_location_reference=has_location_reference,
        slot_positions=slot_positions,
        action_hint=action_hint,
    )
    guardrails_text = " ".join(guardrails)
    gritty = any(
        token in context_text
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

    # Keep legacy wording as backup for quick rollback if needed.
    _ = LEGACY_IMAGE_ROLE_GUIDANCE

    system_prompt = f"""You create composition prompts for Qwen-Image-Edit.
Prefer short imperative phrases (no long narrative). Output a single paragraph of 80–150 tokens.
Order: Identity lock → Command → Preserve rules → Reference roles → Quality boosters → Anchor.
Output must be in English only.

{IMAGE_ROLE_GUIDANCE}

Rules:
1) Composition only (camera, framing, placement, lighting, spatial relationships).
2) No plot retelling or invisible details.
3) Use explicit phrases: "exact match", "no changes to X", "preserve X unchanged".
4) Avoid repetitions and phrases like "as identical as possible".
5) Include: high fidelity, seamless blend, photorealistic detail.
6) If gritty/mud/NSFW/skin texture is mentioned, add: raw realistic textures, detailed mud and dirt, no smoothing.
7) Follow numeric people constraints exactly (no extra principal characters).
8) Integrate principal characters as grounded actors inside the scene depth; never as static pasted cutouts.
9) Characters must perform visible story-driven actions; with two principals, they must interact through complementary actions.
10) Respect slot position hints and visible story actions exactly.
11) Start the prompt with a short identity-lock sentence for slot characters.

End with: Preserve background plate geometry, perspective, and lighting. Do not alter architecture or major props."""

    user_prompt = f"""Generate a composition prompt for this scene.
Return only the prompt.
Critical: this is a cinematic story frame, not a collage. Characters must act and interact according to the action cue.

Scene context: {scene.title if scene else 'Untitled scene'}
{f"Synopsis: {scene.synopsis[:200]}" if scene and scene.synopsis else ""}

Location/Background (image 1): {location_desc}
Image 1 available as visual reference: {"yes" if has_location_reference else "no (may be blank)"}
Characters to place (by image slot only, no names): {char_list}
Framing: {framing_hint}
People/scene constraints: {people_constraints_text}
Action cue: {action_hint or "no explicit action cue provided"}
Dynamic staging guardrails: {guardrails_text}

Visual description (composition notes): {slide_visual}"""

    def _fallback() -> str:
        if has_location_reference:
            parts = [
                f"Use image 1 as the background and lighting reference ({location_desc}); preserve its layout unchanged."
            ]
        else:
            parts = [
                f"Generate the background environment and lighting from the description ({location_desc}); image 1 may be blank and should not constrain composition."
            ]
        if action_hint:
            parts.append(f"Use this story beat for visible actions: {action_hint}.")
        if principal_count > 0 and character_notes:
            parts.append(
                f"Stage Character from Image 2 as an active actor; exact match for face/head; {framing_hint}."
            )
            if len(character_notes) > 1:
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
        else:
            parts.append("Do not place principal cast characters in the frame.")
        if slide_visual:
            parts.append(f"Apply composition notes: {slide_visual}.")
        parts.append(people_constraints_text)
        parts.extend(guardrails)
        parts.append("High fidelity, seamless blend, photorealistic detail.")
        if gritty:
            parts.append("Raw realistic textures, detailed mud and dirt, no smoothing.")
        parts.append("Preserve background plate geometry, perspective, and lighting.")
        parts.append("Do not alter architecture or major props.")
        fallback_text = ensure_english_prompt(" ".join(parts))
        return enforce_slot_identity_labels(
            fallback_text,
            slot2_name=slot2_name,
            slot3_name=slot3_name,
        )

    def _normalize_prompt(prompt: str) -> str:
        normalized = normalize_composition_prompt(
            prompt=prompt,
            people_constraints_text=people_constraints_text,
            guardrails=guardrails,
            gritty=gritty,
            principal_count=principal_count,
        )
        return enforce_slot_identity_labels(
            normalized,
            slot2_name=slot2_name,
            slot3_name=slot3_name,
        )

    try:
        response = asyncio.run(
            create_chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.6,
                max_tokens=200,
            )
        )
        content = (
            response.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        return _normalize_prompt(content) if content else _fallback()
    except Exception as exc:
        logger.warning("Qwen composition prompt generation failed: %s", exc)
        return _fallback()


def _normalize_lib_id(value: str | None) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if raw.startswith("lib:"):
        raw = raw[4:].strip()
    elif raw.startswith("library:"):
        raw = raw[8:].strip()
    return raw or None


def _build_library_prompt_parts(lib_char) -> tuple[list[str], list[str]]:
    prompt_parts: list[str] = []
    negative_parts: list[str] = []
    if getattr(lib_char, "name", None):
        prompt_parts.append(str(lib_char.name))
    if getattr(lib_char, "description", None):
        prompt_parts.append(str(lib_char.description))
    if getattr(lib_char, "appearance_prompt", None):
        prompt_parts.append(str(lib_char.appearance_prompt))
    if getattr(lib_char, "style_tags", None):
        try:
            prompt_parts.extend([str(t) for t in lib_char.style_tags if t])
        except Exception:
            pass
    negative = getattr(lib_char, "negative_prompt", None)
    if negative:
        negative_parts.append(str(negative))
    return prompt_parts, negative_parts


def _load_library_cast(
    cast_ids: list[str] | None,
    scene_cast: list[SceneNodeCharacter],
    settings,
) -> list[object]:
    if not cast_ids or not settings.character_lib_enabled:
        return []
    lib = get_character_lib()
    seen: set[str] = set()
    for sc in scene_cast:
        if sc.id:
            seen.add(sc.id)
        if sc.character_preset_id:
            seen.add(sc.character_preset_id)
    results: list[object] = []
    for raw in cast_ids:
        cid = _normalize_lib_id(raw)
        if not cid or cid in seen:
            continue
        char = lib.get_character(cid)
        if char:
            results.append(char)
            seen.add(cid)
    return results


def _pick_library_reference_images(
    lib_char,
) -> list[bytes]:
    """Pick a small ordered set of reference images (face then body)."""
    lib = get_character_lib()
    refs: list[bytes] = []
    try:
        face_refs = lib.get_character_references(
            lib_char.id,
            types=[ReferenceImageType.PORTRAIT, ReferenceImageType.EXPRESSION],
        )
        if face_refs:
            refs.append(face_refs[0][1])
    except Exception:
        pass
    try:
        body_refs = lib.get_character_references(
            lib_char.id,
            types=[
                ReferenceImageType.FULL_BODY,
                ReferenceImageType.SIDE_VIEW,
                ReferenceImageType.BACK_VIEW,
                ReferenceImageType.POSE,
                ReferenceImageType.OUTFIT,
            ],
        )
        if body_refs:
            refs.append(body_refs[0][1])
    except Exception:
        pass
    if refs:
        return refs
    # Fallback: any available reference
    try:
        any_refs = lib.get_character_references(lib_char.id)
        for _, data in any_refs[:2]:
            refs.append(data)
    except Exception:
        pass
    return refs


def _merge_scripts(*scripts: dict | None) -> dict | None:
    merged: dict = {}
    for payload in scripts:
        if isinstance(payload, dict):
            merged.update(payload)
    return merged or None


def _extract_face_ref_key(preset: CharacterPreset | None) -> str | None:
    if not preset or not isinstance(getattr(preset, "appearance_profile", None), dict):
        return None
    profile = preset.appearance_profile or {}
    visual = profile.get("visual_profile") if isinstance(profile.get("visual_profile"), dict) else {}
    identity = visual.get("identity") if isinstance(visual.get("identity"), dict) else {}
    face_ref = identity.get("face_ref")
    return str(face_ref) if isinstance(face_ref, str) and face_ref else None


def _pick_face_reference_url(
    preset: CharacterPreset | None,
    material: MaterialSet | None,
) -> str | None:
    refs = material.reference_images if material and material.reference_images else None
    if not isinstance(refs, list):
        refs = preset.reference_images if preset and isinstance(preset.reference_images, list) else None
    if not refs:
        return None

    face_key = _extract_face_ref_key(preset)
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        ref_id = ref.get("id")
        url = ref.get("url") or ref.get("thumb_url") or ref.get("thumbnail_url")
        if face_key and (face_key == ref_id or face_key == url):
            return str(url) if url else None

    preferred_kinds = {"sketch", "complex", "portrait", "profile", "full_front", "canonical"}
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        if ref.get("kind") in preferred_kinds:
            url = ref.get("url") or ref.get("thumb_url") or ref.get("thumbnail_url")
            if url:
                return str(url)

    for ref in refs:
        if not isinstance(ref, dict):
            continue
        url = ref.get("url") or ref.get("thumb_url") or ref.get("thumbnail_url")
        if url:
            return str(url)

    return None


def _render_roop_template(template: str, values: dict) -> dict | None:
    if not template:
        return None
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    try:
        payload = json.loads(rendered)
    except json.JSONDecodeError:
        logger.warning("Failed to parse ROOP_ALWAYS_ON_TEMPLATE JSON")
        return None
    return payload if isinstance(payload, dict) else None


def _run_async_job(coro: asyncio.coroutines) -> None:
    """Run an async job from sync context, even if a loop is already running."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(coro)
        return

    error: list[BaseException] = []

    def _runner() -> None:
        try:
            asyncio.run(coro)
        except BaseException as exc:
            error.append(exc)

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()
    if error:
        raise error[0]


def _build_roop_scripts(
    cast: list[SceneNodeCharacter],
    settings,
    assets_root: Path,
) -> dict | None:
    template = (settings.roop_alwayson_template or "").strip()
    if not template:
        return None
    if settings.roop_require_single and len(cast) != 1:
        return None
    link = cast[0]
    source_url = _pick_face_reference_url(link.character_preset, link.material_set)
    if not source_url:
        return None
    source_data = _load_asset_bytes(source_url, assets_root)
    if not source_data:
        return None
    return _render_roop_template(template, {"source_image": _encode_image_bytes(source_data)}) or None


def _extract_reference_urls(refs: list | None) -> list[str]:
    urls: list[str] = []
    for ref in refs or []:
        if not isinstance(ref, dict):
            continue
        url = ref.get("url") or ref.get("thumb_url") or ref.get("thumbnail_url")
        if url:
            urls.append(str(url))
    seen: set[str] = set()
    ordered: list[str] = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        ordered.append(url)
    return ordered


def _compose_pose_map(
    pose_images: list[bytes],
    width: int,
    height: int,
    positions: list[str | None],
    framing: str | None,
) -> bytes:
    canvas = Image.new("RGB", (width, height), color=(0, 0, 0))
    if not pose_images:
        buffer = BytesIO()
        canvas.save(buffer, format="PNG")
        return buffer.getvalue()

    if framing == "half":
        scale_base = 0.65
    elif framing == "portrait":
        scale_base = 0.5
    else:
        scale_base = 0.85

    count = len(pose_images)
    default_centers = [((idx + 1) / (count + 1)) for idx in range(count)]
    center_map = {"left": 0.25, "center": 0.5, "right": 0.75}

    for idx, data in enumerate(pose_images):
        try:
            image = Image.open(BytesIO(data)).convert("RGBA")
        except Exception:
            continue

        label = positions[idx] if idx < len(positions) else None
        center = center_map.get(label or "", default_centers[idx])
        scale = scale_base
        if label == "foreground":
            scale *= 1.1
            center = 0.5
        elif label == "background":
            scale *= 0.85
            center = 0.5

        target_h = max(8, int(height * scale))
        ratio = target_h / image.height
        target_w = max(8, int(image.width * ratio))
        resized = image.resize((target_w, target_h), Image.BICUBIC)
        x = int(center * width - target_w / 2)
        if framing == "portrait":
            y = int(height * 0.5 - target_h / 2)
        else:
            y = height - target_h
        canvas.paste(resized, (x, y), resized)

    buffer = BytesIO()
    canvas.save(buffer, format="PNG")
    return buffer.getvalue()


async def _process_asset_generation_job_v2(job_id: str) -> None:
    """Process a non-scene GenerationJob (characters/locations/artifacts) using async services.

    This keeps API requests fast by moving heavy SD/Comfy work into Celery while still
    reusing the existing service-layer generation logic.
    """

    # Local imports to avoid pulling async-only deps at Celery boot time.
    from app.infra.db import SessionLocal
    from app.services.character import CharacterService
    from app.services.world import WorldService
    from app.schemas.generation_overrides import GenerationOverrides
    from app.schemas.characters import CharacterRenderRequest

    async with SessionLocal() as session:
        job = await session.get(GenerationJob, job_id)
        if job is None:
            raise RuntimeError(f"Job {job_id} not found")

        job.status = GenerationStatus.RUNNING
        job.stage = "running"
        job.progress = 0
        job.started_at = datetime.utcnow()
        await session.commit()

        cfg = job.config or {}
        overrides = None
        if isinstance(cfg.get("overrides"), dict):
            overrides = GenerationOverrides.model_validate(cfg.get("overrides"))

        kind = cfg.get("kind") if isinstance(cfg.get("kind"), str) else None
        payload = cfg.get("payload") if isinstance(cfg.get("payload"), dict) else None
        num_variants = int(cfg.get("num_variants") or 1)
        sd_overrides = SDProviderOverrides.from_config(cfg)

        try:
            with sd_provider_context(
                sd_overrides.provider,
                comfy_api_key=sd_overrides.comfy_api_key,
                comfy_url=sd_overrides.comfy_url,
                poe_api_key=sd_overrides.poe_api_key,
                poe_url=sd_overrides.poe_url,
                poe_model=sd_overrides.poe_model,
            ):
                if job.task_type == GenerationTaskType.CHARACTER_SHEET:
                    kinds = None
                    if isinstance(payload, dict):
                        raw_kinds = payload.get("kinds")
                        if isinstance(raw_kinds, (list, tuple)):
                            kinds = [str(k).strip() for k in raw_kinds if str(k).strip()]
                    service = CharacterService(session)
                    await service.generate_preset_sheet(
                        preset_id=job.entity_id,
                        user_id=str(job.user_id or ""),
                        project_id=job.project_id,
                        style_profile_id=job.style_profile_id,
                        overrides=overrides,
                        variants=num_variants,
                        kinds=kinds or None,
                        job_id=job.id,
                    )
                    preset = await session.get(CharacterPreset, job.entity_id)
                    if preset is not None:
                        job.results = {
                            "reference_images": preset.reference_images,
                            "preview_image_url": preset.preview_image_url,
                            "preview_thumbnail_url": preset.preview_thumbnail_url,
                        }

                elif job.task_type == GenerationTaskType.CHARACTER_RENDER:
                    service = CharacterService(session)
                    render_req = CharacterRenderRequest.model_validate(payload or {})
                    await service.generate_preset_representation(
                        preset_id=job.entity_id,
                        payload=render_req,
                        user_id=str(job.user_id or ""),
                        project_id=job.project_id,
                        style_profile_id=job.style_profile_id,
                        job_id=job.id,
                    )
                    preset = await session.get(CharacterPreset, job.entity_id)
                    if preset is not None:
                        job.results = {
                            "reference_images": preset.reference_images,
                            "preview_image_url": preset.preview_image_url,
                            "preview_thumbnail_url": preset.preview_thumbnail_url,
                        }

                elif job.task_type == GenerationTaskType.CHARACTER_REFERENCE:
                    if not kind:
                        raise RuntimeError("character_reference requires config.kind")
                    service = CharacterService(session)
                    await service.regenerate_preset_reference(
                        preset_id=job.entity_id,
                        kind=kind,
                        user_id=str(job.user_id or ""),
                        project_id=job.project_id,
                        style_profile_id=job.style_profile_id,
                        overrides=overrides,
                        job_id=job.id,
                    )
                    preset = await session.get(CharacterPreset, job.entity_id)
                    if preset is not None:
                        job.results = {
                            "reference_images": preset.reference_images,
                            "preview_image_url": preset.preview_image_url,
                            "preview_thumbnail_url": preset.preview_thumbnail_url,
                        }

                elif job.task_type == GenerationTaskType.CHARACTER_SKETCH:
                    service = CharacterService(session)
                    await service.generate_preset_sketch(
                        preset_id=job.entity_id,
                        user_id=str(job.user_id or ""),
                        overrides=overrides,
                    )
                    preset = await session.get(CharacterPreset, job.entity_id)
                    if preset is not None:
                        job.results = {
                            "reference_images": preset.reference_images,
                            "preview_image_url": preset.preview_image_url,
                            "preview_thumbnail_url": preset.preview_thumbnail_url,
                        }

                elif job.task_type == GenerationTaskType.CHARACTER_MULTIVIEW:
                    # Root cause: Need sequential multi-view character generation with view-specific prompts
                    # Solution: Use new generate_preset_multiview method for comprehensive character views
                    service = CharacterService(session)
                    await service.generate_preset_multiview(
                        preset_id=job.entity_id,
                        user_id=str(job.user_id or ""),
                        project_id=job.project_id,
                        style_profile_id=job.style_profile_id,
                        overrides=overrides,
                        job_id=job.id,
                    )
                    preset = await session.get(CharacterPreset, job.entity_id)
                    if preset is not None:
                        job.results = {
                            "reference_images": preset.reference_images,
                            "preview_image_url": preset.preview_image_url,
                            "preview_thumbnail_url": preset.preview_thumbnail_url,
                            "multiview_generated": True,
                            "total_views": len([r for r in (preset.reference_images or []) 
                                              if isinstance(r, dict) and r.get("kind", "").startswith("multiview_")]),
                        }

                elif job.task_type in {GenerationTaskType.LOCATION_SHEET, GenerationTaskType.LOCATION_SKETCH}:
                    service = WorldService(session)
                    if job.task_type == GenerationTaskType.LOCATION_SHEET:
                        await service.generate_location_sheet(
                            location_id=job.entity_id,
                            overrides=overrides,
                            style_profile_id=job.style_profile_id,
                            job_id=job.id,
                        )
                    else:
                        await service.generate_location_sketch(
                            location_id=job.entity_id,
                            overrides=overrides,
                            style_profile_id=job.style_profile_id,
                            job_id=job.id,
                        )

                    location = await session.get(Location, job.entity_id)
                    if location is not None:
                        job.results = {
                            "reference_images": location.reference_images,
                            "preview_image_url": location.preview_image_url,
                            "preview_thumbnail_url": location.preview_thumbnail_url,
                        }

                elif job.task_type == GenerationTaskType.ARTIFACT_SKETCH:
                    service = WorldService(session)
                    await service.generate_artifact_sketch(
                        artifact_id=job.entity_id,
                        overrides=overrides,
                        style_profile_id=job.style_profile_id,
                        job_id=job.id,
                    )
                    artifact = await session.get(Artifact, job.entity_id)
                    if artifact is not None:
                        job.results = {
                            "preview_image_url": artifact.preview_image_url,
                            "preview_thumbnail_url": artifact.preview_thumbnail_url,
                        }

                else:
                    raise RuntimeError(f"Unsupported asset task_type: {job.task_type}")

            job.status = GenerationStatus.DONE
            job.stage = "done"
            job.progress = 100
            job.finished_at = datetime.utcnow()
            await session.commit()

        except Exception as exc:
            job.status = GenerationStatus.FAILED
            job.stage = "failed"
            job.error = str(exc)
            job.finished_at = datetime.utcnow()
            await session.commit()
            raise



def _compose_reference_collage(reference_images: list[bytes], tile: int = 256) -> bytes:
    if not reference_images:
        raise ValueError("No reference images provided")
    cols = min(3, len(reference_images))
    rows = (len(reference_images) + cols - 1) // cols
    canvas = Image.new("RGB", (cols * tile, rows * tile), color=(0, 0, 0))
    for idx, data in enumerate(reference_images):
        try:
            image = Image.open(BytesIO(data)).convert("RGB")
        except Exception:
            continue
        image.thumbnail((tile, tile))
        cell = Image.new("RGB", (tile, tile), color=(0, 0, 0))
        cell.paste(image, ((tile - image.width) // 2, (tile - image.height) // 2))
        x = (idx % cols) * tile
        y = (idx // cols) * tile
        canvas.paste(cell, (x, y))
    buffer = BytesIO()
    canvas.save(buffer, format="PNG")
    return buffer.getvalue()


def _build_controlnet_unit(
    image_b64: str,
    module: str,
    model: str,
    weight: float,
    *,
    guidance_start: float = 0.0,
    guidance_end: float = 1.0,
    control_mode: int = 0,
    pixel_perfect: bool = True,
    processor_res: int | None = None,
    threshold_a: float | None = None,
    threshold_b: float | None = None,
) -> dict:
    # Note: resize_mode removed for SD Forge compatibility
    unit = {
        "image": image_b64,  # Forge uses "image" instead of "input_image"
        "module": module,
        "model": model,
        "weight": weight,
        "guidance_start": guidance_start,
        "guidance_end": guidance_end,
        "control_mode": control_mode,
        "pixel_perfect": pixel_perfect,
    }
    if processor_res is not None:
        unit["processor_res"] = processor_res
    if threshold_a is not None:
        unit["threshold_a"] = threshold_a
    if threshold_b is not None:
        unit["threshold_b"] = threshold_b
    return unit


def _load_scene_cast(
    session: SyncSessionLocal,
    scene_id: str,
    cast_ids: list[str] | None,
) -> list[SceneNodeCharacter]:
    query = (
        select(SceneNodeCharacter)
        .options(
            selectinload(SceneNodeCharacter.character_preset),
            selectinload(SceneNodeCharacter.material_set),
        )
        .where(SceneNodeCharacter.scene_id == scene_id)
    )
    if cast_ids is None:
        query = query.where(SceneNodeCharacter.in_frame.is_(True))
    elif cast_ids:
        query = query.where(
            or_(
                SceneNodeCharacter.id.in_(cast_ids),
                SceneNodeCharacter.character_preset_id.in_(cast_ids),
            )
        )
    else:
        return []
    result = session.execute(query)
    return list(result.scalars().all())


def _run_controlnet_pipeline(
    *,
    session: SyncSessionLocal,
    sd_layer,
    settings,
    job: GenerationJob,
    cfg: dict,
    pipeline: dict,
) -> list[bytes]:
    num_variants = cfg.get("num_variants", 4)
    width = cfg.get("width", 640)
    height = cfg.get("height", 480)
    cfg_scale = cfg.get("cfg_scale")
    steps = cfg.get("steps")
    seed = cfg.get("seed")
    sampler = cfg.get("sampler")
    scheduler = cfg.get("scheduler")
    model_id = cfg.get("model_id") or cfg.get("model_checkpoint")
    vae_id = cfg.get("vae_id")
    loras = cfg.get("loras")

    framing = pipeline.get("framing")
    pose_cfg = pipeline.get("pose") if isinstance(pipeline.get("pose"), dict) else {}
    identity_cfg = pipeline.get("identity") if isinstance(pipeline.get("identity"), dict) else {}

    cast_ids_raw = pipeline.get("cast_ids")
    cast_ids = [str(value) for value in cast_ids_raw] if isinstance(cast_ids_raw, list) else None
    cast = _load_scene_cast(session, job.scene_id, cast_ids)
    library_cast = _load_library_cast(cast_ids, cast, settings)

    assets_root = settings.assets_root_path
    reference_images: list[bytes] = []
    positions: list[str | None] = []
    lib_prompt_parts: list[str] = []
    lib_negative_parts: list[str] = []
    for link in cast:
        positions.append(link.position if link else None)
        preset = link.character_preset
        material = link.material_set
        if material and material.reference_images:
            for url in _extract_reference_urls(material.reference_images):
                data = _load_asset_bytes(url, assets_root)
                if data:
                    reference_images.append(data)
                    break
            continue
        if not preset:
            continue
        for url in _pick_reference_urls(preset):
            data = _load_asset_bytes(url, assets_root)
            if data:
                reference_images.append(data)
                break

    for lib_char in library_cast:
        positions.append(None)
        prompt_parts, negative_parts = _build_library_prompt_parts(lib_char)
        if prompt_parts:
            lib_prompt_parts.extend(prompt_parts)
        if negative_parts:
            lib_negative_parts.extend(negative_parts)
        for data in _pick_library_reference_images(lib_char):
            if data:
                reference_images.append(data)

    prompt = job.prompt
    negative_prompt = job.negative_prompt
    if lib_prompt_parts:
        prompt = ", ".join([p for p in [prompt, ", ".join(lib_prompt_parts)] if p])
    if lib_negative_parts:
        negative_prompt = ", ".join([p for p in [negative_prompt, ", ".join(lib_negative_parts)] if p])

    if not sd_layer.supports("alwayson_scripts") or not sd_layer.supports("controlnet_detect"):
        logger.warning(
            "ControlNet pipeline is not supported by the active SD provider; falling back to standard generation."
        )
        return sd_layer.generate_simple(
            prompt=prompt,
            negative_prompt=negative_prompt,
            num_images=num_variants,
            width=width,
            height=height,
            cfg_scale=cfg_scale,
            steps=steps,
            seed=seed,
            sampler=sampler,
            scheduler=scheduler,
            model_id=model_id,
            vae_id=vae_id,
            loras=loras,
        )

    scene = session.get(SceneNode, job.scene_id)
    location_reference: list[bytes] = []
    if scene and scene.location_material_set_id:
        material = session.get(MaterialSet, scene.location_material_set_id)
        if material and material.reference_images:
            for url in _extract_reference_urls(material.reference_images):
                data = _load_asset_bytes(url, assets_root)
                if data:
                    location_reference.append(data)
                    break

    roop_scripts = _build_roop_scripts(cast, settings, assets_root)

    pose_image_url = pipeline.get("pose_image_url") or ""
    pose_image = _load_asset_bytes(pose_image_url, assets_root) if pose_image_url else None
    pose_unit = None
    if not pose_image and reference_images:
        module = (pose_cfg.get("module") or settings.controlnet_openpose_module or "").strip()
        if not module:
            module = ""
        processor_res = int(pose_cfg.get("processor_res") or settings.controlnet_processor_res)
        threshold_a = float(pose_cfg.get("threshold_a") or settings.controlnet_threshold_a)
        threshold_b = float(pose_cfg.get("threshold_b") or settings.controlnet_threshold_b)
        if module:
            pose_maps = sd_layer.controlnet_detect(
                module=module,
                images=reference_images[:3],
                processor_res=processor_res,
                threshold_a=threshold_a,
                threshold_b=threshold_b,
            )
            if pose_maps:
                pose_image = _compose_pose_map(pose_maps, width, height, positions, framing)

    pose_module = (pose_cfg.get("module") or settings.controlnet_openpose_module or "").strip()
    pose_model_base = (pose_cfg.get("model") or settings.controlnet_openpose_model or "").strip()
    pose_model = _find_controlnet_model(pose_model_base) if pose_model_base else None
    if pose_image and pose_module and pose_model:
        pose_unit = _build_controlnet_unit(
            image_b64=_encode_image_bytes(pose_image),
            module=pose_module,
            model=pose_model,
            weight=float(pose_cfg.get("weight") or settings.controlnet_pose_weight),
            guidance_start=float(pose_cfg.get("guidance_start", 0.0)),
            guidance_end=float(pose_cfg.get("guidance_end", 0.7)),
            control_mode=int(pose_cfg.get("control_mode", 0)),
            processor_res=int(pose_cfg.get("processor_res") or settings.controlnet_processor_res),
            threshold_a=float(pose_cfg.get("threshold_a") or settings.controlnet_threshold_a),
            threshold_b=float(pose_cfg.get("threshold_b") or settings.controlnet_threshold_b),
        )

    identity_unit = None
    identity_units: list[dict] = []
    identity_module = (identity_cfg.get("module") or settings.controlnet_reference_module or "").strip()
    # reference_only, reference_adain, reference_adain+attn don't need a model
    is_reference_module = identity_module.startswith("reference_")
    identity_model_base = (identity_cfg.get("model") or settings.controlnet_reference_model or "").strip()
    identity_model = None
    if not is_reference_module and identity_model_base:
        identity_model = _find_controlnet_model(identity_model_base)
    
    identity_mode = (pipeline.get("identity_mode") or "").strip().lower()
    if identity_mode == "ip_adapter" and reference_images:
        face_ref = reference_images[0] if reference_images else None
        body_ref = reference_images[1] if len(reference_images) > 1 else face_ref
        face_model = _find_controlnet_model("ip-adapter-face")
        body_model = _find_controlnet_model("ip-adapter")
        if face_ref and face_model:
            identity_units.append(
                _build_controlnet_unit(
                    image_b64=_encode_image_bytes(face_ref),
                    module="ip-adapter-face",
                    model=face_model,
                    weight=float(identity_cfg.get("face_weight") or settings.character_quality_face_weight),
                    guidance_start=float(identity_cfg.get("guidance_start", 0.0)),
                    guidance_end=float(identity_cfg.get("guidance_end", 1.0)),
                    control_mode=int(identity_cfg.get("control_mode", 0)),
                )
            )
        if body_ref and body_model:
            identity_units.append(
                _build_controlnet_unit(
                    image_b64=_encode_image_bytes(body_ref),
                    module="ip-adapter",
                    model=body_model,
                    weight=float(identity_cfg.get("body_weight") or settings.character_quality_body_weight),
                    guidance_start=float(identity_cfg.get("guidance_start", 0.0)),
                    guidance_end=float(identity_cfg.get("guidance_end", 1.0)),
                    control_mode=int(identity_cfg.get("control_mode", 0)),
                )
            )

    if not identity_units:
        # For reference modules, we don't need a model; for others, we need both module and model
        can_use_identity = reference_images and identity_module and (is_reference_module or identity_model)
        if can_use_identity:
            try:
                identity_image = _compose_reference_collage(reference_images[:3])
            except Exception:
                identity_image = None
            if identity_image:
                identity_unit = _build_controlnet_unit(
                    image_b64=_encode_image_bytes(identity_image),
                    module=identity_module,
                    model=identity_model or "None",  # Use "None" for reference modules
                    weight=float(identity_cfg.get("weight") or settings.controlnet_reference_weight),
                    guidance_start=float(identity_cfg.get("guidance_start", 0.2)),
                    guidance_end=float(identity_cfg.get("guidance_end", 1.0)),
                    control_mode=int(identity_cfg.get("control_mode", 0)),
                )
                identity_units = [identity_unit]

    if not pose_unit and not identity_units:
        return sd_layer.generate_simple(
            prompt=prompt,
            negative_prompt=negative_prompt,
            num_images=num_variants,
            width=width,
            height=height,
            cfg_scale=cfg_scale,
            steps=steps,
            seed=seed,
            alwayson_scripts=roop_scripts,
            sampler=sampler,
            scheduler=scheduler,
            model_id=model_id,
            vae_id=vae_id,
            loras=loras,
        )

    layout_units = [pose_unit] if pose_unit else []
    detail_units = [unit for unit in ([pose_unit] + identity_units) if unit]

    layout_steps = pipeline.get("layout_steps")
    if not isinstance(layout_steps, int):
        layout_steps = max(10, int((steps or 20) * 0.6))
    detail_steps = pipeline.get("detail_steps")
    if not isinstance(detail_steps, int):
        detail_steps = steps or 20

    denoise = pipeline.get("denoising_strength")
    if not isinstance(denoise, (int, float)):
        denoise = 0.45

    layout_init_images = location_reference[:1] if location_reference else None
    location_denoise = pipeline.get("location_denoise")
    if not isinstance(location_denoise, (int, float)):
        location_denoise = 0.35

    results: list[bytes] = []
    for idx in range(num_variants):
        seed_value = seed + idx if isinstance(seed, int) else None
        layout_scripts = {"controlnet": {"args": layout_units}} if layout_units else None
        detail_scripts = {"controlnet": {"args": detail_units}} if detail_units else None
        detail_scripts = _merge_scripts(detail_scripts, roop_scripts)

        base = sd_layer.generate_simple(
            prompt=prompt,
            negative_prompt=negative_prompt,
            num_images=1,
            width=width,
            height=height,
            cfg_scale=cfg_scale,
            steps=layout_steps,
            seed=seed_value,
            alwayson_scripts=layout_scripts,
            init_images=layout_init_images,
            denoising_strength=location_denoise if layout_init_images else None,
            sampler=sampler,
            scheduler=scheduler,
            model_id=model_id,
            vae_id=vae_id,
            loras=loras,
        )[0]

        if detail_scripts:
            refined = sd_layer.generate_simple(
                prompt=prompt,
                negative_prompt=negative_prompt,
                num_images=1,
                width=width,
                height=height,
                cfg_scale=cfg_scale,
                steps=detail_steps,
                seed=seed_value,
                init_images=[base],
                denoising_strength=denoise,
                alwayson_scripts=detail_scripts,
                sampler=sampler,
                scheduler=scheduler,
                model_id=model_id,
                vae_id=vae_id,
                loras=loras,
            )[0]
            results.append(refined)
        else:
            results.append(base)

    return results


@celery_app.task(
    name="app.workers.generation.generate_images",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def generate_images(
    self,
    scene_id: str,
    prompt: str,
    negative_prompt: str | None = None,
    style: str | None = None,
    num_variants: int = 4,
    width: int = 640,
    height: int = 480,
    cfg_scale: float | None = None,
    steps: int | None = None,
    seed: int | None = None,
    sampler: str | None = None,
    scheduler: str | None = None,
    model_id: str | None = None,
    vae_id: str | None = None,
    loras: list[dict] | None = None,
    workflow_set: str | None = None,
    workflow_task: str | None = None,
    sd_provider: str | None = None,
    comfy_api_key: str | None = None,
    comfy_api_url: str | None = None,
) -> dict:
    """Generate image variants for a scene via SD Request Layer."""
    settings = get_settings()
    storage = LocalImageStorage(settings.generated_assets_path)

    overrides = SDProviderOverrides(
        provider=sd_provider,
        comfy_api_key=comfy_api_key,
        comfy_url=comfy_api_url,
    ).normalized()

    # Use SD Request Layer for automatic translation and generation
    with sd_provider_context(
        overrides.provider,
        comfy_api_key=overrides.comfy_api_key,
        comfy_url=overrides.comfy_url,
        poe_api_key=overrides.poe_api_key,
        poe_url=overrides.poe_url,
        poe_model=overrides.poe_model,
    ):
        sd_layer = get_sd_layer()
        images = sd_layer.generate_simple(
            prompt=prompt,
            negative_prompt=negative_prompt,
            num_images=num_variants,
            width=width,
            height=height,
            style=style,
            cfg_scale=cfg_scale,
            steps=steps,
            seed=seed,
            sampler=sampler,
            scheduler=scheduler,
            model_id=model_id,
            vae_id=vae_id,
            loras=loras,
            workflow_set=workflow_set,
            workflow_task=workflow_task,
        )
    
    paths = storage.save_images(scene_id, images)
    rel_paths = [Path(p).relative_to(settings.assets_root_path).as_posix() for p in paths]
    public_urls = [f"/api/assets/{rp}" for rp in rel_paths]

    logger.info(
        "Generated images for scene",
        extra={"scene_id": scene_id, "variant_count": len(paths)},
    )
    return {
        "scene_id": scene_id,
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "cfg_scale": cfg_scale,
        "steps": steps,
        "paths": paths,
        "images": rel_paths,
        "image_urls": public_urls,
        "num_variants": num_variants,
        "width": width,
        "height": height,
        "seed": seed,
        "sampler": sampler,
        "scheduler": scheduler,
        "model_id": model_id,
        "vae_id": vae_id,
        "loras": loras,
    }


@celery_app.task(
    name="app.workers.generation.pipeline_check",
    bind=True,
)
def pipeline_check(
    self,
    sd_provider: str | None = None,
    comfy_api_key: str | None = None,
    comfy_api_url: str | None = None,
) -> dict:
    """Run a diagnostic generation to validate SD -> storage pipeline."""
    settings = get_settings()
    storage = LocalImageStorage(settings.generated_assets_path)

    check_id = uuid4().hex
    diagnostics: dict = {"status": "ok", "checks": {}}

    start = time.perf_counter()
    overrides = SDProviderOverrides(
        provider=sd_provider,
        comfy_api_key=comfy_api_key,
        comfy_url=comfy_api_url,
    ).normalized()

    try:
        with sd_provider_context(
            overrides.provider,
            comfy_api_key=overrides.comfy_api_key,
            comfy_url=overrides.comfy_url,
            poe_api_key=overrides.poe_api_key,
            poe_url=overrides.poe_url,
            poe_model=overrides.poe_model,
        ):
            sd_layer = get_sd_layer()
            from app.services.pipeline_profiles import get_pipeline_resolver, PipelineSeedContext
            resolver = get_pipeline_resolver()
            resolved = resolver.resolve(
                kind="scene",
                overrides={"width": 320, "height": 240},
                seed_context=PipelineSeedContext(kind="scene"),
            )
            images = sd_layer.generate_simple(
                prompt="pipeline check",
                num_images=1,
                width=resolved.width,
                height=resolved.height,
                style="diagnostic",
                cfg_scale=resolved.cfg_scale,
                steps=resolved.steps,
                seed=resolved.seed,
                sampler=resolved.sampler,
                scheduler=resolved.scheduler,
                model_id=resolved.model_id,
                vae_id=resolved.vae_id,
                loras=[lora.model_dump() for lora in resolved.loras],
            )
        diagnostics["checks"]["sd"] = {
            "status": "ok",
            "latency_ms": int((time.perf_counter() - start) * 1000),
            "images": len(images),
        }
    except Exception as exc:
        logger.exception("SD pipeline check failed")
        raise RuntimeError(f"sd_error: {exc}") from exc

    try:
        paths = storage.save_images(f"pipeline-check/{check_id}", images)
        diagnostics["checks"]["storage"] = {"status": "ok", "paths": paths}
        diagnostics["artifacts"] = paths
    except Exception as exc:
        logger.exception("Storage pipeline check failed")
        raise RuntimeError(f"storage_error: {exc}") from exc

    return diagnostics


@celery_app.task(
    name="app.workers.generation.process_generation_job",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
    ignore_result=True,
)
def process_generation_job(self, job_id: str) -> dict:
    """Process a GenerationJob.

    - For scene jobs (`task_type=scene_generate`), uses the existing SD request layer + ImageVariant.
    - For asset jobs (characters/locations/etc), dispatches to async services and writes results into
      the job record and the target entity.
    """
    settings = get_settings()
    storage = LocalImageStorage(settings.generated_assets_path)

    # Fast dispatch: asset jobs are processed with async services.
    with SyncSessionLocal() as session:
        job: GenerationJob | None = session.get(GenerationJob, job_id)
        if job is None:
            raise RuntimeError(f"Job {job_id} not found")
        if job.task_type != GenerationTaskType.SCENE_GENERATE:
            # Close sync session before running async pipeline (important for SQLite and to avoid
            # holding extra connections).
            session.close()
            _run_async_job(_process_asset_generation_job_v2(job_id))
            return {"job_id": job_id}

        job.status = GenerationStatus.RUNNING
        job.stage = "running"
        job.progress = 0
        job.started_at = datetime.utcnow()
        session.commit()

        cfg = job.config or {}
        num_variants = cfg.get("num_variants", 4)
        width = cfg.get("width", 640)
        height = cfg.get("height", 480)
        cfg_scale = cfg.get("cfg_scale")
        steps = cfg.get("steps")
        seed = cfg.get("seed")
        sampler = cfg.get("sampler")
        scheduler = cfg.get("scheduler")
        model_id = cfg.get("model_id") or cfg.get("model_checkpoint")
        vae_id = cfg.get("vae_id")
        loras = cfg.get("loras")
        pipeline = cfg.get("pipeline") if isinstance(cfg.get("pipeline"), dict) else {}
        assets_root = settings.assets_root_path
        slide_id = cfg.get("slide_id") if isinstance(cfg, dict) else None
        auto_approve_raw = cfg.get("auto_approve") if isinstance(cfg, dict) else None
        if isinstance(auto_approve_raw, bool):
            auto_approve = auto_approve_raw
        elif isinstance(auto_approve_raw, str):
            auto_approve = auto_approve_raw.strip().lower() in {"1", "true", "yes", "on"}
        else:
            auto_approve = False
        scene = session.get(SceneNode, job.scene_id)
        slide_context = _find_slide_context(scene, slide_id) if scene and slide_id else None
        cast_ids_raw = pipeline.get("cast_ids") if isinstance(pipeline, dict) else None
        pipeline_cast_ids = [str(value) for value in cast_ids_raw] if isinstance(cast_ids_raw, list) else None
        slot_ids_raw = pipeline.get("character_slot_ids") if isinstance(pipeline, dict) else None
        pipeline_slot_ids = [str(value) for value in slot_ids_raw if value is not None] if isinstance(slot_ids_raw, list) else []
        slide_cast_ids = None
        if isinstance(slide_context, dict):
            raw_cast = slide_context.get("cast_ids")
            if isinstance(raw_cast, list):
                slide_cast_ids = [str(value) for value in raw_cast if value is not None]
        cast_ids = slide_cast_ids or pipeline_cast_ids
        all_reference_ids: list[str] = []
        seen_reference_ids: set[str] = set()
        for value in [*(cast_ids or []), *pipeline_slot_ids]:
            if not value or value in seen_reference_ids:
                continue
            seen_reference_ids.add(value)
            all_reference_ids.append(value)
        cast_lookup_ids = all_reference_ids if all_reference_ids else cast_ids
        cast = _load_scene_cast(session, job.scene_id, cast_lookup_ids)
        library_cast = _load_library_cast(all_reference_ids or cast_ids, cast, settings)
        roop_scripts = _build_roop_scripts(cast, settings, assets_root)
        base_prompt = job.prompt
        base_negative_prompt = job.negative_prompt

        # Gather reference images for Qwen scene workflow (location + up to 2 characters).
        location_ref: bytes | None = None
        location_obj: Location | None = None
        location_ref_mode = str(pipeline.get("location_ref_mode") or "").strip().lower()
        location_ref_url = str(pipeline.get("location_ref_url") or "").strip()
        location_ref_disabled = location_ref_mode == "none"
        slide_location_id = None
        if isinstance(slide_context, dict):
            raw_location = slide_context.get("location_id")
            if isinstance(raw_location, str) and raw_location:
                slide_location_id = raw_location
        location_id = slide_location_id or (scene.location_id if scene else None)
        if location_id:
            location_obj = session.get(Location, location_id)

        if location_ref_mode == "selected" and location_ref_url:
            location_ref = _load_asset_bytes(location_ref_url, assets_root)
            if location_ref is None:
                logger.warning("Failed to load selected location reference for scene generation: %s", location_ref_url)

        if not location_ref and not location_ref_disabled and scene and scene.location_material_set_id:
            material = session.get(MaterialSet, scene.location_material_set_id)
            if material and material.reference_images:
                for url in _extract_reference_urls(material.reference_images):
                    data = _load_asset_bytes(url, assets_root)
                    if data:
                        location_ref = data
                        break

        if not location_ref and not location_ref_disabled and location_obj:
            for url in _pick_location_reference_urls(location_obj):
                data = _load_asset_bytes(url, assets_root)
                if data:
                    location_ref = data
                    break

        scene_cast_by_id: dict[str, SceneNodeCharacter] = {}
        for link in cast:
            if link.id:
                scene_cast_by_id[str(link.id)] = link
            if link.character_preset_id:
                scene_cast_by_id[str(link.character_preset_id)] = link

        lib_cast_by_id: dict[str, object] = {}
        for lib_char in library_cast:
            lib_id = getattr(lib_char, "id", None)
            if lib_id:
                lib_cast_by_id[str(lib_id)] = lib_char

        def _pick_scene_cast_ref(link: SceneNodeCharacter | None) -> bytes | None:
            if not link:
                return None
            material = link.material_set
            if material and material.reference_images:
                for url in _extract_reference_urls(material.reference_images):
                    data = _load_asset_bytes(url, assets_root)
                    if data:
                        return data
            preset = link.character_preset
            if preset:
                for url in _pick_reference_urls(preset):
                    data = _load_asset_bytes(url, assets_root)
                    if data:
                        return data
            return None

        ordered_cast_ids = cast_ids or []
        ordered_cast_ids_unique: list[str] = []
        ordered_cast_ids_seen: set[str] = set()
        for value in ordered_cast_ids:
            if value in ordered_cast_ids_seen:
                continue
            ordered_cast_ids_seen.add(value)
            ordered_cast_ids_unique.append(value)
        slot_cast_ids: list[str] = []
        slot_cast_seen: set[str] = set()
        for value in pipeline_slot_ids:
            if not value or value in slot_cast_seen:
                continue
            slot_cast_seen.add(value)
            slot_cast_ids.append(value)
        explicit_slot_ids = slot_cast_ids or ordered_cast_ids_unique
        selected_cast_ids_for_constraints = list(explicit_slot_ids or ordered_cast_ids_unique)

        character_ref_slots: list[tuple[str, str, bytes]] = []

        def _append_character_ref(cid: str, display_name: str, data: bytes | None) -> None:
            if data is None:
                return
            if any(existing_id == cid for existing_id, _, _ in character_ref_slots):
                return
            character_ref_slots.append((cid, display_name, data))

        def _resolve_character_label(cid: str) -> str:
            link = scene_cast_by_id.get(cid)
            if link and link.character_preset and link.character_preset.name:
                return str(link.character_preset.name)
            lib_char = lib_cast_by_id.get(cid)
            if lib_char is not None:
                name = getattr(lib_char, "name", None)
                if isinstance(name, str) and name.strip():
                    return name.strip()
            return cid

        missing_selected_refs: list[str] = []
        required_cast_ids = explicit_slot_ids[:2]

        # Explicit cast selection from slide/pipeline is treated as strict source mapping.
        # We do not silently replace missing selections with other characters.
        if explicit_slot_ids:
            for cid in explicit_slot_ids:
                link = scene_cast_by_id.get(cid)
                display_name = _resolve_character_label(cid)
                data = _pick_scene_cast_ref(link) if link else None
                if data is None:
                    lib_char = lib_cast_by_id.get(cid)
                    if lib_char:
                        for ref in _pick_library_reference_images(lib_char):
                            data = ref
                            break
                if data is None and cid in required_cast_ids:
                    missing_selected_refs.append(cid)
                _append_character_ref(cid, display_name, data)
        else:
            for link in cast:
                cid = str(link.character_preset_id or link.id or "")
                display_name = (
                    str(link.character_preset.name)
                    if link.character_preset and link.character_preset.name
                    else cid
                )
                _append_character_ref(cid, display_name, _pick_scene_cast_ref(link))
                if len(character_ref_slots) >= 2:
                    break
            if len(character_ref_slots) < 2:
                for lib_char in library_cast:
                    cid = str(getattr(lib_char, "id", "") or "")
                    display_name = str(getattr(lib_char, "name", "") or cid)
                    data = None
                    for ref in _pick_library_reference_images(lib_char):
                        data = ref
                        break
                    _append_character_ref(cid, display_name, data)
                    if len(character_ref_slots) >= 2:
                        break

        if missing_selected_refs:
            missing_labels = [_resolve_character_label(cid) for cid in missing_selected_refs]
            strict_missing_refs_raw = cfg.get("strict_selected_cast_references")
            strict_missing_refs = False
            if isinstance(strict_missing_refs_raw, bool):
                strict_missing_refs = strict_missing_refs_raw
            elif isinstance(strict_missing_refs_raw, str):
                strict_missing_refs = strict_missing_refs_raw.strip().lower() in {
                    "1",
                    "true",
                    "yes",
                    "on",
                }
            if strict_missing_refs:
                raise RuntimeError(
                    "Missing reference images for selected cast: "
                    + ", ".join(missing_labels)
                    + ". Add/import references and retry scene generation."
                )
            missing_ids_set = set(missing_selected_refs)
            explicit_slot_ids = [cid for cid in explicit_slot_ids if cid not in missing_ids_set]
            selected_cast_ids_for_constraints = [
                cid for cid in selected_cast_ids_for_constraints if cid not in missing_ids_set
            ]
            logger.warning(
                "Scene generation proceeding without missing selected cast refs: %s",
                ", ".join(missing_labels),
                extra={
                    "scene_id": job.scene_id,
                    "slide_id": slide_id,
                    "missing_selected_cast_ids": missing_selected_refs,
                },
            )

        if len(explicit_slot_ids) > 2:
            logger.info(
                "Scene img2img supports up to 2 character references; extra selected cast ids are ignored for image slots.",
                extra={
                    "scene_id": job.scene_id,
                    "selected_cast_ids": explicit_slot_ids,
                },
            )

        character_refs = [slot[2] for slot in character_ref_slots[:2]]
        logger.info(
            "Scene refs resolved: location=%s, char_slots=%s",
            "yes" if location_ref is not None else "no",
            [
                {"slot": idx + 2, "id": cid, "name": name}
                for idx, (cid, name, _) in enumerate(character_ref_slots[:2])
            ],
        )
        sd_overrides = SDProviderOverrides.from_config(cfg)

        try:
            with sd_provider_context(
                sd_overrides.provider,
                comfy_api_key=sd_overrides.comfy_api_key,
                comfy_url=sd_overrides.comfy_url,
                poe_api_key=sd_overrides.poe_api_key,
                poe_url=sd_overrides.poe_url,
                poe_model=sd_overrides.poe_model,
            ):
                # Use SD Request Layer for automatic translation and generation
                sd_layer = get_sd_layer()
                is_cloud = bool(getattr(sd_layer.client, "_is_cloud", False))
                use_qwen_scene = is_cloud

                if pipeline.get("mode") == "controlnet" and not is_cloud:
                    images = _run_controlnet_pipeline(
                        session=session,
                        sd_layer=sd_layer,
                        settings=settings,
                        job=job,
                        cfg=cfg,
                        pipeline=pipeline,
                    )
                elif use_qwen_scene:
                    if pipeline.get("mode") == "controlnet":
                        logger.info(
                            "Cloud scene generation ignores controlnet mode and uses Qwen scene img2img workflow.",
                            extra={"scene_id": job.scene_id, "slide_id": slide_id},
                        )
                    character_notes: list[tuple[str, str]] = []
                    for cid, fallback_name, _ in character_ref_slots[:2]:
                        link = scene_cast_by_id.get(cid)
                        if link and link.character_preset:
                            name = link.character_preset.name or fallback_name or ""
                            desc = link.character_preset.description or ""
                            character_notes.append((name, desc))
                            continue
                        lib_char = lib_cast_by_id.get(cid)
                        if lib_char:
                            name = getattr(lib_char, "name", "") or fallback_name or ""
                            desc = (
                                getattr(lib_char, "description", None)
                                or getattr(lib_char, "appearance_prompt", None)
                                or ""
                            )
                            character_notes.append((name, str(desc)))
                            continue
                        character_notes.append((fallback_name or "", ""))

                    slot_positions: list[str | None] = []
                    for cid, _, _ in character_ref_slots[:2]:
                        link = scene_cast_by_id.get(cid)
                        if link and isinstance(link.position, str):
                            slot_positions.append(link.position)
                        else:
                            slot_positions.append(None)

                    slide_framing = None
                    if isinstance(slide_context, dict):
                        framing_value = slide_context.get("framing")
                        if isinstance(framing_value, str):
                            slide_framing = framing_value
                    framing = slide_framing or pipeline.get("framing") or "full"
                    requested_cast_count = len(selected_cast_ids_for_constraints)
                    slide_visual = ""
                    if isinstance(slide_context, dict):
                        for key in ("user_prompt", "visual", "title"):
                            value = slide_context.get(key)
                            if isinstance(value, str) and value.strip():
                                slide_visual = value.strip()
                                break
                    if not slide_visual and scene:
                        slide_visual = scene.title or ""
                    action_hint = build_story_action_hint(
                        slide_context=slide_context if isinstance(slide_context, dict) else None,
                        slide_visual=slide_visual,
                        scene_synopsis=scene.synopsis if scene else "",
                    )
                    context_text = " ".join(
                        [
                            slide_visual or "",
                            scene.synopsis if scene and scene.synopsis else "",
                        ]
                    ).lower()
                    extras_policy = infer_background_extras_policy(
                        slide_context=slide_context if isinstance(slide_context, dict) else None,
                        context_text=context_text,
                        principal_count=len(character_notes),
                        requested_cast_count=requested_cast_count,
                    )
                    people_constraints = build_people_constraints(
                        principal_count=len(character_notes),
                        has_location_reference=location_ref is not None,
                        extras_policy=extras_policy,
                    )
                    people_constraints_text = " ".join(people_constraints)
                    composition_guardrails = build_composition_guardrails(
                        principal_count=len(character_notes),
                        has_location_reference=location_ref is not None,
                        slot_positions=slot_positions,
                        action_hint=action_hint,
                    )
                    composition_guardrails_text = " ".join(composition_guardrails)
                    composition_negative_prompt = build_composition_negative_prompt(
                        principal_count=len(character_notes),
                        extras_policy=extras_policy,
                    )
                    scene_denoise_raw = cfg.get("scene_denoising_strength")
                    if isinstance(scene_denoise_raw, (int, float)):
                        scene_denoise = max(0.0, min(1.0, float(scene_denoise_raw)))
                    elif location_ref is not None:
                        # Lower denoise helps keep image-1 layout intact while compositing refs.
                        scene_denoise = 0.8
                    else:
                        # Without location ref, keep some conditioning strength from character refs.
                        scene_denoise = 0.9

                    composition_prompt = None
                    composition_generated = False
                    composition_from_slide = False
                    composition_regenerated_reason = None
                    if isinstance(slide_context, dict):
                        comp = slide_context.get("composition_prompt")
                        if isinstance(comp, str) and comp.strip():
                            existing_prompt = " ".join(comp.split())
                            lower_existing = existing_prompt.lower()
                            sentence_like = len(re.split(r"[.;!?]\s+", existing_prompt))
                            preserve_hits = lower_existing.count("preserve ")
                            has_cyrillic = bool(re.search(r"[А-Яа-яЁё]", existing_prompt))
                            too_long = len(existing_prompt) > 1400
                            too_repetitive = sentence_like > 22 or preserve_hits >= 6
                            if too_long or too_repetitive or has_cyrillic:
                                composition_prompt = None
                                composition_from_slide = False
                                reasons = []
                                if too_long:
                                    reasons.append("too_long")
                                if too_repetitive:
                                    reasons.append("too_repetitive")
                                if has_cyrillic:
                                    reasons.append("has_cyrillic")
                                composition_regenerated_reason = ",".join(reasons) or "quality_guard"
                            else:
                                composition_prompt = existing_prompt
                                composition_from_slide = True
                    if composition_prompt and missing_selected_refs:
                        # Saved prompt may describe characters that have no usable refs anymore.
                        # Regenerate prompt from effective references for this run.
                        composition_prompt = None
                        composition_from_slide = False
                        composition_regenerated_reason = "missing_selected_refs"
                    if not composition_prompt:
                        composition_prompt = _build_scene_composition_prompt(
                            scene=scene,
                            slide_context=slide_context if isinstance(slide_context, dict) else None,
                            character_notes=character_notes,
                            location=location_obj,
                            framing=framing,
                            has_location_reference=location_ref is not None,
                            slot_positions=slot_positions,
                            action_hint=action_hint,
                            requested_cast_count=requested_cast_count,
                        )
                        composition_generated = True

                    if composition_prompt:
                        composition_prompt = normalize_composition_prompt(
                            prompt=composition_prompt,
                            people_constraints_text=people_constraints_text,
                            guardrails=composition_guardrails,
                            gritty=any(
                                token in context_text
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
                            ),
                            principal_count=len(character_notes),
                        )
                    if composition_generated and composition_prompt and scene and slide_id:
                        context = scene.context if isinstance(scene.context, dict) else None
                        if context:
                            sequence = context.get("sequence") if isinstance(context.get("sequence"), dict) else None
                            slides = sequence.get("slides") if sequence and isinstance(sequence.get("slides"), list) else None
                            if slides:
                                updated = False
                                new_slides = []
                                for slide in slides:
                                    if isinstance(slide, dict) and slide.get("id") == slide_id:
                                        existing_comp = slide.get("composition_prompt")
                                        if not isinstance(existing_comp, str) or not existing_comp.strip():
                                            new_slide = dict(slide)
                                            new_slide["composition_prompt"] = composition_prompt
                                            new_slides.append(new_slide)
                                            updated = True
                                        else:
                                            new_slides.append(slide)
                                    else:
                                        new_slides.append(slide)
                                if updated:
                                    new_sequence = dict(sequence) if isinstance(sequence, dict) else {}
                                    new_sequence["slides"] = new_slides
                                    new_context = dict(context)
                                    new_context["sequence"] = new_sequence
                                    scene.context = new_context
                                    session.commit()
                                    logger.info(
                                        "Saved generated composition_prompt to scene context.",
                                        extra={"scene_id": job.scene_id, "slide_id": slide_id},
                                    )
                    prompt = composition_prompt or base_prompt
                    prompt_source = (
                        "slide_context"
                        if composition_from_slide
                        else ("generated" if composition_generated else "base_prompt_fallback")
                    )
                    if not composition_prompt:
                        prompt_source = "base_prompt_fallback"
                    if not composition_prompt:
                        logger.warning(
                            "Qwen scene generation missing composition_prompt; falling back to base prompt.",
                            extra={"scene_id": job.scene_id, "slide_id": slide_id},
                        )
                    final_constraints_metadata = {
                        "mode": "qwen_scene_img2img",
                        "slide_id": slide_id,
                        "framing": framing,
                        "prompt_source": prompt_source,
                        "prompt_regenerated_reason": composition_regenerated_reason,
                        "has_location_reference": location_ref is not None,
                        "location_id": location_id,
                        "principal_count": len(character_notes),
                        "requested_cast_count": requested_cast_count,
                        "character_slots": [
                            {"slot": idx + 2, "id": cid, "name": name}
                            for idx, (cid, name, _) in enumerate(character_ref_slots[:2])
                        ],
                        "background_extras": {
                            "allowed": bool(extras_policy.allowed),
                            "min_count": int(extras_policy.min_count),
                            "max_count": int(extras_policy.max_count),
                            "note": extras_policy.note or None,
                        },
                        "missing_selected_cast_ids": missing_selected_refs or [],
                        "missing_selected_cast_labels": [
                            _resolve_character_label(cid) for cid in (missing_selected_refs or [])
                        ],
                        "slot_positions": slot_positions,
                        "story_action_hint": action_hint or None,
                        "people_constraints": people_constraints,
                        "people_constraints_text": people_constraints_text,
                        "composition_guardrails": composition_guardrails,
                        "composition_guardrails_text": composition_guardrails_text,
                        "composition_negative_prompt": composition_negative_prompt,
                        "denoising_strength": scene_denoise,
                        "final_prompt_preview": (prompt or "")[:400],
                    }
                    try:
                        _merge_job_runtime_metadata(
                            job,
                            "final_scene_constraints",
                            final_constraints_metadata,
                        )
                        session.commit()
                    except Exception as meta_exc:
                        session.rollback()
                        logger.warning(
                            "Failed to persist final scene constraints metadata: %s",
                            meta_exc,
                            extra={"job_id": job.id, "scene_id": job.scene_id, "slide_id": slide_id},
                        )
                    init_images = [location_ref, *character_refs]
                    images = sd_layer.generate_simple(
                        prompt=prompt,
                        negative_prompt=composition_negative_prompt,
                        num_images=num_variants,
                        width=width,
                        height=height,
                        cfg_scale=cfg_scale,
                        steps=steps,
                        seed=seed,
                        sampler=sampler,
                        scheduler=scheduler,
                        model_id=model_id,
                        vae_id=vae_id,
                        loras=loras,
                        init_images=init_images,
                        denoising_strength=scene_denoise,
                        workflow_set="cloud_api",
                        workflow_task="scene",
                    )
                else:
                    lib_prompt_parts: list[str] = []
                    lib_negative_parts: list[str] = []
                    for lib_char in library_cast:
                        prompt_parts, negative_parts = _build_library_prompt_parts(lib_char)
                        if prompt_parts:
                            lib_prompt_parts.extend(prompt_parts)
                        if negative_parts:
                            lib_negative_parts.extend(negative_parts)
                    prompt = base_prompt
                    negative_prompt = base_negative_prompt
                    if lib_prompt_parts:
                        prompt = ", ".join([p for p in [prompt, ", ".join(lib_prompt_parts)] if p])
                    if lib_negative_parts:
                        negative_prompt = ", ".join([p for p in [negative_prompt, ", ".join(lib_negative_parts)] if p])
                    images = sd_layer.generate_simple(
                        prompt=prompt,
                        negative_prompt=negative_prompt,
                        num_images=num_variants,
                        width=width,
                        height=height,
                        cfg_scale=cfg_scale,
                        steps=steps,
                        seed=seed,
                        alwayson_scripts=roop_scripts,
                        sampler=sampler,
                        scheduler=scheduler,
                        model_id=model_id,
                        vae_id=vae_id,
                        loras=loras,
                    )
        except Exception as exc:
            job.status = GenerationStatus.FAILED
            job.error = str(exc)
            job.finished_at = datetime.utcnow()
            session.commit()
            track_event(
                "generation_job_failed",
                metadata={"job_id": job.id, "scene_id": job.scene_id, "error": str(exc)},
            )
            raise

        # Scene generation completed; move to persistence stage.
        job.progress = max(int(job.progress or 0), 75)
        job.stage = "saving"
        session.commit()

        paths = storage.save_images_for_scene(job.project_id, job.scene_id, images)
        rel_paths = [Path(p).relative_to(settings.assets_root_path).as_posix() for p in paths]
        urls = [f"/api/assets/{rp}" for rp in rel_paths]

        # clear previous variants for this job
        for variant in list(job.variants):
            session.delete(variant)
        session.commit()

        # For auto-approved runs, keep a single approved image per scene.
        if auto_approve:
            session.execute(
                ImageVariant.__table__.update()
                .where(ImageVariant.scene_id == job.scene_id)
                .values(is_approved=False)
            )
            session.commit()

        total_variants = max(1, len(paths))
        approved_variant_id: str | None = None
        approved_variant_url: str | None = None
        created_variants_payload: list[dict] = []
        for idx, (path, rel, url) in enumerate(zip(paths, rel_paths, urls), start=1):
            is_variant_approved = bool(auto_approve and idx == 1)
            variant = ImageVariant(
                job_id=job.id,
                project_id=job.project_id,
                scene_id=job.scene_id,
                url=url,
                image_metadata={
                    "path": path,
                    "rel_path": rel,
                    "cfg_scale": cfg_scale,
                    "steps": steps,
                    "seed": seed,
                    "sampler": sampler,
                    "scheduler": scheduler,
                    "model_id": model_id,
                    "vae_id": vae_id,
                    "loras": loras,
                    "pipeline": pipeline if pipeline else None,
                },
                is_approved=is_variant_approved,
            )
            session.add(variant)
            # Best-effort progress: 75% after SD, last 25% while persisting variants.
            job.progress = 75 + int(idx / total_variants * 25)
            job.stage = f"variant_{idx}/{total_variants}"
            session.commit()
            created_variants_payload.append(
                {
                    "id": variant.id,
                    "url": variant.url,
                    "thumbnail_url": variant.thumbnail_url,
                }
            )
            if is_variant_approved and approved_variant_id is None:
                approved_variant_id = variant.id
                approved_variant_url = variant.url

        # If this job targets a specific slide, persist resolved image pointers into sequence context.
        if slide_id and approved_variant_id and approved_variant_url and scene:
            context = scene.context if isinstance(scene.context, dict) else None
            if context:
                sequence = context.get("sequence") if isinstance(context.get("sequence"), dict) else None
                slides = sequence.get("slides") if sequence and isinstance(sequence.get("slides"), list) else None
                if slides:
                    updated = False
                    new_slides = []
                    for slide in slides:
                        if isinstance(slide, dict) and str(slide.get("id")) == str(slide_id):
                            new_slide = dict(slide)
                            new_slide["image_url"] = approved_variant_url
                            new_slide["image_variant_id"] = approved_variant_id
                            new_slide["variants"] = created_variants_payload
                            new_slides.append(new_slide)
                            updated = True
                        else:
                            new_slides.append(slide)
                    if updated:
                        new_sequence = dict(sequence) if isinstance(sequence, dict) else {}
                        new_sequence["slides"] = new_slides
                        new_context = dict(context)
                        new_context["sequence"] = new_sequence
                        scene.context = new_context
                        session.commit()
                        logger.info(
                            "Updated sequence slide with generated image.",
                            extra={"scene_id": job.scene_id, "slide_id": slide_id, "job_id": job.id},
                        )

        job.status = GenerationStatus.DONE
        job.stage = "done"
        job.progress = 100
        job.results = {
            "image_urls": urls,
            "variant_count": len(urls),
            "approved_variant_id": approved_variant_id,
            "approved_variant_url": approved_variant_url,
        }
        job.finished_at = datetime.utcnow()
        session.commit()
        session.refresh(job)
        
        track_event(
            "generation_job_completed",
            metadata={
                "job_id": job.id,
                "scene_id": job.scene_id,
                "variant_count": len(job.variants),
            },
        )

        return {
            "job_id": job.id,
            "scene_id": job.scene_id,
            "prompt": job.prompt,
            "negative_prompt": job.negative_prompt,
            "cfg_scale": cfg_scale,
            "steps": steps,
            "image_urls": urls,
            "sampler": sampler,
            "scheduler": scheduler,
            "model_id": model_id,
            "vae_id": vae_id,
            "loras": loras,
        }
