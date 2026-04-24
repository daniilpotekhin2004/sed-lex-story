from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.models import Quest, Scene
from app.schemas.quests import QuestCreate, SceneCreate


class QuestService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_quest(self, payload: QuestCreate) -> Quest:
        quest = Quest(
            title=payload.title,
            description=payload.description,
            audience=payload.audience,
        )
        self.session.add(quest)
        await self.session.commit()
        # Eager load relationships to avoid lazy load issues
        await self.session.refresh(quest, ["scenes"])
        return quest

    async def add_scene(self, quest_id: str, payload: SceneCreate) -> Optional[Scene]:
        quest = await self.session.get(Quest, quest_id)
        if quest is None:
            return None

        order = payload.order
        if order is None:
            result = await self.session.execute(
                select(func.count()).select_from(Scene).where(Scene.quest_id == quest_id)
            )
            order = (result.scalar_one() or 0) + 1

        scene = Scene(
            quest_id=quest_id,
            title=payload.title,
            text=payload.text,
            order=order,
        )
        self.session.add(scene)
        await self.session.commit()
        # Eager load relationships to avoid lazy load issues
        await self.session.refresh(scene, ["quest"])
        return scene

    async def get_quest_with_scenes(self, quest_id: str) -> Optional[Quest]:
        result = await self.session.execute(
            select(Quest)
            .options(
                selectinload(Quest.scenes).load_only(
                    Scene.id, Scene.quest_id, Scene.title, Scene.text, Scene.order, Scene.image_path
                )
            )
            .where(Quest.id == quest_id)
        )
        return result.scalar_one_or_none()

    async def get_scene(self, scene_id: str) -> Optional[Scene]:
        return await self.session.get(Scene, scene_id)
