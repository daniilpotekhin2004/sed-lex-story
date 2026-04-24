from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_quest_service
from app.schemas.quests import QuestCreate, QuestRead, SceneCreate, SceneRead
from app.services.quests import QuestService

router = APIRouter(prefix="/quests", tags=["quests"])


@router.post("", response_model=QuestRead, status_code=status.HTTP_201_CREATED)
async def create_quest(
    payload: QuestCreate, service: QuestService = Depends(get_quest_service)
) -> QuestRead:
    quest = await service.create_quest(payload)
    return quest


@router.post(
    "/{quest_id}/scenes",
    response_model=SceneRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_scene_to_quest(
    quest_id: str,
    payload: SceneCreate,
    service: QuestService = Depends(get_quest_service),
) -> SceneRead:
    scene = await service.add_scene(quest_id, payload)
    if scene is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quest not found")
    return scene


@router.get("/{quest_id}", response_model=QuestRead)
async def get_quest(
    quest_id: str, service: QuestService = Depends(get_quest_service)
) -> QuestRead:
    quest = await service.get_quest_with_scenes(quest_id)
    if quest is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quest not found")
    return quest
