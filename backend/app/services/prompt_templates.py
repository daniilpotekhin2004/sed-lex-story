from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import List, Optional

from app.schemas.prompting import PromptBundle


@dataclass
class CharacterPrompt:
    prompt: str
    negative_prompt: str


class PromptTemplateLibrary:
    """
    Small rule-based helper that turns short user descriptions into richer,
    generation-ready prompts. Keeps everything deterministic and testable.
    """

    DEFAULT_NEGATIVE = (
        "blurry, low quality, overexposed, underexposed, watermark, signature, "
        "extra limbs, distorted hands, deformed face, low-res, duplicated features"
    )

    QUALITY_TAGS = {
        "high": "ultra-detailed, sharp focus, 8k, photorealistic details",
        "cinematic": "cinematic still frame, depth of field, film grain, subtle bokeh",
        "aesthetic": "award-winning photography, volumetric lighting, dramatic composition",
        "illustration": "digital illustration, crisp lineart, painterly shading, rich colors",
        "noir": "film noir aesthetic, high contrast rim lighting, desaturated palette",
        "character": "studio lighting, neutral background, skin texture, accurate anatomy",
    }

    SHOT_TEMPLATES = {
        "establishing": "establishing wide shot, 24mm lens, sense of scale",
        "medium": "cinematic medium shot, 35mm lens, balanced framing",
        "portrait": "portrait close-up, 85mm lens, shallow depth of field, eyes in focus",
        "action": "dynamic action shot, 35mm lens, motion in frame, dramatic angle",
    }

    LIGHTING_TAGS = {
        "morning": "morning light, soft warm highlights, long gentle shadows",
        "day": "daytime natural light, balanced exposure, crisp details",
        "afternoon": "bright afternoon light, slightly warmer tones, defined shadows",
        "dawn": "early dawn light, pastel sky glow, soft contrast",
        "night": "night lighting, cool blue tones, gentle rim light",
        "evening": "late evening glow, warm rim light, long shadows",
        "dusk": "sunset glow, golden hour rim light, long shadows",
        "neon": "neon city lights, reflective surfaces, moody contrast",
        "overcast": "soft overcast lighting, diffuse shadows",
        "studio": "clean studio lighting, three point light setup",
    }

    MOOD_TAGS = {
        "tense": "tense atmosphere, heightened contrast",
        "calm": "calm mood, balanced soft light",
        "heroic": "heroic tone, confident posture, uplifting framing",
        "mysterious": "mysterious vibe, foggy depth, selective light",
        "romantic": "romantic warmth, soft highlights",
    }

    ROLE_TAGS = {
        "protagonist": "lead character focus",
        "antagonist": "ominous presence, antagonist focus",
        "supporting": "supporting character, complementary framing",
        "background": "background character, subtle presence",
    }

    CHARACTER_NEGATIVE = (
        "asymmetry, deformed hands, extra fingers, low detail skin, artifacts, watermark"
    )

    def _pick_shot(self, description: str, shot: Optional[str]) -> str:
        if shot:
            return self.SHOT_TEMPLATES.get(shot, self.SHOT_TEMPLATES["medium"])
        text = description.lower()
        if any(k in text for k in ["close up", "close-up", "portrait", "headshot", "face"]):
            return self.SHOT_TEMPLATES["portrait"]
        if any(k in text for k in ["run", "battle", "fight", "chase", "action"]):
            return self.SHOT_TEMPLATES["action"]
        if any(k in text for k in ["cityscape", "landscape", "vast", "wide", "establish"]):
            return self.SHOT_TEMPLATES["establishing"]
        return self.SHOT_TEMPLATES["medium"]

    def _pick_lighting(self, description: str, lighting: Optional[str]) -> Optional[str]:
        if lighting:
            return self.LIGHTING_TAGS.get(lighting, self.LIGHTING_TAGS["studio"])
        text = description.lower()
        if any(k in text for k in ["night", "moon", "midnight"]):
            return self.LIGHTING_TAGS["night"]
        if any(k in text for k in ["sunset", "dusk", "golden hour"]):
            return self.LIGHTING_TAGS["dusk"]
        if "neon" in text:
            return self.LIGHTING_TAGS["neon"]
        if "rain" in text or "cloud" in text:
            return self.LIGHTING_TAGS["overcast"]
        return self.LIGHTING_TAGS["studio"]

    def _pick_mood(self, description: str, mood: Optional[str]) -> Optional[str]:
        if mood and mood in self.MOOD_TAGS:
            return self.MOOD_TAGS[mood]
        text = description.lower()
        for key, tag in self.MOOD_TAGS.items():
            if key in text:
                return tag
        return None

    def build_scene_prompt(
        self,
        description: str,
        *,
        style: str = "cinematic",
        quality: str = "high",
        mood: Optional[str] = None,
        shot: Optional[str] = None,
        lighting: Optional[str] = None,
        negative_prompt: Optional[str] = None,
    ) -> PromptBundle:
        """
        Turn a brief scene description into a prompt/negative pair with cinematic defaults.
        """
        shot_tag = self._pick_shot(description, shot)
        lighting_tag = self._pick_lighting(description, lighting)
        mood_tag = self._pick_mood(description, mood)
        quality_tag = self.QUALITY_TAGS.get(style, self.QUALITY_TAGS.get(quality, self.QUALITY_TAGS["high"]))
        clarity_tag = self.QUALITY_TAGS["cinematic"] if style == "cinematic" else None

        prompt_parts = [
            shot_tag,
            lighting_tag,
            mood_tag,
            quality_tag,
            clarity_tag,
            description.strip(),
        ]
        prompt = ", ".join([p for p in prompt_parts if p])
        negative = negative_prompt or self.DEFAULT_NEGATIVE

        return PromptBundle(
            prompt=prompt,
            negative_prompt=negative,
            config={
                "shot": shot_tag,
                "lighting": lighting_tag,
                "mood": mood_tag,
                "quality": quality,
                "style": style,
            },
        )

    def build_character_prompt(
        self,
        name: str,
        description: str,
        *,
        traits: Optional[List[str]] = None,
        role: str = "supporting",
        anchor_token: Optional[str] = None,
        style: str = "character",
    ) -> CharacterPrompt:
        """
        Build a neutral, reusable character prompt that works well for creation
        and later consistency (turntables, sheets, single-frame portraits).
        """
        trait_str = ", ".join(traits) if traits else None
        role_tag = self.ROLE_TAGS.get(role, self.ROLE_TAGS["supporting"])
        quality = self.QUALITY_TAGS.get(style, self.QUALITY_TAGS["character"])
        anchor = f"consistency tag {anchor_token}" if anchor_token else None
        base_sheet = "turnaround character sheet, neutral pose, evenly lit, clean background"

        prompt_parts = [
            role_tag,
            name,
            description.strip(),
            trait_str,
            base_sheet,
            quality,
            anchor,
        ]
        prompt = ", ".join([p for p in prompt_parts if p])

        return CharacterPrompt(prompt=prompt, negative_prompt=self.CHARACTER_NEGATIVE)

    @staticmethod
    def stable_seed(project_id: str, character_ids: List[str], extra: str = "") -> int:
        """
        Deterministically derive a seed from project + characters so the same cast
        keeps visual consistency across scenes.
        """
        if not character_ids:
            return 0
        payload = f"{project_id}:{','.join(sorted(character_ids))}:{extra}"
        digest = hashlib.sha256(payload.encode()).digest()
        return int.from_bytes(digest[:4], "big")
