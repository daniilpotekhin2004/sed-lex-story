from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.core.deps import require_author
from app.domain.models import User
from app.schemas.training import (
    LoraTrainingRequest,
    LoraTrainingResponse,
    TextualInversionRequest,
    TextualInversionResponse,
)
from app.services.training import TrainingService

router = APIRouter(prefix="/v1/training", tags=["training"])


@router.post("/textual-inversion", response_model=TextualInversionResponse)
async def create_textual_inversion(
    payload: TextualInversionRequest,
    current_user: User = Depends(require_author),
    db: AsyncSession = Depends(get_db_session),
) -> TextualInversionResponse:
    service = TrainingService(db)
    info = await service.create_textual_inversion(
        token=payload.token,
        character_id=payload.character_id,
        init_text=payload.init_text,
        num_vectors=payload.num_vectors,
        overwrite=payload.overwrite,
        user_id=current_user.id,
    )
    return TextualInversionResponse(token=payload.token, created=True, info=info or None)


@router.post("/lora", response_model=LoraTrainingResponse)
async def prepare_lora_training(
    payload: LoraTrainingRequest,
    current_user: User = Depends(require_author),
    db: AsyncSession = Depends(get_db_session),
) -> LoraTrainingResponse:
    service = TrainingService(db)
    result = await service.prepare_lora_dataset(
        material_set_id=payload.material_set_id,
        token=payload.token,
        label=payload.label,
        caption=payload.caption,
        character_id=payload.character_id,
        user_id=current_user.id,
    )
    return LoraTrainingResponse(**result)
