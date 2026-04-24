from __future__ import annotations

import json
from typing import List, Optional

from app.core.config import get_settings
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Project, StyleProfile
from app.schemas.style_profiles import StyleProfileCreate, StyleProfileUpdate


class StyleProfileService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_style(self, payload: StyleProfileCreate) -> Optional[StyleProfile]:
        project = await self.session.get(Project, payload.project_id)
        if project is None:
            return None

        style = StyleProfile(
            project_id=payload.project_id,
            name=payload.name,
            description=payload.description,
            base_prompt=payload.base_prompt,
            negative_prompt=payload.negative_prompt,
            model_checkpoint=payload.model_checkpoint,
            lora_refs=payload.lora_refs,
            aspect_ratio=payload.aspect_ratio,
            resolution=payload.resolution,
            sampler=payload.sampler,
            steps=payload.steps,
            cfg_scale=payload.cfg_scale,
            seed_policy=payload.seed_policy,
            palette=payload.palette,
            forbidden=payload.forbidden,
            style_metadata=payload.style_metadata,
        )
        self.session.add(style)
        await self.session.commit()
        # Eager load relationships to avoid lazy load issues
        await self.session.refresh(style, ["project"])
        return style

    async def update_style(self, style_id: str, payload: StyleProfileUpdate) -> Optional[StyleProfile]:
        style = await self.session.get(StyleProfile, style_id)
        if style is None:
            return None
        for field, value in payload.dict(exclude_unset=True).items():
            setattr(style, field, value)
        await self.session.commit()
        # Eager load relationships to avoid lazy load issues
        await self.session.refresh(style, ["project"])
        return style

    async def list_styles(self, project_id: str) -> List[StyleProfile]:
        result = await self.session.execute(
            select(StyleProfile).where(StyleProfile.project_id == project_id)
        )
        return list(result.scalars().all())

    async def list_all(self) -> List[StyleProfile]:
        result = await self.session.execute(select(StyleProfile))
        return list(result.scalars().all())

    async def get_style(self, style_id: str) -> Optional[StyleProfile]:
        return await self.session.get(StyleProfile, style_id)

    async def bootstrap_legal_styles(self, project_id: str, *, overwrite: bool = False) -> Optional[List[StyleProfile]]:
        """Create/update a curated set of 'legal' style profiles for a project.

        Idempotent by default: if a template (identified by style_metadata.template_id) exists,
        it is skipped. When `overwrite=True`, existing templates are updated in-place.

        Returns None if project does not exist.
        """

        project = await self.session.get(Project, project_id)
        if project is None:
            return None

        settings = get_settings()
        template_path: Path = settings.style_profile_templates_path
        try:
            raw = json.loads(template_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            # Fall back to legacy name (optional)
            alt = template_path.with_name("style_profile_templates_legal.json")
            raw = json.loads(alt.read_text(encoding="utf-8"))

        templates = raw.get("templates") or []

        result = await self.session.execute(select(StyleProfile).where(StyleProfile.project_id == project_id))
        existing_styles: list[StyleProfile] = list(result.scalars().all())

        by_template_id: dict[str, StyleProfile] = {}
        for style in existing_styles:
            meta = style.style_metadata if isinstance(style.style_metadata, dict) else {}
            tid = meta.get("template_id")
            if isinstance(tid, str) and tid:
                by_template_id[tid] = style

        created_or_updated: list[StyleProfile] = []

        for tpl in templates:
            if not isinstance(tpl, dict):
                continue
            template_id = str(tpl.get("template_id") or "").strip()
            if not template_id:
                continue

            meta = tpl.get("style_metadata") if isinstance(tpl.get("style_metadata"), dict) else {}
            # Always persist the template id so future bootstrap is stable.
            meta = {**meta, "template_id": template_id, "pack": meta.get("pack") or "legal"}

            existing = by_template_id.get(template_id)
            if existing is not None and not overwrite:
                created_or_updated.append(existing)
                continue

            if existing is None:
                style = StyleProfile(
                    project_id=project_id,
                    name=str(tpl.get("name") or template_id),
                    description=tpl.get("description"),
                    base_prompt=tpl.get("base_prompt"),
                    negative_prompt=tpl.get("negative_prompt"),
                    model_checkpoint=tpl.get("model_checkpoint"),
                    lora_refs=tpl.get("lora_refs"),
                    aspect_ratio=tpl.get("aspect_ratio"),
                    resolution=tpl.get("resolution"),
                    sampler=tpl.get("sampler"),
                    steps=tpl.get("steps"),
                    cfg_scale=tpl.get("cfg_scale"),
                    seed_policy=tpl.get("seed_policy"),
                    palette=tpl.get("palette"),
                    forbidden=tpl.get("forbidden"),
                    style_metadata=meta,
                )
                self.session.add(style)
                created_or_updated.append(style)
                continue

            # overwrite existing
            existing.name = str(tpl.get("name") or existing.name)
            existing.description = tpl.get("description")
            existing.base_prompt = tpl.get("base_prompt")
            existing.negative_prompt = tpl.get("negative_prompt")
            existing.model_checkpoint = tpl.get("model_checkpoint")
            existing.lora_refs = tpl.get("lora_refs")
            existing.aspect_ratio = tpl.get("aspect_ratio")
            existing.resolution = tpl.get("resolution")
            existing.sampler = tpl.get("sampler")
            existing.steps = tpl.get("steps")
            existing.cfg_scale = tpl.get("cfg_scale")
            existing.seed_policy = tpl.get("seed_policy")
            existing.palette = tpl.get("palette")
            existing.forbidden = tpl.get("forbidden")
            existing.style_metadata = meta
            created_or_updated.append(existing)

        await self.session.commit()

        # Refresh (and eager-load project) so router can safely return them.
        for style in created_or_updated:
            try:
                await self.session.refresh(style, ["project"])
            except Exception:
                pass

        return created_or_updated
