from typing import List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import GeneratedImage, ImageStatus, UserRole
from app.core.telemetry import track_event
from app.infra.repositories.generated_image import GeneratedImageRepository
from app.schemas.moderation import (
    GeneratedImageCreate,
    ModerationAction,
    BulkModerationRequest,
)


class ModerationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = GeneratedImageRepository(db)

    async def create_image_record(
        self,
        data: GeneratedImageCreate,
        author_id: str,
        task_id: Optional[str] = None
    ) -> GeneratedImage:
        """Создать запись о генерации изображения."""
        image = GeneratedImage(
            scene_id=data.scene_id,
            author_id=author_id,
            task_id=task_id,
            prompt=data.prompt,
            negative_prompt=data.negative_prompt,
            generation_params=data.generation_params,
            variant_number=data.variant_number,
            status=ImageStatus.PENDING.value,
        )
        return await self.repo.create(image)

    async def get_image(self, image_id: str) -> GeneratedImage:
        """Получить изображение по ID."""
        image = await self.repo.get_by_id(image_id)
        if not image:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Image not found"
            )
        return image

    async def get_scene_images(self, scene_id: str) -> List[GeneratedImage]:
        """Получить все изображения сцены."""
        return await self.repo.list_by_scene(scene_id)

    async def get_selected_image(self, scene_id: str) -> Optional[GeneratedImage]:
        """Получить выбранное изображение сцены."""
        return await self.repo.get_selected_image(scene_id)

    async def list_my_images(
        self,
        author_id: str,
        status_filter: Optional[str] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[GeneratedImage], int]:
        """Получить мои изображения."""
        skip = (page - 1) * page_size
        return await self.repo.list_by_author(
            author_id,
            status=status_filter,
            skip=skip,
            limit=page_size
        )

    async def get_moderation_queue(
        self,
        status_filter: Optional[str] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[GeneratedImage], int]:
        """Получить очередь модерации."""
        skip = (page - 1) * page_size
        return await self.repo.list_for_moderation(
            status=status_filter,
            skip=skip,
            limit=page_size
        )

    async def get_moderation_stats(self) -> dict:
        """Получить статистику модерации."""
        return await self.repo.get_moderation_stats()

    async def moderate_image(
        self,
        image_id: str,
        action: ModerationAction,
        moderator_id: str,
        moderator_role: UserRole
    ) -> GeneratedImage:
        """Модерировать изображение."""
        image = await self.get_image(image_id)

        # Проверка прав
        if moderator_role not in [UserRole.ADMIN, UserRole.AUTHOR]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only authors and admins can moderate images"
            )

        # Автор не может модерировать свои изображения
        if not image.can_moderate(moderator_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You cannot moderate your own images"
            )

        # Проверка статуса
        if image.status not in [ImageStatus.GENERATED.value, ImageStatus.APPROVED.value, ImageStatus.REJECTED.value]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot moderate image with status: {image.status}"
            )

        # Применить действие
        if action.action == "approve":
            image.approve(moderator_id, action.notes)
        elif action.action == "reject":
            if not action.notes:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Rejection reason is required"
                )
            image.reject(moderator_id, action.notes)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid action. Must be 'approve' or 'reject'"
            )

        updated = await self.repo.update(image)
        track_event(
            "image_moderated",
            user_id=moderator_id,
            metadata={"image_id": image_id, "action": action.action, "notes": action.notes},
        )
        return updated

    async def bulk_moderate(
        self,
        data: BulkModerationRequest,
        moderator_id: str,
        moderator_role: UserRole
    ) -> int:
        """Массовая модерация изображений."""
        if moderator_role not in [UserRole.ADMIN, UserRole.AUTHOR]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only authors and admins can moderate images"
            )

        if data.action == "reject" and not data.notes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Rejection reason is required"
            )

        # Проверить, что модератор не модерирует свои изображения
        for image_id in data.image_ids:
            image = await self.repo.get_by_id(image_id)
            if image and not image.can_moderate(moderator_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Cannot moderate your own image: {image_id}"
                )

        # Применить действие
        status_value = ImageStatus.APPROVED.value if data.action == "approve" else ImageStatus.REJECTED.value
        count = await self.repo.bulk_update_status(
            data.image_ids,
            status_value,
            moderator_id,
            data.notes
        )

        return count

    async def select_image(
        self,
        image_id: str,
        author_id: str
    ) -> GeneratedImage:
        """Выбрать изображение как основное для сцены."""
        image = await self.get_image(image_id)

        # Проверка прав (только автор)
        if image.author_id != author_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the author can select images"
            )

        # Проверка статуса (только одобренные)
        if image.status != ImageStatus.APPROVED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only approved images can be selected"
            )

        # Снять выбор с других изображений сцены
        await self.repo.unselect_all_for_scene(image.scene_id)

        # Выбрать это изображение
        image.select()
        updated = await self.repo.update(image)
        track_event(
            "image_selected",
            user_id=author_id,
            metadata={"image_id": image_id, "scene_id": image.scene_id},
        )
        return updated

    async def update_image_status(
        self,
        image_id: str,
        new_status: ImageStatus,
        image_path: Optional[str] = None,
        thumbnail_path: Optional[str] = None,
        generation_time: Optional[int] = None,
        file_size: Optional[int] = None
    ) -> GeneratedImage:
        """Обновить статус изображения (для воркера)."""
        image = await self.get_image(image_id)

        image.status = new_status.value
        
        if image_path:
            image.image_path = image_path
        if thumbnail_path:
            image.thumbnail_path = thumbnail_path
        if generation_time is not None:
            image.generation_time_seconds = generation_time
        if file_size is not None:
            image.file_size_bytes = file_size

        return await self.repo.update(image)

    async def delete_image(
        self,
        image_id: str,
        user_id: str,
        user_role: UserRole
    ) -> None:
        """Удалить изображение."""
        image = await self.get_image(image_id)

        # Проверка прав (автор или админ)
        if image.author_id != user_id and user_role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to delete this image"
            )

        await self.repo.delete(image)
