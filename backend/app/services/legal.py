from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import LegalConcept
from app.schemas.legal import LegalConceptCreate


class LegalConceptService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_concept(self, payload: LegalConceptCreate) -> LegalConcept:
        concept = LegalConcept(
            code=payload.code,
            title=payload.title,
            description=payload.description,
            difficulty=payload.difficulty,
            tags=payload.tags,
        )
        self.session.add(concept)
        await self.session.commit()
        # Eager load relationships to avoid lazy load issues
        await self.session.refresh(concept, ["scenes"])
        return concept

    async def list_concepts(self) -> List[LegalConcept]:
        result = await self.session.execute(select(LegalConcept))
        return list(result.scalars().all())

    async def get_by_ids(self, ids: List[str]) -> List[LegalConcept]:
        if not ids:
            return []
        result = await self.session.execute(select(LegalConcept).where(LegalConcept.id.in_(ids)))
        return list(result.scalars().all())

    async def get_concept(self, concept_id: str) -> Optional[LegalConcept]:
        return await self.session.get(LegalConcept, concept_id)
