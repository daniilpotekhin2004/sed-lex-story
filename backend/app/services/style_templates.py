from __future__ import annotations

import json
import logging
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class StyleTemplate(BaseModel):
    """A portable template that can be seeded into a Project as a StyleProfile.

    We intentionally keep this model tolerant to different template file shapes
    to avoid breaking changes in configs.
    """

    key: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    description: Optional[str] = None

    base_prompt: Optional[str] = None
    negative_prompt: Optional[str] = None

    model_checkpoint: Optional[str] = None
    lora_refs: Optional[list[dict[str, Any]]] = None

    sampler: Optional[str] = None
    steps: Optional[int] = None
    cfg_scale: Optional[float] = None
    seed_policy: Optional[str] = None

    resolution: Optional[dict[str, Any]] = None
    palette: Optional[dict[str, Any]] = None
    forbidden: Optional[dict[str, Any]] = None
    style_metadata: Optional[dict[str, Any]] = None

    @classmethod
    def from_raw(cls, raw: Any) -> "StyleTemplate":
        if not isinstance(raw, dict):
            raise ValueError("Style template must be an object")

        key = raw.get("key") or raw.get("template_id") or raw.get("id")
        if not isinstance(key, str) or not key.strip():
            raise ValueError("Style template is missing 'key'/'template_id'")

        style_metadata = raw.get("style_metadata") if isinstance(raw.get("style_metadata"), dict) else None
        description = raw.get("description") if isinstance(raw.get("description"), str) else None
        if style_metadata is not None and description and "description" not in style_metadata:
            # Preserve description for UI without needing a dedicated DB column.
            style_metadata = {**style_metadata, "description": description}

        return cls(
            key=key.strip(),
            name=str(raw.get("name") or key).strip(),
            description=description,
            base_prompt=raw.get("base_prompt") if isinstance(raw.get("base_prompt"), str) else None,
            negative_prompt=raw.get("negative_prompt") if isinstance(raw.get("negative_prompt"), str) else None,
            model_checkpoint=raw.get("model_checkpoint") if isinstance(raw.get("model_checkpoint"), str) else None,
            lora_refs=raw.get("lora_refs") if isinstance(raw.get("lora_refs"), list) else None,
            sampler=raw.get("sampler") if isinstance(raw.get("sampler"), str) else None,
            steps=int(raw.get("steps")) if raw.get("steps") is not None else None,
            cfg_scale=float(raw.get("cfg_scale")) if raw.get("cfg_scale") is not None else None,
            seed_policy=raw.get("seed_policy") if isinstance(raw.get("seed_policy"), str) else None,
            resolution=raw.get("resolution") if isinstance(raw.get("resolution"), dict) else None,
            palette=raw.get("palette") if isinstance(raw.get("palette"), dict) else None,
            forbidden=raw.get("forbidden") if isinstance(raw.get("forbidden"), dict) else None,
            style_metadata=style_metadata,
        )


def load_style_templates() -> list[StyleTemplate]:
    """Load style templates from the configured JSON file.

    Supported file shapes:
    1) A list of templates: [ { ... }, { ... } ]
    2) A pack object: { "templates": [ { ... }, ... ], ... }
    """

    settings = get_settings()
    path = settings.style_profile_templates_path
    if not path.exists():
        logger.info("Style template file not found: %s", path)
        return []

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to read style template file %s: %s", path, exc)
        return []

    templates_raw: list[Any]
    if isinstance(raw, list):
        templates_raw = raw
    elif isinstance(raw, dict) and isinstance(raw.get("templates"), list):
        templates_raw = raw.get("templates")
    else:
        logger.warning("Unsupported style template file format in %s", path)
        return []

    out: list[StyleTemplate] = []
    for item in templates_raw:
        try:
            out.append(StyleTemplate.from_raw(item))
        except Exception as exc:
            logger.warning("Skipping invalid style template: %s", exc)
    return out
