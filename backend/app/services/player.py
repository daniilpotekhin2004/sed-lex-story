from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import PlayerRun, PlayerRunEvent, ScenarioGraph, User
from app.schemas.export import ProjectExport
from app.schemas.player import (
    PlayableProjectRead,
    PlayerOwnStatsRead,
    PlayerPackageRead,
    PlayerProjectStatsRead,
    PlayerResumeRead,
    PlayerRunSyncRequest,
    PlayerRunSyncResponse,
)
from app.services.project_releases import ProjectReleaseService


class PlayerRuntimeError(Exception):
    pass


class PlayerService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.release_service = ProjectReleaseService(session)

    async def list_catalog(self, user: User) -> list[PlayableProjectRead]:
        releases = await self.release_service.list_accessible_releases(user)
        items = [self._manifest_from_release(release) for release in releases]
        items.sort(key=lambda item: item.updated_at, reverse=True)
        return items

    async def get_package(
        self,
        project_id: str,
        user: User,
        package_version: str | None = None,
    ) -> Optional[PlayerPackageRead]:
        if package_version:
            release = await self.release_service.find_release_by_package_version(project_id, package_version, user=user)
        else:
            release = await self.release_service.get_latest_accessible_release(project_id, user)
        if release is None:
            return None
        return self._package_from_release(release)

    async def sync_run(
        self,
        project_id: str,
        user: User,
        payload: PlayerRunSyncRequest,
    ) -> PlayerRunSyncResponse:
        release = await self.release_service.find_release_by_package_version(
            project_id,
            payload.package_version,
            user=user,
        )
        manifest: PlayableProjectRead | None = None
        if release is not None:
            manifest = self._manifest_from_release(release)
            if payload.graph_id != manifest.graph_id:
                raise PlayerRuntimeError("Graph does not match published release package")
        else:
            graph = await self._get_graph(payload.graph_id, project_id)
            if graph is None:
                raise PlayerRuntimeError("Graph not found for project")

        run = await self.session.get(PlayerRun, payload.run_id)
        if run is not None and run.user_id != user.id:
            raise PlayerRuntimeError("Run belongs to another user")

        package_version = payload.package_version or (manifest.package_version if manifest is not None else None)

        if run is None:
            started_at = payload.events[0].timestamp if payload.events else datetime.utcnow()
            run = PlayerRun(
                id=payload.run_id,
                project_id=project_id,
                graph_id=payload.graph_id,
                user_id=user.id,
                package_version=package_version,
                status=payload.status,
                started_at=started_at,
                last_node_id=payload.current_node_id,
            )
            self.session.add(run)
        else:
            run.graph_id = payload.graph_id
            run.package_version = package_version or run.package_version
            run.status = payload.status or run.status
            if payload.current_node_id:
                run.last_node_id = payload.current_node_id

        if payload.current_node_id is None:
            latest_node = self._extract_latest_node(payload)
            if latest_node:
                run.last_node_id = latest_node

        event_ids = [event.id for event in payload.events]
        existing_ids: set[str] = set()
        if event_ids:
            result = await self.session.execute(select(PlayerRunEvent.id).where(PlayerRunEvent.id.in_(event_ids)))
            existing_ids = set(result.scalars().all())

        accepted_count = 0
        duplicate_count = 0
        completion_timestamp: datetime | None = None

        for event in payload.events:
            if event.id in existing_ids:
                duplicate_count += 1
                continue
            self.session.add(
                PlayerRunEvent(
                    id=event.id,
                    run_id=payload.run_id,
                    project_id=project_id,
                    user_id=user.id,
                    event_type=event.type,
                    event_timestamp=event.timestamp,
                    payload=event.payload or {},
                )
            )
            accepted_count += 1
            if event.type == "session_completed":
                completion_timestamp = event.timestamp

        if payload.status == "completed" and completion_timestamp is None:
            completion_timestamp = payload.events[-1].timestamp if payload.events else datetime.utcnow()

        if completion_timestamp is not None:
            run.status = "completed"
            run.completed_at = completion_timestamp

        run.last_synced_at = datetime.utcnow()
        await self.session.commit()

        return PlayerRunSyncResponse(
            run_id=run.id,
            accepted_count=accepted_count,
            duplicate_count=duplicate_count,
            status=run.status,
            last_synced_at=run.last_synced_at,
        )

    async def get_project_stats(self, project_id: str, user: User) -> Optional[PlayerProjectStatsRead]:
        package = await self.get_package(project_id, user)
        if package is None:
            return None

        runs_result = await self.session.execute(select(PlayerRun).where(PlayerRun.project_id == project_id))
        runs = runs_result.scalars().all()

        events_result = await self.session.execute(select(PlayerRunEvent).where(PlayerRunEvent.project_id == project_id))
        events = events_result.scalars().all()

        edge_map: dict[str, str] = {}
        for edge in package.export.graph.edges:
            label = edge.choice_label or ""
            if not label and isinstance(edge.edge_metadata, dict):
                raw_value = edge.edge_metadata.get("choice_value")
                if isinstance(raw_value, str):
                    label = raw_value
            edge_map[edge.id] = label or edge.id

        choice_counts: Counter[str] = Counter()
        for event in events:
            if event.event_type != "choice_selected":
                continue
            event_payload = event.payload or {}
            choice_id = event_payload.get("choice_id")
            if isinstance(choice_id, str) and choice_id:
                choice_counts[choice_id] += 1

        choice_items = [
            {
                "choice_id": choice_id,
                "label": edge_map.get(choice_id) or choice_id,
                "selection_count": count,
            }
            for choice_id, count in choice_counts.most_common()
        ]

        total_runs = len(runs)
        completed_runs = sum(1 for run in runs if run.completed_at is not None or run.status == "completed")
        unique_players = len({run.user_id for run in runs if run.user_id})

        my_runs = [run for run in runs if run.user_id == user.id]
        my_runs.sort(key=lambda run: run.last_synced_at or run.started_at or datetime.min)
        last_run = my_runs[-1] if my_runs else None

        return PlayerProjectStatsRead(
            project_id=project_id,
            graph_id=package.manifest.graph_id,
            package_version=package.manifest.package_version,
            updated_at=package.manifest.updated_at,
            total_runs=total_runs,
            completed_runs=completed_runs,
            unique_players=unique_players,
            completion_rate=(completed_runs / total_runs) if total_runs else 0.0,
            choices=choice_items,
            mine=PlayerOwnStatsRead(
                total_runs=len(my_runs),
                completed_runs=sum(1 for run in my_runs if run.completed_at is not None or run.status == "completed"),
                last_run_id=last_run.id if last_run else None,
                last_completed_at=last_run.completed_at if last_run else None,
                last_synced_at=last_run.last_synced_at if last_run else None,
                current_node_id=last_run.last_node_id if last_run else None,
            ),
        )

    async def get_resume(self, project_id: str, user: User) -> PlayerResumeRead:
        run = await self._get_latest_active_run(project_id, user)
        if run is None:
            return PlayerResumeRead()

        package = await self.get_package(project_id, user, package_version=run.package_version)
        if package is None:
            return PlayerResumeRead()

        events = await self._get_run_events(run.id)
        scene_history = self._extract_scene_history(events, current_node_id=run.last_node_id)
        session_values = self._extract_session_values(package.export, events)

        return PlayerResumeRead(
            available=True,
            run_id=run.id,
            graph_id=run.graph_id,
            package_version=run.package_version,
            current_node_id=run.last_node_id,
            status=run.status,
            started_at=run.started_at,
            last_synced_at=run.last_synced_at,
            scene_history=scene_history,
            session_values=session_values,
        )

    async def _get_graph(self, graph_id: str, project_id: str) -> ScenarioGraph | None:
        result = await self.session.execute(
            select(ScenarioGraph).where(
                ScenarioGraph.id == graph_id,
                ScenarioGraph.project_id == project_id,
                ScenarioGraph.archived_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def _get_latest_active_run(self, project_id: str, user: User) -> PlayerRun | None:
        result = await self.session.execute(
            select(PlayerRun)
            .where(
                PlayerRun.project_id == project_id,
                PlayerRun.user_id == user.id,
                PlayerRun.status == "active",
            )
            .order_by(PlayerRun.last_synced_at.desc(), PlayerRun.started_at.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def _get_run_events(self, run_id: str) -> list[PlayerRunEvent]:
        result = await self.session.execute(
            select(PlayerRunEvent)
            .where(PlayerRunEvent.run_id == run_id)
            .order_by(PlayerRunEvent.event_timestamp.asc(), PlayerRunEvent.created_at.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    def _manifest_from_release(release) -> PlayableProjectRead:
        return PlayableProjectRead.model_validate(release.manifest_payload)

    @staticmethod
    def _package_from_release(release) -> PlayerPackageRead:
        return PlayerPackageRead(
            manifest=PlayableProjectRead.model_validate(release.manifest_payload),
            export=ProjectExport.model_validate(release.export_payload),
        )

    @staticmethod
    def _extract_scene_history(events: list[PlayerRunEvent], current_node_id: str | None = None) -> list[str]:
        history: list[str] = []
        seen_any = False
        for event in events:
            if event.event_type != "node_entered":
                continue
            node_id = (event.payload or {}).get("node_id")
            if not isinstance(node_id, str) or not node_id:
                continue
            if history and history[-1] == node_id:
                continue
            history.append(node_id)
            seen_any = True

        if not seen_any and current_node_id:
            return [current_node_id]
        if current_node_id and (not history or history[-1] != current_node_id):
            history.append(current_node_id)
        return history

    @staticmethod
    def _extract_session_values(exported: ProjectExport, events: list[PlayerRunEvent]) -> dict[str, str]:
        scene_choice_keys: dict[str, str] = {}
        for scene in exported.graph.scenes:
            context = scene.context or {}
            sequence = context.get("sequence") if isinstance(context, dict) else None
            choice_key = sequence.get("choice_key") if isinstance(sequence, dict) else None
            if isinstance(choice_key, str) and choice_key.strip():
                scene_choice_keys[scene.id] = choice_key.strip()

        session_values: dict[str, str] = {}
        for event in events:
            if event.event_type != "choice_selected":
                continue
            payload = event.payload or {}
            value = payload.get("value")
            if value is None:
                continue
            value_text = value if isinstance(value, str) else str(value)
            session_values["last_choice"] = value_text
            from_node_id = payload.get("from_node_id")
            if isinstance(from_node_id, str) and from_node_id in scene_choice_keys:
                session_values[scene_choice_keys[from_node_id]] = value_text
        return session_values

    @staticmethod
    def _extract_latest_node(payload: PlayerRunSyncRequest) -> str | None:
        for event in reversed(payload.events):
            node_id = (event.payload or {}).get("node_id")
            if isinstance(node_id, str) and node_id:
                return node_id
        return None
