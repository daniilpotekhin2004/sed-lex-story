from __future__ import annotations

from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import TelemetryEvent
from app.schemas.telemetry import TelemetryEventCreate


class TelemetryService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def record_event(self, payload: TelemetryEventCreate, user_id: str | None) -> TelemetryEvent:
        event = TelemetryEvent(
            user_id=user_id,
            event_name=payload.event_name,
            payload=payload.payload,
        )
        self.session.add(event)
        await self.session.commit()
        # No need to refresh - TelemetryEvent has no relationships and all fields are set
        return event

    async def list_events(self, limit: int = 200) -> List[TelemetryEvent]:
        result = await self.session.execute(
            select(TelemetryEvent).order_by(TelemetryEvent.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())
