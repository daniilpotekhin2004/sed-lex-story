"""Сервис для работы с пресетами генерации пользователя."""
from uuid import uuid4
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.user_preset import UserGenerationPreset
from app.schemas.user_presets import UserPresetCreate, UserPresetUpdate


class UserPresetService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_user_presets(self, user_id: str) -> List[UserGenerationPreset]:
        """Получить все пресеты пользователя."""
        result = await self.db.execute(
            select(UserGenerationPreset)
            .where(UserGenerationPreset.user_id == user_id)
            .order_by(UserGenerationPreset.is_favorite.desc(), UserGenerationPreset.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_preset(self, preset_id: str, user_id: str) -> Optional[UserGenerationPreset]:
        """Получить пресет по ID."""
        result = await self.db.execute(
            select(UserGenerationPreset).where(
                UserGenerationPreset.id == preset_id,
                UserGenerationPreset.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_preset(
        self, user_id: str, data: UserPresetCreate
    ) -> UserGenerationPreset:
        """Создать новый пресет."""
        preset = UserGenerationPreset(
            id=uuid4().hex,
            user_id=user_id,
            name=data.name,
            description=data.description,
            negative_prompt=data.negative_prompt,
            cfg_scale=data.cfg_scale,
            steps=data.steps,
            width=data.width,
            height=data.height,
            style=data.style,
            sampler=data.sampler,
            scheduler=data.scheduler,
            model_id=data.model_id,
            vae_id=data.vae_id,
            seed=data.seed,
            pipeline_profile_id=data.pipeline_profile_id,
            pipeline_profile_version=data.pipeline_profile_version,
            lora_models=[m.dict() for m in data.lora_models] if data.lora_models else None,
            is_favorite=data.is_favorite,
        )
        self.db.add(preset)
        await self.db.commit()
        # No relationships to eager load for UserGenerationPreset
        await self.db.refresh(preset)
        return preset

    async def update_preset(
        self, preset_id: str, user_id: str, data: UserPresetUpdate
    ) -> Optional[UserGenerationPreset]:
        """Обновить пресет."""
        preset = await self.get_preset(preset_id, user_id)
        if not preset:
            return None

        update_data = data.dict(exclude_unset=True)
        if "lora_models" in update_data and update_data["lora_models"]:
            update_data["lora_models"] = [m.dict() for m in update_data["lora_models"]]

        for key, value in update_data.items():
            setattr(preset, key, value)

        await self.db.commit()
        # No relationships to eager load for UserGenerationPreset
        await self.db.refresh(preset)
        return preset

    async def delete_preset(self, preset_id: str, user_id: str) -> bool:
        """Удалить пресет."""
        preset = await self.get_preset(preset_id, user_id)
        if not preset:
            return False

        await self.db.delete(preset)
        await self.db.commit()
        return True
