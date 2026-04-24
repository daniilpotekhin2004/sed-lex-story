"""app.utils.sd_tokens

Helpers to serialize Stable Diffusion special tokens.

- LoRA / extra networks tokens are typically written as: `<lora:NAME:WEIGHT>`
- Textual inversion / embeddings are usually just their token name inside the prompt.

Keeping this logic in one place makes prompt construction deterministic.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, List, Optional

DEFAULT_LORA_WEIGHT = 0.8
_LORA_TOKEN_REGEX = re.compile(r"<lora:([^:>]+)(?::([^>]+))?>")


def collect_lora_tokens(lora_refs: Optional[Iterable[Any]], default_weight: float = DEFAULT_LORA_WEIGHT) -> List[str]:
    """Convert LoRA refs (dicts/strings/objects) into A1111 `<lora:...>` tokens."""
    if not lora_refs:
        return []

    tokens: List[str] = []
    for item in lora_refs:
        if item is None:
            continue

        name: Optional[str] = None
        weight: Optional[float] = None

        if isinstance(item, str):
            name = item.strip()
        elif isinstance(item, dict):
            raw_name = item.get("name") or item.get("id")
            if raw_name:
                name = str(raw_name).strip()
            raw_weight = item.get("weight")
            try:
                if raw_weight is not None:
                    weight = float(raw_weight)
            except Exception:
                weight = None
        else:
            raw_name = getattr(item, "name", None)
            if raw_name:
                name = str(raw_name).strip()
            raw_weight = getattr(item, "weight", None)
            try:
                if raw_weight is not None:
                    weight = float(raw_weight)
            except Exception:
                weight = None

        if not name:
            continue

        w = default_weight if weight is None else weight
        tokens.append(f"<lora:{name}:{w}>")

    # Deduplicate by LoRA name while preserving order
    seen: set[str] = set()
    out: List[str] = []
    for tok in tokens:
        match = re.match(r"<lora:([^:>]+):", tok)
        key = match.group(1) if match else tok
        if key in seen:
            continue
        seen.add(key)
        out.append(tok)

    return out


def extract_lora_tokens(prompt: str, default_weight: float = DEFAULT_LORA_WEIGHT) -> tuple[str, List[dict]]:
    """Extract <lora:name:weight> tokens from prompt and return cleaned prompt + structured list."""
    if not prompt:
        return prompt, []

    loras: List[dict] = []

    def _repl(match: re.Match) -> str:
        name = match.group(1).strip()
        raw_weight = match.group(2)
        weight = default_weight
        if raw_weight:
            try:
                weight = float(raw_weight)
            except Exception:
                weight = default_weight
        if name:
            loras.append({"name": name, "weight": weight})
        return ""

    cleaned = _LORA_TOKEN_REGEX.sub(_repl, prompt)
    cleaned = re.sub(r"\s*,\s*,", ", ", cleaned)
    cleaned = cleaned.strip(" ,")
    return cleaned, merge_loras(loras)


def merge_loras(*groups: Optional[Iterable[Any]]) -> List[dict]:
    """Merge LoRA lists by name, keeping last occurrence.

    The merged dict may include "optional": True to allow the SD layer to skip missing LoRAs
    quietly (useful for curated style packs that reference community LoRAs which may not
    be installed everywhere).
    """
    merged: dict[str, dict] = {}
    for group in groups:
        if not group:
            continue
        for item in group:
            if not item:
                continue
            name = None
            weight = DEFAULT_LORA_WEIGHT
            clip_weight = None
            optional = False
            if isinstance(item, dict):
                raw_name = item.get("name") or item.get("id")
                if raw_name:
                    name = str(raw_name).strip()
                raw_weight = item.get("weight")
                try:
                    if raw_weight is not None:
                        weight = float(raw_weight)
                except Exception:
                    weight = DEFAULT_LORA_WEIGHT
                raw_clip = item.get("clip_weight")
                if raw_clip is None:
                    raw_clip = item.get("weight_clip")
                if raw_clip is None:
                    raw_clip = item.get("strength_clip")
                try:
                    if raw_clip is not None:
                        clip_weight = float(raw_clip)
                except Exception:
                    clip_weight = None
                optional = bool(item.get("optional"))
            elif isinstance(item, str):
                name = item.strip()
            else:
                raw_name = getattr(item, "name", None)
                if raw_name:
                    name = str(raw_name).strip()
                raw_weight = getattr(item, "weight", None)
                try:
                    if raw_weight is not None:
                        weight = float(raw_weight)
                except Exception:
                    weight = DEFAULT_LORA_WEIGHT
                raw_clip = getattr(item, "clip_weight", None)
                try:
                    if raw_clip is not None:
                        clip_weight = float(raw_clip)
                except Exception:
                    clip_weight = None
                optional = bool(getattr(item, "optional", False))
            if not name:
                continue

            prev_optional = bool((merged.get(name) or {}).get("optional"))
            prev_clip = (merged.get(name) or {}).get("clip_weight")
            merged[name] = {
                "name": name,
                "weight": weight,
                "clip_weight": clip_weight if clip_weight is not None else prev_clip,
                "optional": (optional or prev_optional),
            }
    return list(merged.values())


def format_lora_tokens(lora_refs: Optional[Iterable[Any]], default_weight: float = DEFAULT_LORA_WEIGHT) -> List[str]:
    """Format LoRA refs into <lora:...> tokens."""
    return collect_lora_tokens(lora_refs, default_weight=default_weight)


def collect_embedding_tokens(embeddings: Optional[Iterable[Any]]) -> List[str]:
    """Deduplicate embedding tokens while preserving order."""
    if not embeddings:
        return []

    seen: set[str] = set()
    out: List[str] = []
    for item in embeddings:
        if item is None:
            continue
        token = str(item).strip()
        if not token:
            continue
        if token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def prepend_tokens(prompt: str, tokens: List[str]) -> str:
    """Prepend comma-separated tokens to an existing prompt."""
    if not tokens:
        return prompt
    token_str = ", ".join(tokens)
    prompt = (prompt or "").strip()
    if not prompt:
        return token_str
    return f"{token_str}, {prompt}"
