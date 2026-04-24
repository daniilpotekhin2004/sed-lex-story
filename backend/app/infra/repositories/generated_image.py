from typing import List, Optional, Tuple

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload

from app.domain.models import GeneratedImage, ImageStatus, Scene, Quest, User


class GeneratedImageRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, image_id: str) -> Optional[GeneratedImage]:
        """Получить изображение по ID."""
        result = await self.db.execute(
            select(GeneratedImage)
            .options(
                selectinload(GeneratedImage.scene),
                selectinload(GeneratedImage.author),
                selectinload(GeneratedImage.moderator),
            )
            .where(GeneratedImage.id == image_id)
        )
        return result.scalar_one_or_none()

    async def get_by_task_id(self, task_id: str) -> Optional[GeneratedImage]:
        """Получить изображение по task_id."""
        result = await self.db.execute(
            select(GeneratedImage).where(GeneratedImage.task_id == task_id)
        )
        return result.scalar_one_or_none()

    async def list_by_scene(self, scene_id: str) -> List[GeneratedImage]:
        """Получить все изображения сцены."""
        result = await self.db.execute(
            select(GeneratedImage)
            .where(GeneratedImage.scene_id == scene_id)
            .order_by(GeneratedImage.variant_number, GeneratedImage.created_at.desc())
        )
        return result.scalars().all()

    async def list_by_author(
        self,
        author_id: str,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> Tuple[List[GeneratedImage], int]:
        """Получить изображения автора."""
        query = select(GeneratedImage).where(GeneratedImage.author_id == author_id)
        
        if status:
            query = query.where(GeneratedImage.status == status)
        
        # Count
        count_result = await self.db.execute(
            select(func.count()).select_from(query.subquery())
        )
        total = count_result.scalar()
        
        # Data
        result = await self.db.execute(
            query
            .options(selectinload(GeneratedImage.scene))
            .offset(skip)
            .limit(limit)
            .order_by(GeneratedImage.created_at.desc())
        )
        return result.scalars().all(), total

    async def list_for_moderation(
        self,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> Tuple[List[GeneratedImage], int]:
        """Получить изображения для модерации."""
        # По умолчанию показываем только сгенерированные (ожидающие модерации)
        if status is None:
            status = ImageStatus.GENERATED.value
        
        query = (
            select(GeneratedImage)
            .options(
                joinedload(GeneratedImage.scene).joinedload(Scene.quest),
                joinedload(GeneratedImage.author),
            )
            .where(GeneratedImage.status == status)
        )
        
        # Count
        count_result = await self.db.execute(
            select(func.count()).select_from(
                select(GeneratedImage).where(GeneratedImage.status == status).subquery()
            )
        )
        total = count_result.scalar()
        
        # Data
        result = await self.db.execute(
            query
            .offset(skip)
            .limit(limit)
            .order_by(GeneratedImage.created_at.asc())  # Старые первыми
        )
        return result.scalars().all(), total

    async def get_moderation_stats(self) -> dict:
        """Получить статистику модерации."""
        result = await self.db.execute(
            select(
                GeneratedImage.status,
                func.count(GeneratedImage.id).label('count')
            )
            .group_by(GeneratedImage.status)
        )
        
        stats = {status.value: 0 for status in ImageStatus}
        for row in result:
            stats[row.status] = row.count
        
        stats['total_images'] = sum(stats.values())
        return stats

    async def get_selected_image(self, scene_id: str) -> Optional[GeneratedImage]:
        """Получить выбранное изображение для сцены."""
        result = await self.db.execute(
            select(GeneratedImage)
            .where(
                and_(
                    GeneratedImage.scene_id == scene_id,
                    GeneratedImage.is_selected == True
                )
            )
        )
        return result.scalar_one_or_none()

    async def create(self, image: GeneratedImage) -> GeneratedImage:
        """Создать запись об изображении."""
        self.db.add(image)
        await self.db.commit()
        await self.db.refresh(image)
        return image

    async def update(self, image: GeneratedImage) -> GeneratedImage:
        """Обновить изображение."""
        await self.db.commit()
        await self.db.refresh(image)
        return image

    async def delete(self, image: GeneratedImage) -> None:
        """Удалить изображение."""
        await self.db.delete(image)
        await self.db.commit()

    async def bulk_update_status(
        self,
        image_ids: List[str],
        status: str,
        moderator_id: str,
        notes: Optional[str] = None
    ) -> int:
        """Массовое обновление статуса."""
        from datetime import datetime
        
        images = await self.db.execute(
            select(GeneratedImage).where(GeneratedImage.id.in_(image_ids))
        )
        
        count = 0
        for image in images.scalars():
            if status == ImageStatus.APPROVED.value:
                image.approve(moderator_id, notes)
            elif status == ImageStatus.REJECTED.value:
                image.reject(moderator_id, notes)
            count += 1
        
        await self.db.commit()
        return count

    async def unselect_all_for_scene(self, scene_id: str) -> None:
        """Снять выбор со всех изображений сцены."""
        images = await self.list_by_scene(scene_id)
        for image in images:
            image.is_selected = False
        await self.db.commit()
