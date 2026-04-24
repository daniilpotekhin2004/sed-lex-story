from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import MaterialSet, CharacterPreset, Location
from app.schemas.material_sets import MaterialSetCreate


class MaterialSetService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_material_sets(
        self,
        project_id: str,
        *,
        asset_type: Optional[str] = None,
        asset_id: Optional[str] = None,
    ) -> list[MaterialSet]:
        query = select(MaterialSet).where(MaterialSet.project_id == project_id)
        if asset_type:
            query = query.where(MaterialSet.asset_type == asset_type)
        if asset_id:
            query = query.where(MaterialSet.asset_id == asset_id)
        result = await self.session.execute(query.order_by(MaterialSet.created_at.desc()))
        return list(result.scalars().all())

    async def create_material_set(
        self,
        project_id: str,
        payload: MaterialSetCreate,
    ) -> MaterialSet:
        reference_images = payload.reference_images
        if reference_images is None:
            if payload.asset_type == "character":
                asset = await self.session.get(CharacterPreset, payload.asset_id)
            elif payload.asset_type == "location":
                asset = await self.session.get(Location, payload.asset_id)
            else:
                asset = None
            reference_images = asset.reference_images if asset else None

        material = MaterialSet(
            project_id=project_id,
            asset_type=payload.asset_type,
            asset_id=payload.asset_id,
            label=payload.label,
            reference_images=reference_images,
            material_metadata=payload.material_metadata,
        )
        self.session.add(material)
        await self.session.commit()
        await self.session.refresh(material)
        return material
