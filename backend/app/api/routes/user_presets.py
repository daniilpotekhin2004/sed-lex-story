"""API для пресетов генерации пользователя."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_active_user
from app.domain.models import User
from app.infra.db import get_session as get_db_session
from app.schemas.user_presets import (
    UserPresetCreate,
    UserPresetList,
    UserPresetRead,
    UserPresetUpdate,
)
from app.services.user_presets import UserPresetService

router = APIRouter(prefix="/user-presets", tags=["user-presets"])


@router.get("", response_model=UserPresetList)
async def list_user_presets(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Получить список пресетов текущего пользователя."""
    service = UserPresetService(db)
    presets = await service.list_user_presets(current_user.id)
    return UserPresetList(items=presets, total=len(presets))


@router.post("", response_model=UserPresetRead, status_code=status.HTTP_201_CREATED)
async def create_user_preset(
    data: UserPresetCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Создать новый пресет."""
    service = UserPresetService(db)
    return await service.create_preset(current_user.id, data)


@router.get("/{preset_id}", response_model=UserPresetRead)
async def get_user_preset(
    preset_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Получить пресет по ID."""
    service = UserPresetService(db)
    preset = await service.get_preset(preset_id, current_user.id)
    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")
    return preset


@router.patch("/{preset_id}", response_model=UserPresetRead)
async def update_user_preset(
    preset_id: str,
    data: UserPresetUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Обновить пресет."""
    service = UserPresetService(db)
    preset = await service.update_preset(preset_id, current_user.id, data)
    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")
    return preset


@router.delete("/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_preset(
    preset_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Удалить пресет."""
    service = UserPresetService(db)
    deleted = await service.delete_preset(preset_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Preset not found")
