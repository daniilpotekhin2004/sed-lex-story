from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_active_user, require_author, require_admin
from app.domain.models import User
from app.infra.db import get_session as get_db_session
from app.schemas.moderation import (
    GeneratedImageRead,
    GeneratedImageList,
    ModerationAction,
    ModerationStats,
    ImageSelectionRequest,
    BulkModerationRequest,
    SceneImagesResponse,
    ModerationQueueItem,
    ModerationQueueResponse,
)
from app.services.moderation import ModerationService

router = APIRouter(prefix="/moderation", tags=["moderation"])


# === Мои изображения (для авторов) ===

@router.get("/my-images", response_model=GeneratedImageList)
async def get_my_images(
    status: Optional[str] = Query(None, description="Фильтр по статусу"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Получить мои сгенерированные изображения."""
    service = ModerationService(db)
    images, total = await service.list_my_images(
        current_user.id,
        status_filter=status,
        page=page,
        page_size=page_size
    )
    
    return GeneratedImageList(
        items=images,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/scenes/{scene_id}/images", response_model=SceneImagesResponse)
async def get_scene_images(
    scene_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Получить все изображения сцены."""
    service = ModerationService(db)
    images = await service.get_scene_images(scene_id)
    selected = await service.get_selected_image(scene_id)
    
    return SceneImagesResponse(
        scene_id=scene_id,
        images=images,
        selected_image=selected,
    )


@router.post("/images/{image_id}/select", response_model=GeneratedImageRead)
async def select_image(
    image_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Выбрать изображение как основное для сцены (только автор)."""
    service = ModerationService(db)
    image = await service.select_image(image_id, current_user.id)
    return image


# === Модерация (для авторов и админов) ===

@router.get("/queue", response_model=ModerationQueueResponse)
async def get_moderation_queue(
    status: Optional[str] = Query(None, description="Фильтр по статусу (по умолчанию: generated)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_author),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Получить очередь модерации (только для авторов и админов).
    По умолчанию показывает изображения со статусом 'generated'.
    """
    service = ModerationService(db)
    images, total = await service.get_moderation_queue(
        status_filter=status,
        page=page,
        page_size=page_size
    )
    
    # Формируем расширенную информацию
    items = []
    for image in images:
        scene = image.scene
        quest = scene.quest if scene else None
        author = image.author
        
        items.append(ModerationQueueItem(
            image=image,
            scene_title=scene.title if scene else None,
            quest_title=quest.title if quest else None,
            author_username=author.username if author else "Unknown",
        ))
    
    return ModerationQueueResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/stats", response_model=ModerationStats)
async def get_moderation_stats(
    current_user: User = Depends(require_author),
    db: AsyncSession = Depends(get_db_session),
):
    """Получить статистику модерации (только для авторов и админов)."""
    service = ModerationService(db)
    stats = await service.get_moderation_stats()
    return ModerationStats(**stats)


@router.post("/images/{image_id}/moderate", response_model=GeneratedImageRead)
async def moderate_image(
    image_id: str,
    action: ModerationAction,
    current_user: User = Depends(require_author),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Модерировать изображение (только для авторов и админов).
    Автор не может модерировать свои изображения.
    """
    service = ModerationService(db)
    image = await service.moderate_image(
        image_id,
        action,
        current_user.id,
        current_user.role
    )
    return image


@router.post("/bulk-moderate", status_code=status.HTTP_200_OK)
async def bulk_moderate_images(
    data: BulkModerationRequest,
    current_user: User = Depends(require_author),
    db: AsyncSession = Depends(get_db_session),
):
    """Массовая модерация изображений (только для авторов и админов)."""
    service = ModerationService(db)
    count = await service.bulk_moderate(data, current_user.id, current_user.role)
    return {"message": f"Successfully moderated {count} images", "count": count}


@router.get("/images/{image_id}", response_model=GeneratedImageRead)
async def get_image(
    image_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Получить информацию об изображении."""
    service = ModerationService(db)
    image = await service.get_image(image_id)
    return image


@router.delete("/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_image(
    image_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Удалить изображение (автор или админ)."""
    service = ModerationService(db)
    await service.delete_image(image_id, current_user.id, current_user.role)


# === Админские эндпоинты ===

@router.post("/admin/images/{image_id}/force-approve", response_model=GeneratedImageRead)
async def force_approve_image(
    image_id: str,
    notes: Optional[str] = None,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """Принудительно одобрить изображение (только админ)."""
    service = ModerationService(db)
    action = ModerationAction(action="approve", notes=notes)
    image = await service.moderate_image(
        image_id,
        action,
        current_user.id,
        current_user.role
    )
    return image
