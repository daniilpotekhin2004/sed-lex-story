from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db import get_session as get_db_session
from app.schemas.presets import PresetsResponse, SimplePreset
from app.services.character import CharacterService

router = APIRouter(prefix="/presets", tags=["presets"])


@router.get("", response_model=PresetsResponse)
async def list_presets(db: AsyncSession = Depends(get_db_session)) -> PresetsResponse:
    """
    Публичный список пресетов персонажей и LoRA.
    Возвращает упрощенную структуру для выпадающих списков.
    """
    service = CharacterService(db)
    presets, _total = await service.list_presets(
        user_id=None, only_public=True, page=1, page_size=100
    )

    character_items = [
        SimplePreset(
            id=p.id,
            name=p.name,
            description=p.description,
            preview_thumbnail_url=p.preview_thumbnail_url or p.preview_image_url,
        )
        for p in presets
    ]

    lora_items: dict[str, SimplePreset] = {}
    for preset in presets:
        if preset.lora_models:
            for lora in preset.lora_models:
                name = lora.get("name")
                if not name:
                    continue
                if name not in lora_items:
                    lora_items[name] = SimplePreset(
                        id=f"lora::{name}", name=name, description=str(lora.get("weight", "")),
                    )
    return PresetsResponse(characters=character_items, loras=list(lora_items.values()))
