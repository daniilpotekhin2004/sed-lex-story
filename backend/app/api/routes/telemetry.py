from fastapi import APIRouter, Depends

from app.api.deps import get_db_session
from app.core.deps import get_optional_user
from app.domain.models import User
from app.schemas.telemetry import TelemetryEventCreate, TelemetryEventRead
from app.services.telemetry import TelemetryService
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


@router.post("/events", response_model=TelemetryEventRead)
async def record_event(
    data: TelemetryEventCreate,
    current_user: User | None = Depends(get_optional_user),
    session: AsyncSession = Depends(get_db_session),
) -> TelemetryEventRead:
    service = TelemetryService(session)
    return await service.record_event(data, current_user.id if current_user else None)


@router.get("/events", response_model=list[TelemetryEventRead])
async def list_events(
    session: AsyncSession = Depends(get_db_session),
) -> list[TelemetryEventRead]:
    service = TelemetryService(session)
    return await service.list_events()
