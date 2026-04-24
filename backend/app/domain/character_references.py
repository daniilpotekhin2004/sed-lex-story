"""
Character Reference Definitions - Domain logic for character reference slots.

Root cause: Reference slot definitions scattered across service layer
Solution: Centralized domain model for character references
"""
from __future__ import annotations

from typing import Optional

# Standard reference set for a character "card"
CHARACTER_REFERENCE_SLOTS: list[dict] = [
    {
        "kind": "sketch",
        "label": "Sketch",
        "prompt": "Create a clean character sketch reference of a single person based on the provided image. Show the full body from head to toe, centered, with a neutral stance and clear silhouette on a plain studio background. Keep face details, age, identity, outfit and hairstyle consistent. No text or watermark.",
        "note": "base",
        "required": False,
        "width": 768,
        "height": 1024,
    },
    {
        "kind": "complex",
        "label": "Complex",
        "prompt": "Generate a clean full-body reference of the character shown in the sketch, keeping face details, age, identity, outfit and hairstyle consistent. Show a different pose in an urban environment, full body visible head to toe, subtle shadows, cinematic mood, photorealistic high resolution, detailed image. Avoid cropped or blurry results, deformed anatomy, text or watermarks.",
        "note": "blend",
        "required": False,
        "width": 768,
        "height": 1024,
    },
    {
        "kind": "portrait",
        "label": "Portrait",
        "prompt": "Generate a clean portrait of the character shown in the sketch. Head and shoulders, facing the camera with gentle eye contact and a neutral expression. Keep face details, age, identity, outfit and hairstyle consistent. Plain neutral background, subtle shadows, photorealistic high resolution, detailed image. Avoid cropped face, blurry results, deformed anatomy, text or watermarks.",
        "note": "portrait",
        "required": True,
        "width": 768,
        "height": 1024,
    },
    {
        "kind": "full_front",
        "label": "Full body",
        "prompt": "Generate a clean full-body front view reference of the character shown in the sketch. The character faces the camera, standing naturally with feet visible and arms relaxed. Keep face details, age, identity, outfit and hairstyle consistent. Plain neutral background, subtle shadows, cinematic mood, photorealistic high resolution, detailed image. Avoid cropped or blurry results, deformed anatomy, text or watermarks.",
        "note": "front",
        "required": True,
        "negative": "side view, back view",
        "width": 768,
        "height": 1024,
    },
    {
        "kind": "full_side",
        "label": "Full body",
        "prompt": "Generate a clean full-body side view reference of the character shown in the sketch. The character is in true side profile, one hand raised above the head in greeting, the other behind the back, full body visible head to toe. Keep face details, age, identity, outfit and hairstyle consistent. Subtle shadows, cinematic mood, photorealistic high resolution, detailed image. Avoid cropped or blurry results, deformed anatomy, text or watermarks.",
        "note": "side",
        "required": True,
        "negative": "front view, back view, facing camera",
        "width": 768,
        "height": 1024,
    },
    {
        "kind": "full_back",
        "label": "Full body",
        "prompt": "Generate a clean full-body rear view reference of the character shown in the sketch. The character is seen from behind, looking back over the shoulder toward the camera and gesturing to someone behind, full body visible head to toe. Keep face details, age, identity, outfit and hairstyle consistent. Subtle shadows, cinematic mood, photorealistic high resolution, detailed image. Avoid cropped or blurry results, deformed anatomy, text or watermarks.",
        "note": "back",
        "required": True,
        "negative": "front view, facing camera, face visible",
        "width": 768,
        "height": 1024,
    },
]

# Reference kind categories
PORTRAIT_REFERENCE_KINDS = {
    "sketch", "complex", "portrait", "profile", "face", "expression", "face_front", "face_profile"
}

BODY_REFERENCE_KINDS = {
    "full_front", "full_side", "full_back", "body", "turnaround"
}

# View-specific prompt tuning for FLUX Kontext
# Root cause: FLUX Kontext needs clear, natural language descriptions
# Solution: Clean prompts optimized for FLUX understanding with specific pose instructions
DEFAULT_VIEW_SPECIFIC_PROMPTS = {
    "portrait": "Generate a clean portrait of the character shown in the sketch. Head and shoulders, facing the camera with gentle eye contact and a neutral expression. Keep face details, age, identity, outfit and hairstyle consistent. Plain neutral background, subtle shadows, photorealistic high resolution, detailed image. Avoid cropped face, blurry results, deformed anatomy, text or watermarks.",
    "profile": "Generate a clean side profile portrait of the character shown in the sketch. True 90-degree profile, head and shoulders, clear silhouette, neutral expression. Keep face details, age, identity, outfit and hairstyle consistent. Plain neutral background, subtle shadows, photorealistic high resolution, detailed image. Avoid front view, blurry results, deformed anatomy, text or watermarks.",
    "complex": "Generate a clean full-body reference of the character shown in the sketch, keeping face details, age, identity, outfit and hairstyle consistent. Show a different pose in an urban environment, full body visible head to toe, subtle shadows, cinematic mood, photorealistic high resolution, detailed image. Avoid cropped or blurry results, deformed anatomy, text or watermarks.",
    "full_front": "Generate a clean full-body front view reference of the character shown in the sketch. The character faces the camera, standing naturally with feet visible and arms relaxed. Keep face details, age, identity, outfit and hairstyle consistent. Plain neutral background, subtle shadows, cinematic mood, photorealistic high resolution, detailed image. Avoid cropped or blurry results, deformed anatomy, text or watermarks.",
    "full_side": "Generate a clean full-body side view reference of the character shown in the sketch. The character is in true side profile, one hand raised above the head in greeting, the other behind the back, full body visible head to toe. Keep face details, age, identity, outfit and hairstyle consistent. Subtle shadows, cinematic mood, photorealistic high resolution, detailed image. Avoid cropped or blurry results, deformed anatomy, text or watermarks.",
    "full_back": "Generate a clean full-body rear view reference of the character shown in the sketch. The character is seen from behind, looking back over the shoulder toward the camera and gesturing to someone behind, full body visible head to toe. Keep face details, age, identity, outfit and hairstyle consistent. Subtle shadows, cinematic mood, photorealistic high resolution, detailed image. Avoid cropped or blurry results, deformed anatomy, text or watermarks.",
    "pose_walk": "full body walking pose, mid-stride with one leg forward, arms swinging naturally, dynamic movement, studio lighting, neutral background",
    "pose_arms": "full body standing with arms crossed over chest, confident stance, feet visible, studio lighting, neutral background",
    "pose_sit": "full body sitting on chair, relaxed position, legs visible, natural posture, studio lighting, neutral background",
}

DEFAULT_VIEW_SPECIFIC_NEGATIVES = {
    "portrait": "side view, profile, back view, turned away, full body, cropped face, multiple people",
    "profile": "front view, facing camera, back view, looking at camera, frontal, multiple people",
    "complex": "Avoid of cropped or blurry, low quality, deformed images with bad anatomy or pure details, no text or watermark should be on image",
    "full_front": "cropped, partial body, sitting, side view, back view, close up",
    "full_side": "front view, back view, cropped, facing camera",
    "full_back": "front view, side view, face visible, looking at camera",
    "pose_walk": "standing still, static pose, sitting, lying down, arms at sides, multiple people",
    "pose_arms": "arms at sides, arms down, hands in pockets, arms raised, multiple people",
    "pose_sit": "standing, walking, lying down, jumping, multiple people",
}

DEFAULT_SHEET_PROMPT_PREFIX = (
    "character reference sheet, consistent identity, same person throughout"
)


def get_reference_slot_by_kind(kind: str) -> Optional[dict]:
    """Get reference slot definition by kind"""
    for slot in CHARACTER_REFERENCE_SLOTS:
        if slot.get("kind") == kind:
            return slot
    return None


def is_portrait_kind(kind: str) -> bool:
    """Check if kind is a portrait reference"""
    return kind.lower() in PORTRAIT_REFERENCE_KINDS


def is_body_kind(kind: str) -> bool:
    """Check if kind is a body reference"""
    kind_lower = kind.lower()
    return kind_lower in BODY_REFERENCE_KINDS or kind_lower.startswith("pose")


def get_view_key_for_kind(kind: str) -> Optional[str]:
    """Determine view key for enhanced prompts based on kind"""
    kind_lower = kind.lower()
    
    if kind_lower == "portrait" or kind_lower.startswith("portrait"):
        return "portrait"
    if "portrait" in kind_lower and "front" in kind_lower:
        return "portrait"
    elif "profile" in kind_lower:
        return "profile"
    elif "full" in kind_lower and "front" in kind_lower:
        return "full_front"
    elif "full" in kind_lower and "side" in kind_lower:
        return "full_side"
    elif "full" in kind_lower and "back" in kind_lower:
        return "full_back"
    elif "pose" in kind_lower and "walk" in kind_lower:
        return "pose_walk"
    elif "pose" in kind_lower and "arms" in kind_lower:
        return "pose_arms"
    elif "pose" in kind_lower and "sit" in kind_lower:
        return "pose_sit"
    
    return None


def get_preferred_reference_kinds(target_kind: str) -> list[str]:
    """
    Get preferred reference kinds for identity consistency.
    
    Returns ordered list of reference kinds that should be used
    as identity hints when generating the target kind.
    """
    kind_lower = target_kind.lower()
    
    # Portrait references prefer other portraits
    if is_portrait_kind(kind_lower):
        return [
            "sketch", "complex", "portrait", "profile",
            "face_front", "face_profile", "face", "expression", "canonical"
        ]
    
    # Body references prefer other body references
    if is_body_kind(kind_lower):
        return [
            "full_front", "full_side", "full_back", "complex",
            "body", "turnaround"
        ]
    
    # Default: prefer sketch and complex
    return ["sketch", "complex", "canonical"]


def calculate_denoise_strength(
    target_kind: str,
    reference_kind: Optional[str],
    has_reference: bool
) -> Optional[float]:
    """
    Calculate appropriate denoising strength for img2img.
    
    Args:
        target_kind: Kind of reference being generated
        reference_kind: Kind of reference being used as input
        has_reference: Whether a reference image is available
    
    Returns:
        Denoise strength (0.0-1.0) or None for txt2img
    """
    if not has_reference or not reference_kind:
        return None
    
    target_lower = target_kind.lower()
    ref_lower = reference_kind.lower()
    
    # Same kind: high preservation
    if target_lower == ref_lower:
        return 0.3
    
    # Same category: moderate preservation
    target_is_portrait = is_portrait_kind(target_lower)
    target_is_body = is_body_kind(target_lower)
    ref_is_portrait = is_portrait_kind(ref_lower)
    ref_is_body = is_body_kind(ref_lower)
    
    if target_is_portrait and ref_is_portrait:
        return 0.5
    if target_is_body and ref_is_body:
        return 0.5
    
    # Cross-category: low preservation (identity hint only)
    if (target_is_portrait and ref_is_body) or (target_is_body and ref_is_portrait):
        return 0.7
    
    # Default: moderate
    return 0.6
