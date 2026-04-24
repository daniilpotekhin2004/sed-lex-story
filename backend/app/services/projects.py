from __future__ import annotations

import logging
from datetime import datetime

from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.domain.models import Project, ScenarioGraph, StyleProfile, User, UserRole
from app.schemas.projects import ProjectCreate, ProjectUpdate
from app.schemas.scenario import ScenarioGraphCreate
from app.services.style_templates import load_style_templates
from app.core.telemetry import track_event

logger = logging.getLogger(__name__)


class ProjectService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _get_active_project_entity(self, project_id: str, actor: User | None = None) -> Optional[Project]:
        query = select(Project).where(
            Project.id == project_id,
            Project.archived_at.is_(None),
        )
        if actor is not None and actor.role != UserRole.ADMIN:
            query = query.where(Project.owner_id == actor.id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def _seed_style_profiles_for_project(self, project: Project) -> None:
        """Create a small set of recommended (legal) StyleProfile rows for a new project.

        We keep templates in a JSON file and clone them per project because StyleProfile has a
        required project_id.

        This is intentionally *best-effort*:
        - If the template file is missing/corrupted, we do nothing.
        - If the project already has styles, we do nothing.
        """

        templates = load_style_templates()
        if not templates:
            return

        # If styles already exist for this project, don't duplicate.
        existing = await self.session.execute(
            select(StyleProfile.id).where(StyleProfile.project_id == project.id).limit(1)
        )
        if existing.first() is not None:
            return

        created: list[StyleProfile] = []
        recommended: StyleProfile | None = None

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
            self.session.add(style)
            created.append(style)
            if tpl.style_metadata and tpl.style_metadata.get('recommended') is True:
                recommended = style

        # Assign ids
        await self.session.flush()

        # If caller didn't pick a style profile explicitly, set the recommended one.
        if not project.style_profile_id and created:
            project.style_profile_id = (recommended.id if recommended is not None else created[0].id)

        await self.session.commit()

    async def create_project(self, payload: ProjectCreate, actor: User) -> Project:
        owner_id = actor.id
        if actor.role == UserRole.ADMIN and payload.owner_id:
            owner_id = payload.owner_id
        project = Project(
            name=payload.name,
            description=payload.description,
            story_outline=getattr(payload, "story_outline", None),
            owner_id=owner_id,
            style_profile_id=payload.style_profile_id,
        )
        self.session.add(project)
        await self.session.commit()

        # Seed recommended per-project style profiles (legal templates).
        # Best-effort: failures should not block project creation.
        try:
            await self._seed_style_profiles_for_project(project)
        except Exception as exc:
            logger.warning("Failed to seed default style profiles: %s", exc)

        # Eager load relationships to avoid lazy load issues
        await self.session.refresh(project, ["style_profile", "graphs"])
        track_event("project_created", user_id=owner_id, metadata={"project_id": project.id})
        return project

    async def list_projects(self, actor: User) -> List[Project]:
        query = (
            select(Project)
            .options(
                selectinload(Project.style_profile),
            )
            .where(Project.archived_at.is_(None))
        )
        if actor.role != UserRole.ADMIN:
            query = query.where(Project.owner_id == actor.id)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_project(self, project_id: str, actor: User) -> Optional[Project]:
        query = (
            select(Project)
            .options(
                selectinload(Project.style_profile),
                selectinload(Project.graphs.and_(ScenarioGraph.archived_at.is_(None))),
            )
            .where(
                Project.id == project_id,
                Project.archived_at.is_(None),
            )
        )
        if actor.role != UserRole.ADMIN:
            query = query.where(Project.owner_id == actor.id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def update_project(self, project_id: str, payload: ProjectUpdate, actor: User) -> Optional[Project]:
        project = await self._get_active_project_entity(project_id, actor=actor)
        if project is None:
            return None

        for field, value in payload.dict(exclude_unset=True).items():
            setattr(project, field, value)

        await self.session.commit()
        return await self.get_project(project_id, actor=actor)

    async def create_graph(self, project_id: str, payload: ScenarioGraphCreate, actor: User) -> Optional[ScenarioGraph]:
        # Ensure project exists
        project = await self._get_active_project_entity(project_id, actor=actor)
        if project is None:
            return None

        graph = ScenarioGraph(
            project_id=project_id,
            title=payload.title,
            description=payload.description,
            root_scene_id=payload.root_scene_id,
        )
        self.session.add(graph)
        await self.session.commit()
        
        # Refresh with eager loading to avoid lazy load issues during serialization
        await self.session.refresh(graph, ["project", "scenes", "edges"])
        return graph

    async def archive_project(self, project_id: str, actor: User) -> bool:
        project = await self._get_active_project_entity(project_id, actor=actor)
        if project is None:
            return False

        archived_at = datetime.utcnow()
        project.archived_at = archived_at
        await self.session.execute(
            update(ScenarioGraph)
            .where(
                ScenarioGraph.project_id == project_id,
                ScenarioGraph.archived_at.is_(None),
            )
            .values(archived_at=archived_at)
        )
        await self.session.commit()
        return True
