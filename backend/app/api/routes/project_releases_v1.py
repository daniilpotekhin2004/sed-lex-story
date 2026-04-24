from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_project_release_service
from app.core.deps import get_current_active_user
from app.domain.models import User
from app.schemas.releases import (
    ProjectReleaseListResponse,
    ProjectReleaseRead,
    PublishProjectReleaseRequest,
    ReleaseCandidateUserListResponse,
    ReplaceProjectReleaseAccessRequest,
)
from app.services.project_releases import ProjectReleaseError, ProjectReleaseService

router = APIRouter(prefix="/v1/projects/{project_id}/releases", tags=["project-releases"])


@router.get("", response_model=ProjectReleaseListResponse)
async def list_project_releases(
    project_id: str,
    current_user: User = Depends(get_current_active_user),
    service: ProjectReleaseService = Depends(get_project_release_service),
) -> ProjectReleaseListResponse:
    try:
        items = await service.list_releases(project_id, actor=current_user)
    except ProjectReleaseError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ProjectReleaseListResponse(items=items)


@router.get("/candidate-users", response_model=ReleaseCandidateUserListResponse)
async def list_release_candidate_users(
    project_id: str,
    search: str | None = Query(None, max_length=120),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    service: ProjectReleaseService = Depends(get_project_release_service),
) -> ReleaseCandidateUserListResponse:
    try:
        await service.list_releases(project_id, actor=current_user)
    except ProjectReleaseError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    items = await service.list_candidate_users(search=search, limit=limit)
    return ReleaseCandidateUserListResponse(items=items)


@router.post("/publish", response_model=ProjectReleaseRead, status_code=status.HTTP_201_CREATED)
async def publish_project_release(
    project_id: str,
    payload: PublishProjectReleaseRequest,
    current_user: User = Depends(get_current_active_user),
    service: ProjectReleaseService = Depends(get_project_release_service),
) -> ProjectReleaseRead:
    try:
        return await service.publish_release(
            project_id=project_id,
            actor=current_user,
            graph_id=payload.graph_id,
            notes=payload.notes,
        )
    except ProjectReleaseError as exc:
        detail = str(exc)
        status_code = status.HTTP_404_NOT_FOUND if "not found" in detail.lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.put("/{release_id}/access", response_model=ProjectReleaseRead)
async def replace_project_release_access(
    project_id: str,
    release_id: str,
    payload: ReplaceProjectReleaseAccessRequest,
    current_user: User = Depends(get_current_active_user),
    service: ProjectReleaseService = Depends(get_project_release_service),
) -> ProjectReleaseRead:
    try:
        return await service.replace_release_access(
            project_id=project_id,
            release_id=release_id,
            user_ids=payload.user_ids,
            cohort_codes=payload.cohort_codes,
            actor=current_user,
        )
    except ProjectReleaseError as exc:
        detail = str(exc)
        status_code = status.HTTP_404_NOT_FOUND if "not found" in detail.lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/{release_id}/archive", response_model=ProjectReleaseRead)
async def archive_project_release(
    project_id: str,
    release_id: str,
    current_user: User = Depends(get_current_active_user),
    service: ProjectReleaseService = Depends(get_project_release_service),
) -> ProjectReleaseRead:
    try:
        return await service.archive_release(project_id=project_id, release_id=release_id, actor=current_user)
    except ProjectReleaseError as exc:
        detail = str(exc)
        status_code = status.HTTP_404_NOT_FOUND if "not found" in detail.lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=detail) from exc
