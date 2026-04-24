from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_style_profile_service
from app.schemas.style_profiles import (
    StyleProfileBootstrapRequest,
    StyleProfileCreate,
    StyleProfileRead,
    StyleProfileUpdate,
)
from app.services.style_profiles import StyleProfileService

router = APIRouter(prefix="/v1/style-profiles", tags=["styles"])


@router.post("", response_model=StyleProfileRead, status_code=status.HTTP_201_CREATED)
async def create_style_profile(
    payload: StyleProfileCreate,
    service: StyleProfileService = Depends(get_style_profile_service),
) -> StyleProfileRead:
    style = await service.create_style(payload)
    if style is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return style


@router.get("", response_model=list[StyleProfileRead])
async def list_styles(
    project_id: str | None = None,
    service: StyleProfileService = Depends(get_style_profile_service),
) -> list[StyleProfileRead]:
    if project_id:
        return await service.list_styles(project_id)
    return await service.list_all()


@router.post("/bootstrap/legal", response_model=list[StyleProfileRead])
async def bootstrap_legal_style_profiles(
    payload: StyleProfileBootstrapRequest,
    service: StyleProfileService = Depends(get_style_profile_service),
) -> list[StyleProfileRead]:
    """Create a curated set of legal-oriented style profiles for a project.

    This endpoint is idempotent by default (it will skip profiles that already exist).
    Use `overwrite=true` to update existing templates.
    """

    styles = await service.bootstrap_legal_styles(payload.project_id, overwrite=payload.overwrite)
    if styles is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return styles


@router.get("/{style_id}", response_model=StyleProfileRead)
async def get_style_profile(
    style_id: str,
    service: StyleProfileService = Depends(get_style_profile_service),
) -> StyleProfileRead:
    style = await service.get_style(style_id)
    if style is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Style profile not found")
    return style


@router.patch("/{style_id}", response_model=StyleProfileRead)
async def update_style_profile(
    style_id: str,
    payload: StyleProfileUpdate,
    service: StyleProfileService = Depends(get_style_profile_service),
) -> StyleProfileRead:
    style = await service.update_style(style_id, payload)
    if style is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Style profile not found")
    return style
