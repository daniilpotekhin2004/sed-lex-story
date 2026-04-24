from typing import List, Optional
from datetime import datetime

from sqlalchemy import select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.models import CharacterPreset, SceneCharacter


class CharacterPresetRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, preset_id: str) -> Optional[CharacterPreset]:
        """Получить пресет по ID."""
        result = await self.db.execute(
            select(CharacterPreset).where(
                CharacterPreset.id == preset_id,
                CharacterPreset.archived_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_name(
        self,
        name: str,
        author_id: str,
        project_id: Optional[str] = None,
    ) -> Optional[CharacterPreset]:
        """Получить пресет по имени и автору."""
        result = await self.db.execute(
            select(CharacterPreset)
            .where(
                and_(
                    CharacterPreset.name == name,
                    CharacterPreset.author_id == author_id,
                    CharacterPreset.project_id == project_id,
                    CharacterPreset.archived_at.is_(None),
                )
            )
            .order_by(CharacterPreset.updated_at.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def list_by_author(
        self,
        author_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> tuple[List[CharacterPreset], int]:
        """Получить пресеты автора."""
        # Count
        count_result = await self.db.execute(
            select(CharacterPreset).where(
                and_(
                    CharacterPreset.author_id == author_id,
                    CharacterPreset.project_id.is_(None),
                    CharacterPreset.archived_at.is_(None),
                )
            )
        )
        total = len(count_result.all())
        
        # Data
        result = await self.db.execute(
            select(CharacterPreset)
            .where(
                and_(
                    CharacterPreset.author_id == author_id,
                    CharacterPreset.project_id.is_(None),
                    CharacterPreset.archived_at.is_(None),
                )
            )
            .offset(skip)
            .limit(limit)
            .order_by(CharacterPreset.created_at.desc())
        )
        return result.scalars().all(), total

    async def list_public(
        self,
        skip: int = 0,
        limit: int = 100,
        character_type: Optional[str] = None
    ) -> tuple[List[CharacterPreset], int]:
        """Получить публичные пресеты."""
        query = select(CharacterPreset).where(
            and_(
                CharacterPreset.is_public == True,
                CharacterPreset.project_id.is_(None),
                CharacterPreset.archived_at.is_(None),
            )
        )
        
        if character_type:
            query = query.where(CharacterPreset.character_type == character_type)
        
        # Count
        count_result = await self.db.execute(query)
        total = len(count_result.all())
        
        # Data
        result = await self.db.execute(
            query
            .offset(skip)
            .limit(limit)
            .order_by(CharacterPreset.usage_count.desc(), CharacterPreset.created_at.desc())
        )
        return result.scalars().all(), total

    async def list_accessible(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> tuple[List[CharacterPreset], int]:
        """Получить доступные пресеты (свои + публичные)."""
        query = select(CharacterPreset).where(
            and_(
                CharacterPreset.project_id.is_(None),
                or_(
                    CharacterPreset.author_id == user_id,
                    CharacterPreset.is_public == True,
                ),
                CharacterPreset.archived_at.is_(None),
            )
        )
        
        # Count
        count_result = await self.db.execute(query)
        total = len(count_result.all())
        
        # Data
        result = await self.db.execute(
            query
            .offset(skip)
            .limit(limit)
            .order_by(CharacterPreset.created_at.desc())
        )
        return result.scalars().all(), total

    async def create(self, preset: CharacterPreset) -> CharacterPreset:
        """Создать пресет."""
        self.db.add(preset)
        await self.db.commit()
        await self.db.refresh(preset)
        return preset

    async def update(self, preset: CharacterPreset) -> CharacterPreset:
        """Обновить пресет."""
        await self.db.commit()
        await self.db.refresh(preset)
        return preset

    async def delete(self, preset: CharacterPreset) -> None:
        """Удалить пресет."""
        preset.archived_at = datetime.utcnow()
        await self.db.commit()

    async def increment_usage(self, preset_id: str) -> None:
        """Увеличить счетчик использования."""
        preset = await self.get_by_id(preset_id)
        if preset:
            preset.usage_count += 1
            await self.db.commit()

    async def list_by_project(
        self,
        project_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[CharacterPreset]:
        result = await self.db.execute(
            select(CharacterPreset)
            .where(
                CharacterPreset.project_id == project_id,
                CharacterPreset.archived_at.is_(None),
            )
            .offset(skip)
            .limit(limit)
            .order_by(CharacterPreset.created_at.desc())
        )
        return list(result.scalars().all())


class SceneCharacterRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, scene_character_id: str) -> Optional[SceneCharacter]:
        """Получить связь по ID."""
        result = await self.db.execute(
            select(SceneCharacter)
            .options(selectinload(SceneCharacter.character_preset))
            .where(SceneCharacter.id == scene_character_id)
        )
        return result.scalar_one_or_none()

    async def list_by_scene(self, scene_id: str) -> List[SceneCharacter]:
        """Получить всех персонажей сцены."""
        result = await self.db.execute(
            select(SceneCharacter)
            .options(selectinload(SceneCharacter.character_preset))
            .where(SceneCharacter.scene_id == scene_id)
            .order_by(SceneCharacter.importance.desc())
        )
        return result.scalars().all()

    async def create(self, scene_character: SceneCharacter) -> SceneCharacter:
        """Добавить персонажа к сцене."""
        self.db.add(scene_character)
        await self.db.commit()
        await self.db.refresh(scene_character)
        return scene_character

    async def update(self, scene_character: SceneCharacter) -> SceneCharacter:
        """Обновить связь."""
        await self.db.commit()
        await self.db.refresh(scene_character)
        return scene_character

    async def delete(self, scene_character: SceneCharacter) -> None:
        """Удалить персонажа из сцены."""
        await self.db.delete(scene_character)
        await self.db.commit()
