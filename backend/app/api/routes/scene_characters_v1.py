from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_db_session
from app.domain.models import SceneNode, SceneNodeCharacter, CharacterPreset
from app.schemas.scene_characters_v2 import (
    SceneNodeCharacterCreate,
    SceneNodeCharacterRead,
    SceneNodeCharacterUpdate,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

router = APIRouter(prefix="/v1/scenes", tags=["scene-characters"])


@router.post(
    "/{scene_id}/characters",
    response_model=SceneNodeCharacterRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_character_to_scene(
    scene_id: str,
    payload: SceneNodeCharacterCreate,
    session: AsyncSession = Depends(get_db_session),
) -> SceneNodeCharacterRead:
    scene = await session.get(SceneNode, scene_id)
    if scene is None:
        raise HTTPException(status_code=404, detail="Scene not found")
    character = await session.get(CharacterPreset, payload.character_preset_id)
    if character is None:
        raise HTTPException(status_code=400, detail="Character preset not found")

    link = SceneNodeCharacter(
        scene_id=scene_id,
        character_preset_id=payload.character_preset_id,
        scene_context=payload.scene_context,
        position=payload.position,
        importance=payload.importance,
        seed_override=payload.seed_override,
        in_frame=payload.in_frame,
        material_set_id=payload.material_set_id,
    )
    session.add(link)
    await session.commit()
    await session.refresh(link)
    return link


@router.get(
    "/{scene_id}/characters",
    response_model=list[SceneNodeCharacterRead],
)
async def list_scene_characters(
    scene_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> list[SceneNodeCharacterRead]:
    result = await session.execute(
        select(SceneNodeCharacter).where(SceneNodeCharacter.scene_id == scene_id)
    )
    return list(result.scalars().all())


@router.patch(
    "/{scene_id}/characters/{link_id}",
    response_model=SceneNodeCharacterRead,
)
async def update_scene_character_link(
    scene_id: str,
    link_id: str,
    payload: SceneNodeCharacterUpdate,
    session: AsyncSession = Depends(get_db_session),
) -> SceneNodeCharacterRead:
    link = await session.get(SceneNodeCharacter, link_id)
    if link is None or link.scene_id != scene_id:
        raise HTTPException(status_code=404, detail="Scene character link not found")
    for field, value in payload.dict(exclude_unset=True).items():
        setattr(link, field, value)
    await session.commit()
    await session.refresh(link)
    return link


@router.delete(
    "/{scene_id}/characters/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_scene_character_link(
    scene_id: str,
    link_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> None:
    link = await session.get(SceneNodeCharacter, link_id)
    if link is None or link.scene_id != scene_id:
        raise HTTPException(status_code=404, detail="Scene character link not found")
    await session.delete(link)
    await session.commit()
