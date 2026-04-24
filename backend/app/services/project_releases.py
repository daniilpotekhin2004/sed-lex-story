from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.models import (
    Project,
    ProjectRelease,
    ProjectReleaseAccess,
    ProjectReleaseCohortAccess,
    ScenarioGraph,
    User,
    UserRole,
)
from app.schemas.player import PlayableProjectRead
from app.schemas.releases import ProjectReleaseRead, ReleaseAssignedUserRead
from app.services.export import ExportService


class ProjectReleaseError(Exception):
    pass


class ProjectReleaseService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.export_service = ExportService(session)

    async def list_releases(self, project_id: str, actor: User | None = None) -> list[ProjectReleaseRead]:
        project = await self._get_project(project_id)
        if project is None:
            raise ProjectReleaseError("Project not found")
        if actor is not None:
            self._ensure_project_manage_access(project, actor)

        result = await self.session.execute(
            select(ProjectRelease)
            .options(
                selectinload(ProjectRelease.access_entries).selectinload(ProjectReleaseAccess.user),
                selectinload(ProjectRelease.cohort_entries),
            )
            .where(ProjectRelease.project_id == project_id)
            .order_by(ProjectRelease.version.desc(), ProjectRelease.published_at.desc())
        )
        releases = result.scalars().unique().all()
        return [self._to_release_read(item) for item in releases]

    async def publish_release(
        self,
        project_id: str,
        actor: User,
        graph_id: str | None = None,
        notes: str | None = None,
    ) -> ProjectReleaseRead:
        project = await self._get_project(project_id)
        if project is None:
            raise ProjectReleaseError("Project not found")
        self._ensure_project_manage_access(project, actor)

        graph = await self._resolve_graph(project_id, graph_id)
        if graph is None:
            raise ProjectReleaseError("Playable graph not found")

        exported = await self.export_service.export_project(project_id, graph_id=graph.id)
        if exported is None:
            raise ProjectReleaseError("Playable graph export is empty")

        export_payload = self._dump_model(exported)
        manifest = self._build_manifest(export_payload)

        previous_active_release = await self._get_latest_active_release(project_id)
        next_version = await self._get_next_version(project_id)
        release = ProjectRelease(
            project_id=project_id,
            graph_id=graph.id,
            created_by_user_id=actor.id,
            version=next_version,
            status="published",
            package_version=manifest.package_version,
            notes=notes,
            published_at=datetime.utcnow(),
            manifest_payload=self._dump_model(manifest),
            export_payload=export_payload,
        )
        self.session.add(release)
        await self.session.flush()

        if previous_active_release is not None:
            source_access = await self._list_release_access_entries(previous_active_release.id)
            for access in source_access:
                self.session.add(
                    ProjectReleaseAccess(
                        release_id=release.id,
                        user_id=access.user_id,
                        granted_by_user_id=actor.id,
                    )
                )
            source_cohorts = await self._list_release_cohort_entries(previous_active_release.id)
            for cohort_entry in source_cohorts:
                self.session.add(
                    ProjectReleaseCohortAccess(
                        release_id=release.id,
                        cohort_code=cohort_entry.cohort_code,
                        granted_by_user_id=actor.id,
                    )
                )

        await self.session.commit()
        entity = await self._get_release(project_id, release.id)
        if entity is None:
            raise ProjectReleaseError("Release not found after publishing")
        return self._to_release_read(entity)

    async def archive_release(self, project_id: str, release_id: str, actor: User | None = None) -> ProjectReleaseRead:
        entity = await self._get_release(project_id, release_id)
        if entity is None:
            raise ProjectReleaseError("Release not found")
        if actor is not None:
            project = await self._get_project(project_id)
            if project is None:
                raise ProjectReleaseError("Project not found")
            self._ensure_project_manage_access(project, actor)

        entity.status = "archived"
        entity.archived_at = datetime.utcnow()
        await self.session.commit()
        entity = await self._get_release(project_id, release_id)
        if entity is None:
            raise ProjectReleaseError("Release not found")
        return self._to_release_read(entity)

    async def replace_release_access(
        self,
        project_id: str,
        release_id: str,
        user_ids: list[str],
        cohort_codes: list[str],
        actor: User,
    ) -> ProjectReleaseRead:
        entity = await self._get_release(project_id, release_id)
        if entity is None:
            raise ProjectReleaseError("Release not found")
        project = await self._get_project(project_id)
        if project is None:
            raise ProjectReleaseError("Project not found")
        self._ensure_project_manage_access(project, actor)

        normalized_ids = list(dict.fromkeys(user_id for user_id in user_ids if user_id))
        normalized_cohorts = list(
            dict.fromkeys(
                cohort_code.strip().upper()
                for cohort_code in cohort_codes
                if isinstance(cohort_code, str) and cohort_code.strip()
            )
        )
        if normalized_ids:
            users_result = await self.session.execute(
                select(User).where(
                    User.id.in_(normalized_ids),
                    User.is_active.is_(True),
                    User.role == UserRole.PLAYER,
                )
            )
            users = users_result.scalars().all()
            resolved_ids = {user.id for user in users}
            missing_ids = [user_id for user_id in normalized_ids if user_id not in resolved_ids]
            if missing_ids:
                raise ProjectReleaseError("Some assigned users are missing or not active players")

        await self.session.execute(
            delete(ProjectReleaseAccess).where(ProjectReleaseAccess.release_id == release_id)
        )
        await self.session.execute(
            delete(ProjectReleaseCohortAccess).where(ProjectReleaseCohortAccess.release_id == release_id)
        )
        for user_id in normalized_ids:
            self.session.add(
                ProjectReleaseAccess(
                    release_id=release_id,
                    user_id=user_id,
                    granted_by_user_id=actor.id,
                )
            )
        for cohort_code in normalized_cohorts:
            self.session.add(
                ProjectReleaseCohortAccess(
                    release_id=release_id,
                    cohort_code=cohort_code,
                    granted_by_user_id=actor.id,
                )
            )

        await self.session.commit()
        entity = await self._get_release(project_id, release_id)
        if entity is None:
            raise ProjectReleaseError("Release not found")
        return self._to_release_read(entity)

    async def list_candidate_users(self, search: str | None = None, limit: int = 50) -> list[ReleaseAssignedUserRead]:
        query = (
            select(User)
            .where(User.is_active.is_(True), User.role == UserRole.PLAYER)
            .order_by(User.username.asc())
            .limit(limit)
        )
        if search:
            like = f"%{search.strip()}%"
            query = query.where(
                (User.username.ilike(like)) | (User.email.ilike(like)) | (User.full_name.ilike(like))
            )

        result = await self.session.execute(query)
        users = result.scalars().all()
        return [
            ReleaseAssignedUserRead(
                id=user.id,
                username=user.username,
                email=user.email,
                full_name=user.full_name,
            )
            for user in users
        ]

    async def get_latest_accessible_release(
        self,
        project_id: str,
        user: User,
    ) -> ProjectRelease | None:
        releases = await self.list_accessible_releases(user, project_id=project_id)
        return releases[0] if releases else None

    async def list_accessible_releases(
        self,
        user: User,
        project_id: str | None = None,
    ) -> list[ProjectRelease]:
        query = (
            select(ProjectRelease)
            .options(
                selectinload(ProjectRelease.access_entries).selectinload(ProjectReleaseAccess.user),
                selectinload(ProjectRelease.cohort_entries),
            )
            .where(
                ProjectRelease.status == "published",
                ProjectRelease.archived_at.is_(None),
            )
            .order_by(ProjectRelease.project_id.asc(), ProjectRelease.version.desc(), ProjectRelease.published_at.desc())
        )
        if project_id is not None:
            query = query.where(ProjectRelease.project_id == project_id)

        result = await self.session.execute(query)
        releases = result.scalars().unique().all()
        if user.role == UserRole.PLAYER:
            releases = [release for release in releases if self._player_has_release_access(release, user)]
        latest_by_project: dict[str, ProjectRelease] = {}
        for release in releases:
            existing = latest_by_project.get(release.project_id)
            if existing is None or release.version > existing.version:
                latest_by_project[release.project_id] = release
        ordered = list(latest_by_project.values())
        ordered.sort(key=lambda item: item.published_at, reverse=True)
        return ordered

    async def find_release_by_package_version(
        self,
        project_id: str,
        package_version: str | None,
        user: User | None = None,
    ) -> ProjectRelease | None:
        if not package_version:
            return None
        query = (
            select(ProjectRelease)
            .options(
                selectinload(ProjectRelease.access_entries).selectinload(ProjectReleaseAccess.user),
                selectinload(ProjectRelease.cohort_entries),
            )
            .where(
                ProjectRelease.project_id == project_id,
                ProjectRelease.package_version == package_version,
                ProjectRelease.status == "published",
                ProjectRelease.archived_at.is_(None),
            )
            .order_by(ProjectRelease.version.desc())
            .limit(1)
        )
        result = await self.session.execute(query)
        release = result.scalars().unique().first()
        if release is None:
            return None
        if user is not None and user.role == UserRole.PLAYER and not self._player_has_release_access(release, user):
            return None
        return release

    async def _get_project(self, project_id: str) -> Project | None:
        result = await self.session.execute(
            select(Project).where(Project.id == project_id, Project.archived_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def _resolve_graph(self, project_id: str, graph_id: str | None) -> ScenarioGraph | None:
        query = (
            select(ScenarioGraph)
            .where(
                ScenarioGraph.project_id == project_id,
                ScenarioGraph.archived_at.is_(None),
            )
            .order_by(ScenarioGraph.updated_at.desc(), ScenarioGraph.created_at.desc())
            .limit(1)
        )
        if graph_id is not None:
            query = query.where(ScenarioGraph.id == graph_id)
        result = await self.session.execute(query)
        return result.scalars().first()

    async def _get_latest_active_release(self, project_id: str) -> ProjectRelease | None:
        result = await self.session.execute(
            select(ProjectRelease)
            .where(
                ProjectRelease.project_id == project_id,
                ProjectRelease.status == "published",
                ProjectRelease.archived_at.is_(None),
            )
            .order_by(ProjectRelease.version.desc(), ProjectRelease.published_at.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def _get_next_version(self, project_id: str) -> int:
        result = await self.session.execute(
            select(func.max(ProjectRelease.version)).where(ProjectRelease.project_id == project_id)
        )
        return int(result.scalar() or 0) + 1

    async def _get_release(self, project_id: str, release_id: str) -> ProjectRelease | None:
        result = await self.session.execute(
            select(ProjectRelease)
            .options(
                selectinload(ProjectRelease.access_entries).selectinload(ProjectReleaseAccess.user),
                selectinload(ProjectRelease.cohort_entries),
            )
            .where(ProjectRelease.project_id == project_id, ProjectRelease.id == release_id)
        )
        return result.scalars().unique().one_or_none()

    async def _list_release_access_entries(self, release_id: str) -> list[ProjectReleaseAccess]:
        result = await self.session.execute(
            select(ProjectReleaseAccess).where(ProjectReleaseAccess.release_id == release_id)
        )
        return result.scalars().all()

    async def _list_release_cohort_entries(self, release_id: str) -> list[ProjectReleaseCohortAccess]:
        result = await self.session.execute(
            select(ProjectReleaseCohortAccess).where(ProjectReleaseCohortAccess.release_id == release_id)
        )
        return result.scalars().all()

    @staticmethod
    def _dump_model(model) -> dict:
        if hasattr(model, "model_dump"):
            return model.model_dump(mode="json")
        return model.dict()

    def _build_manifest(self, export_payload: dict) -> PlayableProjectRead:
        serialized = json.dumps(export_payload, ensure_ascii=False, sort_keys=True, default=str)
        package_version = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]

        project_payload = export_payload.get("project") or {}
        graph_payload = export_payload.get("graph") or {}
        scenes = graph_payload.get("scenes") or []
        edges = graph_payload.get("edges") or []

        updated_at_raw = project_payload.get("updated_at") or graph_payload.get("updated_at") or datetime.utcnow().isoformat()

        return PlayableProjectRead(
            project_id=project_payload["id"],
            project_name=project_payload["name"],
            project_description=project_payload.get("description"),
            graph_id=graph_payload["id"],
            graph_title=graph_payload.get("title") or project_payload["name"],
            graph_description=graph_payload.get("description"),
            root_scene_id=graph_payload.get("root_scene_id"),
            scene_count=len(scenes),
            choice_count=len(edges),
            package_version=package_version,
            updated_at=updated_at_raw,
        )

    @staticmethod
    def _to_release_read(entity: ProjectRelease) -> ProjectReleaseRead:
        manifest = PlayableProjectRead.model_validate(entity.manifest_payload)
        assigned_users = sorted(
            (
                ReleaseAssignedUserRead(
                    id=entry.user.id,
                    username=entry.user.username,
                    email=entry.user.email,
                    full_name=entry.user.full_name,
                )
                for entry in entity.access_entries
                if entry.user is not None
            ),
            key=lambda item: item.username.lower(),
        )
        assigned_cohorts = sorted(
            {
                entry.cohort_code
                for entry in entity.cohort_entries
                if isinstance(entry.cohort_code, str) and entry.cohort_code
            }
        )
        return ProjectReleaseRead(
            id=entity.id,
            project_id=entity.project_id,
            graph_id=entity.graph_id,
            version=entity.version,
            status=entity.status,
            package_version=entity.package_version,
            notes=entity.notes,
            published_at=entity.published_at,
            archived_at=entity.archived_at,
            manifest=manifest,
            assigned_users=assigned_users,
            assigned_cohorts=assigned_cohorts,
        )

    @staticmethod
    def _ensure_project_manage_access(project: Project, actor: User) -> None:
        if actor.role == UserRole.ADMIN:
            return
        if project.owner_id == actor.id:
            return
        raise ProjectReleaseError("Project not found")

    @staticmethod
    def _player_has_release_access(release: ProjectRelease, user: User) -> bool:
        if any(entry.user_id == user.id for entry in release.access_entries):
            return True
        cohort_code = (user.cohort_code or "").strip().upper()
        if cohort_code and any(entry.cohort_code == cohort_code for entry in release.cohort_entries):
            return True
        return False
