"""
Prompt Builder - Centralized prompt construction for all generation types.

Root cause: Prompt building logic scattered across multiple services
Solution: Single source of truth for prompt construction
"""
from __future__ import annotations

import random
import re
from typing import Optional

from app.domain.character_references import (
    DEFAULT_VIEW_SPECIFIC_PROMPTS,
    DEFAULT_VIEW_SPECIFIC_NEGATIVES,
    get_view_key_for_kind,
)
from app.utils.sd_tokens import prepend_tokens

_WILDCARD_PATTERN = re.compile(r"\{([^{}]+)\}")


class PromptBuilder:
    """Builds prompts for SD generation"""
    
    def __init__(self, wildcards: Optional[dict[str, list[str]]] = None):
        """
        Initialize prompt builder.
        
        Args:
            wildcards: Optional dict of wildcard replacements
        """
        self.wildcards = wildcards or {}
    
    def expand_wildcards(self, prompt: str) -> str:
        """
        Expand {wildcard} tokens in prompt.
        
        Supports:
        - Named wildcards: {hair_color} -> looks up in self.wildcards
        - Inline options: {red|blue|green} -> picks one randomly
        """
        if not prompt or not self.wildcards:
            return prompt
        
        rng = random.SystemRandom()
        chosen: dict[str, str] = {}
        
        def _pick(options: list[str], key: str) -> str:
            if key not in chosen:
                chosen[key] = rng.choice(options)
            return chosen[key]
        
        def _replace(match: re.Match) -> str:
            token = match.group(1).strip()
            if not token:
                return match.group(0)
            
            # Inline options: {red|blue|green}
            if "|" in token:
                options = [part.strip() for part in token.split("|") if part.strip()]
                if not options:
                    return match.group(0)
                return _pick(options, f"inline::{token}")
            
            # Named wildcard: {hair_color}
            key = token.strip().strip("_").lower()
            if not key:
                return match.group(0)
            
            options = self.wildcards.get(key)
            if not options:
                return match.group(0)
            
            return _pick(options, key)
        
        return _WILDCARD_PATTERN.sub(_replace, prompt)
    
    def build_character_reference_prompt(
        self,
        *,
        kind: str,
        base_prompt: str,
        sd_tokens: list[str],
        view_specific_prompts: Optional[dict] = None,
        slot_prompt: Optional[str] = None,
    ) -> str:
        """
        Build prompt for character reference generation.
        
        Args:
            kind: Reference kind (e.g. "full_front", "portrait")
            base_prompt: Base character description
            sd_tokens: List of SD tokens (LoRA, embeddings, anchor)
            view_specific_prompts: Optional override for view prompts
            slot_prompt: Optional fallback slot prompt
        
        Returns:
            Complete prompt with tokens prepended
        """
        view_prompts = view_specific_prompts or DEFAULT_VIEW_SPECIFIC_PROMPTS
        view_key = get_view_key_for_kind(kind)
        
        prompt_parts = []
        
        # 1. View-specific prompt (most important - clear angle instruction)
        if view_key and view_key in view_prompts:
            prompt_parts.append(view_prompts[view_key])
        elif slot_prompt:
            prompt_parts.append(slot_prompt)
        
        # 2. Base character description (identity)
        if base_prompt:
            prompt_parts.append(base_prompt)
        
        prompt_text = ", ".join([p for p in prompt_parts if p])
        
        # Expand wildcards
        prompt_text = self.expand_wildcards(prompt_text)
        
        # Prepend SD tokens
        return prepend_tokens(prompt_text, sd_tokens)
    
    def build_character_reference_negative(
        self,
        *,
        kind: str,
        base_negatives: list[str],
        view_specific_negatives: Optional[dict] = None,
        slot_negative: Optional[str | list[str]] = None,
    ) -> str:
        """
        Build negative prompt for character reference generation.
        
        Args:
            kind: Reference kind
            base_negatives: Base negative prompts (style, preset, etc.)
            view_specific_negatives: Optional override for view negatives
            slot_negative: Optional slot-specific negatives
        
        Returns:
            Complete negative prompt
        """
        view_negatives = view_specific_negatives or DEFAULT_VIEW_SPECIFIC_NEGATIVES
        view_key = get_view_key_for_kind(kind)
        
        negative_parts = []
        
        # 1. View-specific negatives (most important)
        if view_key and view_key in view_negatives:
            negative_parts.append(view_negatives[view_key])
        
        # 2. Slot-specific negatives
        if slot_negative:
            if isinstance(slot_negative, list):
                negative_parts.extend([str(n) for n in slot_negative if n])
            elif isinstance(slot_negative, str) and slot_negative.strip():
                negative_parts.append(slot_negative.strip())
        
        # 3. Essential quality negatives only
        negative_parts.append("blurry, low quality, deformed")
        
        # Skip base_negatives - they're too verbose and dilute view-specific negatives
        
        return ", ".join([n for n in negative_parts if n]) or ""
    
    def build_scene_prompt(
        self,
        *,
        base_prompt: str,
        style_prompt: Optional[str] = None,
        sd_tokens: Optional[list[str]] = None,
    ) -> str:
        """
        Build prompt for scene generation.
        
        Args:
            base_prompt: Base scene description
            style_prompt: Optional style additions
            sd_tokens: Optional SD tokens to prepend
        
        Returns:
            Complete prompt
        """
        parts = [base_prompt]
        if style_prompt:
            parts.append(style_prompt)
        
        prompt = ", ".join([p for p in parts if p])
        prompt = self.expand_wildcards(prompt)
        
        if sd_tokens:
            prompt = prepend_tokens(prompt, sd_tokens)
        
        return prompt
