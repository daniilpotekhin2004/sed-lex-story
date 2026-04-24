from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_player_service
from app.core.deps import require_player
from app.domain.models import User
from app.schemas.player import (
    PlayerCatalogResponse,
    PlayerPackageRead,
    PlayerProjectStatsRead,
    PlayerResumeRead,
    PlayerRunSyncRequest,
    PlayerRunSyncResponse,
)
from app.services.player import PlayerRuntimeError, PlayerService

router = APIRouter(prefix="/v1/player", tags=["player"])


@router.get("/projects", response_model=PlayerCatalogResponse)
async def list_playable_projects(
    current_user: User = Depends(require_player),
    service: PlayerService = Depends(get_player_service),
) -> PlayerCatalogResponse:
    items = await service.list_catalog(current_user)
    return PlayerCatalogResponse(items=items)


@router.get("/projects/{project_id}/package", response_model=PlayerPackageRead)
async def get_player_package(
    project_id: str,
    package_version: str | None = Query(None, max_length=64),
    current_user: User = Depends(require_player),
    service: PlayerService = Depends(get_player_service),
) -> PlayerPackageRead:
    package = await service.get_package(project_id, current_user, package_version=package_version)
    if package is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playable project not found")
    return package


@router.post("/projects/{project_id}/runs/sync", response_model=PlayerRunSyncResponse)
async def sync_player_run(
    project_id: str,
    payload: PlayerRunSyncRequest,
    current_user: User = Depends(require_player),
    service: PlayerService = Depends(get_player_service),
) -> PlayerRunSyncResponse:
    try:
        return await service.sync_run(project_id, current_user, payload)
    except PlayerRuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/projects/{project_id}/stats", response_model=PlayerProjectStatsRead)
async def get_player_project_stats(
    project_id: str,
    current_user: User = Depends(require_player),
    service: PlayerService = Depends(get_player_service),
) -> PlayerProjectStatsRead:
    stats = await service.get_project_stats(project_id, current_user)
    if stats is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playable project not found")
    return stats


@router.get("/projects/{project_id}/resume", response_model=PlayerResumeRead)
async def get_player_project_resume(
    project_id: str,
    current_user: User = Depends(require_player),
    service: PlayerService = Depends(get_player_service),
) -> PlayerResumeRead:
    return await service.get_resume(project_id, current_user)
