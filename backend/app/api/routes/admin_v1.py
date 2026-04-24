from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_active_user, require_admin
from app.domain.models import User, UserRole
from app.infra.db import get_session as get_db_session
from app.schemas.admin import (
    AdminOverviewResponse,
    AdminUserListResponse,
    CohortUpdateRequest,
    CohortUpdateResult,
    ComfyOverviewResponse,
    ErrorFeedResponse,
    RoleAuditListResponse,
    RoleBulkUpdateRequest,
    RoleBulkUpdateResponse,
    RoleUpdateRequest,
    RoleUpdateResult,
    UserStatsResponse,
)
from app.services.admin_console import AdminConsoleService

router = APIRouter(prefix="/v1/admin", tags=["admin"])


@router.get("/users", response_model=AdminUserListResponse)
async def list_users(
    search: str | None = Query(None),
    role: str | None = Query(None),
    registered_from: datetime | None = Query(None),
    registered_to: datetime | None = Query(None),
    activity_from: datetime | None = Query(None),
    activity_to: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> AdminUserListResponse:
    service = AdminConsoleService(db)
    return await service.list_users(
        search=search,
        role=role,
        registered_from=registered_from,
        registered_to=registered_to,
        activity_from=activity_from,
        activity_to=activity_to,
        page=page,
        page_size=page_size,
    )


@router.post("/users/{user_id}/role", response_model=RoleUpdateResult)
async def change_user_role(
    user_id: str,
    payload: RoleUpdateRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> RoleUpdateResult:
    service = AdminConsoleService(db)
    return await service.update_user_role(actor=current_user, user_id=user_id, payload=payload)


@router.post("/users/{user_id}/cohort", response_model=CohortUpdateResult)
async def change_user_cohort(
    user_id: str,
    payload: CohortUpdateRequest,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> CohortUpdateResult:
    service = AdminConsoleService(db)
    return await service.update_user_cohort(user_id=user_id, payload=payload)


@router.post("/users/roles/bulk", response_model=RoleBulkUpdateResponse)
async def bulk_change_roles(
    payload: RoleBulkUpdateRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> RoleBulkUpdateResponse:
    service = AdminConsoleService(db)
    return await service.bulk_update_roles(actor=current_user, payload=payload)


@router.get("/users/{user_id}/stats", response_model=UserStatsResponse)
async def get_user_stats(
    user_id: str,
    period_from: datetime | None = Query(None),
    period_to: datetime | None = Query(None),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> UserStatsResponse:
    service = AdminConsoleService(db)
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return await service.get_user_stats(
        user=user,
        period_from=period_from,
        period_to=period_to,
        include_comfy=True,
        minimal=False,
    )


@router.get("/me/stats", response_model=UserStatsResponse)
async def get_my_stats(
    period_from: datetime | None = Query(None),
    period_to: datetime | None = Query(None),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> UserStatsResponse:
    service = AdminConsoleService(db)
    include_comfy = current_user.role in {UserRole.ADMIN, UserRole.AUTHOR}
    minimal = current_user.role == UserRole.PLAYER
    return await service.get_user_stats(
        user=current_user,
        period_from=period_from,
        period_to=period_to,
        include_comfy=include_comfy,
        minimal=minimal,
    )


@router.get("/overview", response_model=AdminOverviewResponse)
async def get_overview(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> AdminOverviewResponse:
    service = AdminConsoleService(db)
    return await service.get_overview()


@router.get("/comfy", response_model=ComfyOverviewResponse)
async def get_comfy_overview(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> ComfyOverviewResponse:
    service = AdminConsoleService(db)
    return await service.get_comfy_overview()


@router.get("/audit/roles", response_model=RoleAuditListResponse)
async def list_role_audit(
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=200),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> RoleAuditListResponse:
    service = AdminConsoleService(db)
    return await service.list_role_audit(page=page, page_size=page_size)


@router.get("/errors", response_model=ErrorFeedResponse)
async def get_errors_feed(
    limit: int = Query(100, ge=1, le=300),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> ErrorFeedResponse:
    service = AdminConsoleService(db)
    return service.get_error_feed(limit=limit)
