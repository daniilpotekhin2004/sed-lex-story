"""
Scene Composition Prompt Generation API

Generates Qwen-based composition prompts for scene slides using img2img workflow.
Maps location and character references to the correct image slots for scene_img2img.json.
"""

from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.infra.db import get_session
from app.domain.models import SceneNode, SceneNodeCharacter, CharacterPreset, Location
from app.infra.llm_client import create_chat_completion
from app.services.scene_composition_adapter import (
    IMAGE_ROLE_GUIDANCE,
    LEGACY_IMAGE_ROLE_GUIDANCE,
    build_slot_character_list,
    build_composition_guardrails,
    build_people_constraints,
    build_story_action_hint,
    enforce_slot_identity_labels,
    ensure_english_prompt,
    infer_background_extras_policy,
    normalize_composition_prompt,
)
from sqlalchemy import select

router = APIRouter(prefix="/scenes", tags=["scene-composition"])


class CompositionPromptRequest(BaseModel):
    """Request to generate composition prompt for a slide"""
    scene_id: str
    slide_visual: str  # Visual description from Step 3
    cast_ids: list[str]  # Character preset IDs
    slide_id: Optional[str] = None
    location_id: Optional[str] = None
    has_location_reference: Optional[bool] = None
    framing: Optional[str] = "full"
    allow_background_extras: Optional[bool] = None
    background_extras_count: Optional[int] = None
    background_extras_min: Optional[int] = None
    background_extras_max: Optional[int] = None
    background_extras_note: Optional[str] = None


class CompositionPromptResponse(BaseModel):
    """Generated composition prompt for img2img"""
    composition_prompt: str
    location_ref_url: Optional[str] = None
    character_ref_urls: list[str]


def _find_slide_context(scene: SceneNode, slide_id: str | None) -> dict[str, Any] | None:
    if not slide_id:
        return None
    context = scene.context if isinstance(scene.context, dict) else {}
    sequence = context.get("sequence") if isinstance(context.get("sequence"), dict) else {}
    slides = sequence.get("slides") if isinstance(sequence.get("slides"), list) else []
    for slide in slides:
        if isinstance(slide, dict) and str(slide.get("id")) == str(slide_id):
            return slide
    return None


async def _build_composition_prompt(
    scene: SceneNode,
    slide_visual: str,
    characters: list[CharacterPreset],
    location: Optional[Location],
    framing: str,
    has_location_reference: bool,
    slot_positions: list[str | None] | None = None,
    action_hint: str | None = None,
    slide_context: Optional[dict[str, Any]] = None,
    requested_cast_count: Optional[int] = None,
) -> str:
    """
    Generate composition prompt using LLM for img2img scene generation.
    
    The prompt instructs how to place characters from reference images into
    the location background, following the Qwen Image Edit pattern.
    """
    
    # Build location context
    location_desc = ""
    if location:
        location_desc = f"{location.name}"
        if location.description:
            location_desc += f" — {location.description[:150]}"
    else:
        location_desc = "the background scene"

    # Build character descriptions aligned to image slots (2 max)
    image_characters = characters[:2]
    principal_count = len(image_characters)
    slot2_name = image_characters[0].name if len(image_characters) > 0 else None
    slot3_name = image_characters[1].name if len(image_characters) > 1 else None
    char_list = build_slot_character_list(principal_count=principal_count)
    
    # Build framing hint
    framing_hint = {
        "full": "full body shot, showing entire figure",
        "half": "waist-up shot, half body",
        "portrait": "close-up portrait, head and shoulders"
    }.get(framing, "full body shot")

    context_text = " ".join([slide_visual or "", scene.synopsis or ""]).lower()
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
    
    # System prompt for composition generation
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
    
    # User prompt with context
    user_prompt = f"""Generate a composition prompt for this scene.
Return only the prompt.
Critical: this is a cinematic story frame, not a collage. Characters must act and interact according to the action cue.

Scene context: {scene.title or 'Untitled scene'}
{f"Synopsis: {scene.synopsis[:200]}" if scene.synopsis else ""}

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
        if principal_count > 0 and image_characters:
            parts.append(
                f"Stage Character from Image 2 as an active actor; exact match for face/head; {framing_hint}."
            )
            if len(image_characters) > 1:
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
        # Generate using LLM
        result = await create_chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=200,
        )

        composition = (
            result.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )

        if not composition:
            composition = _fallback()

        return _normalize_prompt(composition)

    except Exception as e:
        # Fallback on error
        return _normalize_prompt(_fallback())


@router.post("/{scene_id}/composition-prompt", response_model=CompositionPromptResponse)
async def generate_composition_prompt(
    scene_id: str,
    request: CompositionPromptRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    Generate Qwen-based composition prompt for scene slide.
    
    This endpoint:
    1. Loads scene, characters, and location data
    2. Generates composition prompt using Qwen
    3. Returns prompt + reference image URLs for img2img workflow
    
    The returned data maps to scene_img2img.json workflow:
    - location_ref_url → image1 (background)
    - character_ref_urls[0] → image2 (first character)
    - character_ref_urls[1] → image3 (second character, if exists)
    """
    
    # Load scene
    result = await session.execute(
        select(SceneNode).where(SceneNode.id == scene_id)
    )
    scene = result.scalar_one_or_none()
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    slide_context = _find_slide_context(scene, request.slide_id)
    adapter_context: dict[str, Any] = dict(slide_context) if isinstance(slide_context, dict) else {}
    if request.allow_background_extras is not None:
        adapter_context["allow_background_extras"] = request.allow_background_extras
    if request.background_extras_count is not None:
        adapter_context["background_extras_count"] = request.background_extras_count
    if request.background_extras_min is not None:
        adapter_context["background_extras_min"] = request.background_extras_min
    if request.background_extras_max is not None:
        adapter_context["background_extras_max"] = request.background_extras_max
    if request.background_extras_note:
        adapter_context["background_extras_note"] = request.background_extras_note

    effective_slide_visual = (request.slide_visual or "").strip()
    if not effective_slide_visual and isinstance(slide_context, dict):
        for key in ("user_prompt", "visual", "title"):
            value = slide_context.get(key)
            if isinstance(value, str) and value.strip():
                effective_slide_visual = value.strip()
                break
    if not effective_slide_visual:
        effective_slide_visual = scene.title or "Scene composition"

    slide_location_id = None
    if isinstance(slide_context, dict):
        raw_location = slide_context.get("location_id")
        if isinstance(raw_location, str) and raw_location.strip():
            slide_location_id = raw_location.strip()
    effective_location_id = request.location_id or slide_location_id

    effective_framing = request.framing or "full"
    if isinstance(slide_context, dict):
        raw_framing = slide_context.get("framing")
        if isinstance(raw_framing, str) and raw_framing.strip():
            effective_framing = raw_framing.strip()

    effective_cast_ids: list[str] = []
    source_cast_ids = request.cast_ids
    if not source_cast_ids and isinstance(slide_context, dict):
        slide_cast = slide_context.get("cast_ids")
        if isinstance(slide_cast, list):
            source_cast_ids = [str(value) for value in slide_cast if value is not None]
    for value in source_cast_ids or []:
        raw = str(value).strip()
        if raw and raw not in effective_cast_ids:
            effective_cast_ids.append(raw)

    cast_links_result = await session.execute(
        select(SceneNodeCharacter).where(SceneNodeCharacter.scene_id == scene_id)
    )
    scene_cast_links = list(cast_links_result.scalars().all())
    cast_lookup: dict[str, SceneNodeCharacter] = {}
    for link in scene_cast_links:
        if link.id:
            cast_lookup[str(link.id)] = link
        if link.character_preset_id:
            cast_lookup[str(link.character_preset_id)] = link

    # Load location
    location = None
    if effective_location_id:
        result = await session.execute(
            select(Location).where(Location.id == effective_location_id)
        )
        location = result.scalar_one_or_none()
    
    # Load characters (preserve cast order, limit to 2 for workflow)
    characters: list[CharacterPreset] = []
    slot_positions: list[str | None] = []
    if effective_cast_ids:
        ordered_preset_ids: list[str] = []
        position_by_preset: dict[str, str | None] = {}
        for cast_id in effective_cast_ids:
            link = cast_lookup.get(cast_id)
            preset_id = str(link.character_preset_id) if link and link.character_preset_id else cast_id
            if preset_id not in ordered_preset_ids:
                ordered_preset_ids.append(preset_id)
                if link and isinstance(link.position, str):
                    position_by_preset[preset_id] = link.position
                else:
                    position_by_preset[preset_id] = None
        result = await session.execute(
            select(CharacterPreset).where(CharacterPreset.id.in_(ordered_preset_ids))
        )
        fetched = list(result.scalars().all())
        by_id = {char.id: char for char in fetched}
        ordered = []
        for char_id in ordered_preset_ids:
            char = by_id.get(char_id)
            if char and char not in ordered:
                ordered.append(char)
        characters = ordered[:2]
        slot_positions = [position_by_preset.get(char.id) for char in characters]
    
    # Gather reference URLs for img2img workflow first so prompt generation can react when location is missing.
    location_ref_url = None
    if location:
        if location.preview_image_url:
            location_ref_url = location.preview_image_url
        elif location.reference_images:
            for ref in location.reference_images:
                if isinstance(ref, dict):
                    ref_url = ref.get("url") or ref.get("thumb_url") or ref.get("thumbnail_url")
                    if ref_url:
                        location_ref_url = str(ref_url)
                        break
    
    character_ref_urls = []
    characters_with_refs: list[CharacterPreset] = []
    for char in characters:
        # Use preview image or first available reference from reference_images JSON
        ref_url = char.preview_image_url
        if not ref_url and char.reference_images:
            # reference_images is JSON: [{"kind": "portrait", "url": "...", "thumb_url": "...", "meta": {}}, ...]
            for ref in char.reference_images:
                if isinstance(ref, dict):
                    # Prefer portrait references
                    if ref.get("kind") == "portrait" and ref.get("url"):
                        ref_url = ref.get("url")
                        break
            # If no portrait found, use any available reference
            if not ref_url:
                for ref in char.reference_images:
                    if isinstance(ref, dict) and ref.get("url"):
                        ref_url = ref.get("url")
                        break
        
        if ref_url:
            character_ref_urls.append(ref_url)
            characters_with_refs.append(char)

    # Generate composition prompt
    has_location_reference = (
        bool(request.has_location_reference)
        if request.has_location_reference is not None
        else bool(location_ref_url)
    )
    action_hint = build_story_action_hint(
        slide_context=adapter_context if adapter_context else None,
        slide_visual=effective_slide_visual,
        scene_synopsis=scene.synopsis,
    )

    composition_prompt = await _build_composition_prompt(
        scene=scene,
        slide_visual=effective_slide_visual,
        characters=characters_with_refs,
        location=location,
        framing=effective_framing,
        has_location_reference=has_location_reference,
        slot_positions=slot_positions,
        action_hint=action_hint,
        slide_context=adapter_context,
        requested_cast_count=len(effective_cast_ids),
    )

    # Persist generated composition prompt into scene context when slide_id is provided.
    # This keeps prompt state stable when user switches scenes in UI.
    if request.slide_id:
        context = scene.context if isinstance(scene.context, dict) else {}
        sequence = context.get("sequence") if isinstance(context.get("sequence"), dict) else {}
        slides = sequence.get("slides") if isinstance(sequence.get("slides"), list) else []
        if slides:
            updated = False
            new_slides = []
            for slide in slides:
                if isinstance(slide, dict) and str(slide.get("id")) == request.slide_id:
                    new_slide = dict(slide)
                    new_slide["composition_prompt"] = composition_prompt
                    new_slides.append(new_slide)
                    updated = True
                else:
                    new_slides.append(slide)
            if updated:
                new_sequence = dict(sequence)
                new_sequence["slides"] = new_slides
                new_context = dict(context)
                new_context["sequence"] = new_sequence
                scene.context = new_context
                await session.commit()

    return CompositionPromptResponse(
        composition_prompt=composition_prompt,
        location_ref_url=location_ref_url,
        character_ref_urls=character_ref_urls,
    )
