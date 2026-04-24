from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.schemas.prompting import PromptBundle
from app.services.prompt_engine import PromptEngine
from app.infra.translator import get_translator

router = APIRouter(prefix="/v1/scenes", tags=["prompt-preview"])


@router.get("/{scene_id}/prompt-preview", response_model=PromptBundle)
async def prompt_preview(
    scene_id: str,
    character_ids: str | None = Query(None),
    session: AsyncSession = Depends(get_db_session),
) -> PromptBundle:
    engine = PromptEngine(session)
    ids: list[str] | None
    if character_ids is None:
        ids = None
    elif character_ids.strip().lower() == "none":
        ids = []
    else:
        ids = [value for value in character_ids.split(",") if value]
    bundle = await engine.build_for_scene(scene_id, visible_character_ids=ids)
    if bundle is None:
        raise HTTPException(status_code=404, detail="Scene not found")
    translator = get_translator()
    prompt, negative = translator.translate_prompt_and_negative(bundle.prompt, bundle.negative_prompt)
    return PromptBundle(prompt=prompt, negative_prompt=negative, config=bundle.config)
