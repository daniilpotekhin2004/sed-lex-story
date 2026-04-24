from __future__ import annotations

import json
import re
from collections import defaultdict, deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.config import get_settings
from app.domain.models import (
    Artifact,
    CharacterPreset,
    DocumentTemplate,
    GenerationJob,
    GenerationStatus,
    Location,
    Project,
    RoleAuditEvent,
    ScenarioGraph,
    User,
    UserRole,
)
from app.schemas.admin import (
    AdminOverviewResponse,
    AdminUserListResponse,
    AdminUserSummary,
    AssetListItem,
    CohortUpdateRequest,
    CohortUpdateResult,
    ComfyOverviewResponse,
    ComfySpendByUser,
    ErrorFeedItem,
    ErrorFeedResponse,
    QuestListItem,
    RoleAggregateStats,
    RoleAuditListResponse,
    RoleAuditRead,
    RoleBulkUpdateRequest,
    RoleBulkUpdateResponse,
    RoleUpdateRequest,
    RoleUpdateResult,
    UserAssetStats,
    UserComfyStats,
    UserQuestStats,
    UserStatsResponse,
    UserTimeStats,
    WeeklyMetric,
)


def _enum_role_value(role: UserRole | str) -> str:
    return role.value if isinstance(role, UserRole) else str(role)


def _week_bucket(value: datetime) -> str:
    # ISO week start (Monday) as YYYY-MM-DD
    monday = (value - timedelta(days=value.weekday())).date()
    return monday.isoformat()


def _group_weekly(points: Iterable[tuple[datetime, float]]) -> list[WeeklyMetric]:
    buckets: dict[str, float] = defaultdict(float)
    for created_at, amount in points:
        buckets[_week_bucket(created_at)] += amount
    return [WeeklyMetric(week=week, value=value) for week, value in sorted(buckets.items())]


def _duration_seconds(started_at: Optional[datetime], finished_at: Optional[datetime]) -> float:
    if not started_at or not finished_at:
        return 0.0
    seconds = (finished_at - started_at).total_seconds()
    return seconds if seconds > 0 else 0.0


def _normalize_cohort_code(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    return normalized or None


def _tail_lines(path: Path, limit: int) -> list[str]:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as fp:
            return list(deque(fp, maxlen=limit))
    except Exception:
        return []


class AdminConsoleService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()

    def _parse_role(self, raw: str) -> UserRole:
        normalized = (raw or "").strip().lower()
        for role in UserRole:
            if role.value == normalized:
                return role
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown role '{raw}'. Allowed: admin, author, player.",
        )

    def _apply_date_bounds(self, stmt: Select, model_created_at, from_date: datetime | None, to_date: datetime | None):
        if from_date:
            stmt = stmt.where(model_created_at >= from_date)
        if to_date:
            stmt = stmt.where(model_created_at <= to_date)
        return stmt

    async def _asset_counts_by_user(
        self,
        user_ids: list[str],
        *,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> dict[str, int]:
        if not user_ids:
            return {}
        totals: dict[str, int] = defaultdict(int)
        specs = [
            (CharacterPreset, CharacterPreset.author_id),
            (Location, Location.owner_id),
            (Artifact, Artifact.owner_id),
            (DocumentTemplate, DocumentTemplate.owner_id),
        ]
        for model, owner_field in specs:
            stmt = select(owner_field, func.count(model.id)).where(owner_field.in_(user_ids))
            stmt = self._apply_date_bounds(stmt, model.created_at, from_date, to_date)
            stmt = stmt.group_by(owner_field)
            rows = (await self.session.execute(stmt)).all()
            for user_id, count in rows:
                if user_id:
                    totals[user_id] += int(count or 0)
        return totals

    async def _quest_counts_by_user(
        self,
        user_ids: list[str],
        *,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> dict[str, int]:
        if not user_ids:
            return {}
        stmt = (
            select(Project.owner_id, func.count(ScenarioGraph.id))
            .join(ScenarioGraph, ScenarioGraph.project_id == Project.id)
            .where(Project.owner_id.in_(user_ids))
            .group_by(Project.owner_id)
        )
        stmt = self._apply_date_bounds(stmt, ScenarioGraph.created_at, from_date, to_date)
        rows = (await self.session.execute(stmt)).all()
        return {user_id: int(count or 0) for user_id, count in rows if user_id}

    async def _completed_jobs_by_user(
        self,
        user_ids: list[str],
        *,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> dict[str, int]:
        if not user_ids:
            return {}
        stmt = (
            select(GenerationJob.user_id, func.count(GenerationJob.id))
            .where(
                GenerationJob.user_id.in_(user_ids),
                GenerationJob.status == GenerationStatus.DONE,
            )
            .group_by(GenerationJob.user_id)
        )
        stmt = self._apply_date_bounds(stmt, GenerationJob.created_at, from_date, to_date)
        rows = (await self.session.execute(stmt)).all()
        return {user_id: int(count or 0) for user_id, count in rows if user_id}

    async def _active_user_ids(
        self,
        *,
        from_date: datetime | None,
        to_date: datetime | None,
    ) -> set[str]:
        active: set[str] = set()
        specs = [
            (CharacterPreset, CharacterPreset.author_id),
            (Location, Location.owner_id),
            (Artifact, Artifact.owner_id),
            (DocumentTemplate, DocumentTemplate.owner_id),
        ]
        for model, owner_field in specs:
            stmt = select(owner_field).where(owner_field.is_not(None)).distinct()
            stmt = self._apply_date_bounds(stmt, model.created_at, from_date, to_date)
            rows = (await self.session.execute(stmt)).all()
            active.update(str(user_id) for (user_id,) in rows if user_id)
        quests_stmt = (
            select(Project.owner_id)
            .join(ScenarioGraph, ScenarioGraph.project_id == Project.id)
            .where(Project.owner_id.is_not(None))
            .distinct()
        )
        quests_stmt = self._apply_date_bounds(quests_stmt, ScenarioGraph.created_at, from_date, to_date)
        q_rows = (await self.session.execute(quests_stmt)).all()
        active.update(str(user_id) for (user_id,) in q_rows if user_id)
        return active

    async def list_users(
        self,
        *,
        search: str | None,
        role: str | None,
        registered_from: datetime | None,
        registered_to: datetime | None,
        activity_from: datetime | None,
        activity_to: datetime | None,
        page: int,
        page_size: int,
    ) -> AdminUserListResponse:
        conditions = []
        if search:
            pattern = f"%{search.lower()}%"
            conditions.append(
                or_(
                    func.lower(User.username).like(pattern),
                    func.lower(User.email).like(pattern),
                    func.lower(func.coalesce(User.full_name, "")).like(pattern),
                    func.lower(User.id).like(pattern),
                )
            )
        if role:
            selected_role = self._parse_role(role)
            conditions.append(User.role == selected_role)
        if registered_from:
            conditions.append(User.created_at >= registered_from)
        if registered_to:
            conditions.append(User.created_at <= registered_to)
        if activity_from or activity_to:
            active_ids = await self._active_user_ids(from_date=activity_from, to_date=activity_to)
            if active_ids:
                conditions.append(User.id.in_(sorted(active_ids)))
            else:
                return AdminUserListResponse(
                    items=[],
                    total=0,
                    page=page,
                    page_size=page_size,
                    grouped_counts={},
                )

        base_stmt = select(User)
        if conditions:
            base_stmt = base_stmt.where(*conditions)

        total_stmt = select(func.count()).select_from(base_stmt.subquery())
        total = int((await self.session.execute(total_stmt)).scalar() or 0)

        grouped_stmt = select(User.role, func.count(User.id))
        if conditions:
            grouped_stmt = grouped_stmt.where(*conditions)
        grouped_stmt = grouped_stmt.group_by(User.role)
        grouped_rows = (await self.session.execute(grouped_stmt)).all()
        grouped_counts = {_enum_role_value(role_value): int(count) for role_value, count in grouped_rows}

        users_stmt = (
            base_stmt.order_by(User.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        users = list((await self.session.execute(users_stmt)).scalars().all())
        user_ids = [user.id for user in users]

        assets_by_user = await self._asset_counts_by_user(user_ids)
        quests_by_user = await self._quest_counts_by_user(user_ids)
        jobs_by_user = await self._completed_jobs_by_user(user_ids)

        items = [
            AdminUserSummary(
                id=user.id,
                username=user.username,
                email=user.email,
                full_name=user.full_name,
                cohort_code=user.cohort_code,
                role=_enum_role_value(user.role),
                is_active=user.is_active,
                created_at=user.created_at,
                assets_total=assets_by_user.get(user.id, 0),
                quests_total=quests_by_user.get(user.id, 0),
                completed_jobs_total=jobs_by_user.get(user.id, 0),
                comfy_units_total=float(jobs_by_user.get(user.id, 0)),
            )
            for user in users
        ]
        return AdminUserListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            grouped_counts=grouped_counts,
        )

    async def update_user_role(
        self,
        *,
        actor: User,
        user_id: str,
        payload: RoleUpdateRequest,
    ) -> RoleUpdateResult:
        target_role = self._parse_role(payload.role)
        if target_role == UserRole.ADMIN and not payload.confirm_assign_admin:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Confirm admin assignment with confirm_assign_admin=true.",
            )

        user = await self.session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        if actor.id == user.id and actor.role == UserRole.ADMIN and target_role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Admin self-demotion is blocked.",
            )

        previous_role = _enum_role_value(user.role)
        changed = previous_role != target_role.value
        if changed:
            user.role = target_role
            self.session.add(
                RoleAuditEvent(
                    user_id=user.id,
                    actor_user_id=actor.id,
                    from_role=previous_role,
                    to_role=target_role.value,
                    reason=payload.reason.strip() if payload.reason else None,
                )
            )
            await self.session.commit()

        return RoleUpdateResult(
            user_id=user.id,
            previous_role=previous_role,
            new_role=target_role.value,
            changed=changed,
        )

    async def update_user_cohort(
        self,
        *,
        user_id: str,
        payload: CohortUpdateRequest,
    ) -> CohortUpdateResult:
        user = await self.session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        previous = user.cohort_code
        next_value = _normalize_cohort_code(payload.cohort_code)
        changed = previous != next_value
        if changed:
            user.cohort_code = next_value
            await self.session.commit()

        return CohortUpdateResult(
            user_id=user.id,
            previous_cohort_code=previous,
            cohort_code=next_value,
            changed=changed,
        )

    async def bulk_update_roles(self, *, actor: User, payload: RoleBulkUpdateRequest) -> RoleBulkUpdateResponse:
        target_role = self._parse_role(payload.role)
        if target_role == UserRole.ADMIN and not payload.confirm_assign_admin:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Confirm admin assignment with confirm_assign_admin=true.",
            )

        unique_ids = list(dict.fromkeys([user_id for user_id in payload.user_ids if user_id]))
        if not unique_ids:
            return RoleBulkUpdateResponse(updated=0, skipped=0, batch_id=None, results=[])

        users = list((await self.session.execute(select(User).where(User.id.in_(unique_ids)))).scalars().all())
        by_id = {user.id: user for user in users}
        batch_id = uuid4().hex
        updated = 0
        skipped = 0
        results: list[RoleUpdateResult] = []
        for user_id in unique_ids:
            user = by_id.get(user_id)
            if user is None:
                skipped += 1
                continue
            previous_role = _enum_role_value(user.role)
            if actor.id == user.id and actor.role == UserRole.ADMIN and target_role != UserRole.ADMIN:
                skipped += 1
                results.append(
                    RoleUpdateResult(
                        user_id=user.id,
                        previous_role=previous_role,
                        new_role=previous_role,
                        changed=False,
                    )
                )
                continue
            if previous_role == target_role.value:
                skipped += 1
                results.append(
                    RoleUpdateResult(
                        user_id=user.id,
                        previous_role=previous_role,
                        new_role=target_role.value,
                        changed=False,
                    )
                )
                continue
            user.role = target_role
            updated += 1
            results.append(
                RoleUpdateResult(
                    user_id=user.id,
                    previous_role=previous_role,
                    new_role=target_role.value,
                    changed=True,
                )
            )
            self.session.add(
                RoleAuditEvent(
                    user_id=user.id,
                    actor_user_id=actor.id,
                    from_role=previous_role,
                    to_role=target_role.value,
                    reason=payload.reason.strip() if payload.reason else None,
                    batch_id=batch_id,
                )
            )

        await self.session.commit()
        return RoleBulkUpdateResponse(
            updated=updated,
            skipped=skipped,
            batch_id=batch_id if updated else None,
            results=results,
        )

    async def _asset_items(self, user_id: str) -> list[AssetListItem]:
        items: list[AssetListItem] = []
        rows = (await self.session.execute(select(CharacterPreset).where(CharacterPreset.author_id == user_id))).scalars().all()
        items.extend(
            AssetListItem(
                id=item.id,
                type="character",
                name=item.name,
                project_id=item.project_id,
                created_at=item.created_at,
            )
            for item in rows
        )
        rows = (await self.session.execute(select(Location).where(Location.owner_id == user_id))).scalars().all()
        items.extend(
            AssetListItem(
                id=item.id,
                type="location",
                name=item.name,
                project_id=item.project_id,
                created_at=item.created_at,
            )
            for item in rows
        )
        rows = (await self.session.execute(select(Artifact).where(Artifact.owner_id == user_id))).scalars().all()
        items.extend(
            AssetListItem(
                id=item.id,
                type="artifact",
                name=item.name,
                project_id=item.project_id,
                created_at=item.created_at,
            )
            for item in rows
        )
        rows = (await self.session.execute(select(DocumentTemplate).where(DocumentTemplate.owner_id == user_id))).scalars().all()
        items.extend(
            AssetListItem(
                id=item.id,
                type="document_template",
                name=item.name,
                project_id=item.project_id,
                created_at=item.created_at,
            )
            for item in rows
        )
        items.sort(key=lambda item: item.created_at, reverse=True)
        return items

    async def _quest_items(self, user_id: str) -> list[QuestListItem]:
        stmt = (
            select(ScenarioGraph, Project.name)
            .join(Project, Project.id == ScenarioGraph.project_id)
            .where(Project.owner_id == user_id)
            .order_by(ScenarioGraph.created_at.desc())
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            QuestListItem(
                id=graph.id,
                title=graph.title,
                project_id=graph.project_id,
                project_name=project_name,
                created_at=graph.created_at,
            )
            for graph, project_name in rows
        ]

    async def _job_time_rows(self, user_id: str) -> list[tuple[datetime, float]]:
        stmt = select(
            GenerationJob.created_at,
            GenerationJob.started_at,
            GenerationJob.finished_at,
        ).where(
            GenerationJob.user_id == user_id,
            GenerationJob.status == GenerationStatus.DONE,
        )
        rows = (await self.session.execute(stmt)).all()
        points: list[tuple[datetime, float]] = []
        for created_at, started_at, finished_at in rows:
            points.append((created_at, _duration_seconds(started_at, finished_at)))
        return points

    async def _job_count(
        self,
        user_id: str,
        *,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> int:
        stmt = select(func.count(GenerationJob.id)).where(
            GenerationJob.user_id == user_id,
            GenerationJob.status == GenerationStatus.DONE,
        )
        stmt = self._apply_date_bounds(stmt, GenerationJob.created_at, from_date, to_date)
        return int((await self.session.execute(stmt)).scalar() or 0)

    async def get_user_stats(
        self,
        *,
        user: User,
        period_from: datetime | None = None,
        period_to: datetime | None = None,
        include_comfy: bool = True,
        minimal: bool = False,
    ) -> UserStatsResponse:
        assets = await self._asset_items(user.id)
        assets_by_type: dict[str, int] = defaultdict(int)
        asset_points: list[tuple[datetime, float]] = []
        for item in assets:
            assets_by_type[item.type] += 1
            asset_points.append((item.created_at, 1.0))
        asset_stats = UserAssetStats(
            total=len(assets),
            by_type=dict(sorted(assets_by_type.items())),
            weekly=_group_weekly(asset_points),
            items=assets[: (30 if minimal else 120)],
        )

        quests = await self._quest_items(user.id)
        quest_points = [(item.created_at, 1.0) for item in quests]
        quest_stats = UserQuestStats(
            total=len(quests),
            weekly=_group_weekly(quest_points),
            items=quests[: (20 if minimal else 80)],
        )

        time_points = await self._job_time_rows(user.id)
        total_seconds = sum(amount for _, amount in time_points)
        time_stats = UserTimeStats(
            total_seconds=round(total_seconds, 2),
            total_hours=round(total_seconds / 3600.0, 2),
            completed_jobs_total=len(time_points),
            weekly_seconds=_group_weekly(time_points),
        )

        comfy_stats: UserComfyStats | None = None
        if include_comfy:
            units_total = float(await self._job_count(user.id))
            units_period = float(
                await self._job_count(
                    user.id,
                    from_date=period_from,
                    to_date=period_to,
                )
            )
            cost_per_unit = (
                float(self.settings.comfy_api_cost_per_job_usd)
                if self.settings.comfy_api_cost_per_job_usd and self.settings.comfy_api_cost_per_job_usd > 0
                else None
            )
            spend_total = units_total * cost_per_unit if cost_per_unit is not None else None
            spend_period = units_period * cost_per_unit if cost_per_unit is not None else None
            balance = self.settings.comfy_api_balance_usd
            remaining = (balance - spend_total) if (balance is not None and spend_total is not None) else None
            comfy_stats = UserComfyStats(
                units_total=units_total,
                units_period=units_period,
                cost_per_unit_usd=cost_per_unit,
                estimated_spend_total_usd=round(spend_total, 4) if spend_total is not None else None,
                estimated_spend_period_usd=round(spend_period, 4) if spend_period is not None else None,
                configured_balance_usd=balance,
                estimated_remaining_balance_usd=round(remaining, 4) if remaining is not None else None,
                is_estimated=True,
            )

        summary = AdminUserSummary(
            id=user.id,
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            cohort_code=user.cohort_code,
            role=_enum_role_value(user.role),
            is_active=user.is_active,
            created_at=user.created_at,
            assets_total=asset_stats.total,
            quests_total=quest_stats.total,
            completed_jobs_total=time_stats.completed_jobs_total,
            comfy_units_total=comfy_stats.units_total if comfy_stats else 0.0,
        )

        return UserStatsResponse(
            user=summary,
            assets=asset_stats,
            time=time_stats,
            quests=quest_stats,
            comfy=comfy_stats,
        )

    async def get_overview(self) -> AdminOverviewResponse:
        users = list((await self.session.execute(select(User))).scalars().all())
        user_ids = [user.id for user in users]
        role_by_user = {user.id: _enum_role_value(user.role) for user in users}

        assets_by_user = await self._asset_counts_by_user(user_ids)
        quests_by_user = await self._quest_counts_by_user(user_ids)
        jobs_by_user = await self._completed_jobs_by_user(user_ids)

        time_rows = (
            await self.session.execute(
                select(
                    GenerationJob.user_id,
                    GenerationJob.started_at,
                    GenerationJob.finished_at,
                ).where(
                    GenerationJob.status == GenerationStatus.DONE,
                    GenerationJob.user_id.is_not(None),
                )
            )
        ).all()
        time_seconds_by_user: dict[str, float] = defaultdict(float)
        for user_id, started_at, finished_at in time_rows:
            if user_id:
                time_seconds_by_user[user_id] += _duration_seconds(started_at, finished_at)

        users_by_role: dict[str, int] = defaultdict(int)
        for user in users:
            users_by_role[_enum_role_value(user.role)] += 1

        cost_per_unit = (
            float(self.settings.comfy_api_cost_per_job_usd)
            if self.settings.comfy_api_cost_per_job_usd and self.settings.comfy_api_cost_per_job_usd > 0
            else None
        )
        aggregates_by_role: dict[str, RoleAggregateStats] = {}
        for role in [UserRole.ADMIN.value, UserRole.AUTHOR.value, UserRole.PLAYER.value]:
            aggregates_by_role[role] = RoleAggregateStats()

        for user_id, role in role_by_user.items():
            target = aggregates_by_role.setdefault(role, RoleAggregateStats())
            target.users += 1
            target.assets_total += assets_by_user.get(user_id, 0)
            target.quests_total += quests_by_user.get(user_id, 0)
            target.time_seconds_total += round(time_seconds_by_user.get(user_id, 0.0), 2)
            units = float(jobs_by_user.get(user_id, 0))
            target.comfy_units_total += units

        if cost_per_unit is not None:
            for role_stats in aggregates_by_role.values():
                role_stats.estimated_spend_usd_total = round(role_stats.comfy_units_total * cost_per_unit, 4)

        return AdminOverviewResponse(
            users_total=len(users),
            users_by_role=dict(sorted(users_by_role.items())),
            aggregates_by_role=aggregates_by_role,
            generated_at=datetime.utcnow(),
        )

    async def get_comfy_overview(self) -> ComfyOverviewResponse:
        stmt = (
            select(User.id, User.username, func.count(GenerationJob.id))
            .join(GenerationJob, GenerationJob.user_id == User.id)
            .where(GenerationJob.status == GenerationStatus.DONE)
            .group_by(User.id, User.username)
            .order_by(func.count(GenerationJob.id).desc())
        )
        rows = (await self.session.execute(stmt)).all()
        cost_per_unit = (
            float(self.settings.comfy_api_cost_per_job_usd)
            if self.settings.comfy_api_cost_per_job_usd and self.settings.comfy_api_cost_per_job_usd > 0
            else None
        )
        users: list[ComfySpendByUser] = []
        total_units = 0.0
        for user_id, username, count in rows:
            units = float(count or 0)
            total_units += units
            users.append(
                ComfySpendByUser(
                    user_id=user_id,
                    username=username,
                    units=units,
                    estimated_spend_usd=round(units * cost_per_unit, 4) if cost_per_unit is not None else None,
                )
            )
        spend_total = total_units * cost_per_unit if cost_per_unit is not None else None
        balance = self.settings.comfy_api_balance_usd
        remaining = (balance - spend_total) if (balance is not None and spend_total is not None) else None
        return ComfyOverviewResponse(
            total_units=total_units,
            cost_per_unit_usd=cost_per_unit,
            estimated_spend_total_usd=round(spend_total, 4) if spend_total is not None else None,
            configured_balance_usd=balance,
            estimated_remaining_balance_usd=round(remaining, 4) if remaining is not None else None,
            users=users,
            is_estimated=True,
        )

    async def list_role_audit(self, *, page: int, page_size: int) -> RoleAuditListResponse:
        subject = aliased(User)
        actor = aliased(User)
        base = (
            select(
                RoleAuditEvent,
                subject.username.label("subject_username"),
                actor.username.label("actor_username"),
            )
            .join(subject, subject.id == RoleAuditEvent.user_id)
            .join(actor, actor.id == RoleAuditEvent.actor_user_id)
        )
        total = int((await self.session.execute(select(func.count()).select_from(RoleAuditEvent))).scalar() or 0)
        stmt = base.order_by(RoleAuditEvent.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        rows = (await self.session.execute(stmt)).all()
        items = [
            RoleAuditRead(
                id=event.id,
                user_id=event.user_id,
                actor_user_id=event.actor_user_id,
                from_role=event.from_role,
                to_role=event.to_role,
                reason=event.reason,
                batch_id=event.batch_id,
                created_at=event.created_at,
                user_username=subject_username,
                actor_username=actor_username,
            )
            for event, subject_username, actor_username in rows
        ]
        return RoleAuditListResponse(items=items, total=total, page=page, page_size=page_size)

    def _discover_error_sources(self) -> list[Path]:
        backend_root = Path(__file__).resolve().parents[2]
        project_root = backend_root.parent
        sources: list[Path] = []
        explicit = self.settings.ai_sequence_debug_log_path
        if explicit.exists():
            sources.append(explicit)
        for pattern in ("*.log", "*.jsonl"):
            sources.extend((backend_root / "logs").glob(pattern))
            sources.extend((project_root / "log").glob(pattern))
        unique: dict[str, Path] = {}
        for path in sources:
            if path.is_file():
                unique[str(path.resolve())] = path
        return sorted(unique.values(), key=lambda item: item.stat().st_mtime, reverse=True)

    def get_error_feed(self, *, limit: int = 100) -> ErrorFeedResponse:
        items: list[ErrorFeedItem] = []
        remaining = max(limit, 1)
        for path in self._discover_error_sources():
            if remaining <= 0:
                break
            raw_lines = _tail_lines(path, min(max(remaining * 3, 40), 400))
            for line in reversed(raw_lines):
                if remaining <= 0:
                    break
                raw = line.strip()
                if not raw:
                    continue
                if path.suffix == ".jsonl":
                    parsed = None
                    try:
                        parsed = json.loads(raw)
                    except Exception:
                        parsed = None
                    if isinstance(parsed, dict):
                        message = str(parsed.get("error") or parsed.get("message") or parsed.get("response") or "")[:1200]
                        if not message:
                            continue
                        timestamp = parsed.get("timestamp") or parsed.get("created_at")
                        items.append(
                            ErrorFeedItem(
                                source=path.name,
                                level="error",
                                message=message,
                                timestamp=str(timestamp) if timestamp is not None else None,
                            )
                        )
                        remaining -= 1
                        continue
                if not re.search(r"(error|exception|traceback|failed)", raw, re.IGNORECASE):
                    continue
                ts_match = re.match(r"^(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:,\d+)?)", raw)
                timestamp = ts_match.group(1) if ts_match else None
                level = "error" if re.search(r"error", raw, re.IGNORECASE) else "warning"
                items.append(
                    ErrorFeedItem(
                        source=path.name,
                        level=level,
                        message=raw[:1200],
                        timestamp=timestamp,
                    )
                )
                remaining -= 1
        return ErrorFeedResponse(items=items[:limit])
