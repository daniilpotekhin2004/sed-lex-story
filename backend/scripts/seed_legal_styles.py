"""Seed legal style profile templates into existing projects.

Usage:
  python -m scripts.seed_legal_styles --project <project_id>
  python -m scripts.seed_legal_styles --all

This is safe to run multiple times. It will not duplicate styles for a project
that already has at least one StyleProfile.
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import async_session
from app.domain.models import Project, StyleProfile
from app.services.style_templates import load_style_templates

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def seed_for_project(project_id: str) -> None:
    templates = load_style_templates()
    if not templates:
        logger.warning("No templates loaded; nothing to seed")
        return

    async with async_session() as session:
        project = await session.get(Project, project_id)
        if project is None:
            logger.error("Project not found: %s", project_id)
            return

        existing = await session.execute(
            select(StyleProfile.id).where(StyleProfile.project_id == project.id).limit(1)
        )
        if existing.first() is not None:
            logger.info("Project already has styles; skipping: %s", project_id)
            return

        created = []
        recommended = None
        for tpl in templates:
            style = StyleProfile(
                project_id=project.id,
                name=tpl.name,
                description=tpl.description,
                base_prompt=tpl.base_prompt,
                negative_prompt=tpl.negative_prompt,
                model_checkpoint=tpl.model_checkpoint,
                lora_refs=tpl.lora_refs,
                aspect_ratio=tpl.aspect_ratio,
                resolution=tpl.resolution,
                sampler=tpl.sampler,
                steps=tpl.steps,
                cfg_scale=tpl.cfg_scale,
                seed_policy=tpl.seed_policy,
                palette=tpl.palette,
                forbidden=tpl.forbidden,
                style_metadata=tpl.style_metadata,
            )
            session.add(style)
            created.append(style)
            if tpl.style_metadata and tpl.style_metadata.get("recommended") is True:
                recommended = style

        await session.flush()

        if not project.style_profile_id and created:
            project.style_profile_id = (recommended.id if recommended is not None else created[0].id)

        await session.commit()

        logger.info(
            "Seeded %d style profiles into project %s (active=%s)",
            len(created),
            project_id,
            project.style_profile_id,
        )


async def seed_all() -> None:
    settings = get_settings()
    templates = load_style_templates(settings.style_profile_templates_path)
    if not templates:
        logger.warning("No templates loaded; nothing to seed")
        return

    async with async_session() as session:
        result = await session.execute(select(Project))
        projects = list(result.scalars().all())

    for project in projects:
        await seed_for_project(project.id)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=str)
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    if not args.project and not args.all:
        parser.error("Specify --project <id> or --all")

    if args.all:
        asyncio.run(seed_all())
    else:
        asyncio.run(seed_for_project(args.project))


if __name__ == "__main__":
    main()
