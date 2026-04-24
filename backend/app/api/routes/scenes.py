from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_generation_service, get_quest_service, get_sd_overrides
from app.schemas.generation import GenerationRequest, GenerationResponse
from app.services.generation import ImageGenerationService
from app.services.quests import QuestService
from app.utils.sd_provider import SDProviderOverrides

router = APIRouter(prefix="/scenes", tags=["generation"])


@router.post(
    "/{scene_id}/generate-images",
    response_model=GenerationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_images_for_scene(
    scene_id: str,
    payload: GenerationRequest,
    generation_service: ImageGenerationService = Depends(get_generation_service),
    quest_service: QuestService = Depends(get_quest_service),
    sd_overrides: SDProviderOverrides = Depends(get_sd_overrides),
) -> GenerationResponse:
    scene = await quest_service.get_scene(scene_id)
    if scene is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")
    task_id = generation_service.enqueue_generation(scene_id, payload, sd_overrides=sd_overrides)
    return GenerationResponse(task_id=task_id)
