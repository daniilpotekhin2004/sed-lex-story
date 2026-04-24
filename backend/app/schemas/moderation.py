from typing import Optional, List
from pydantic import BaseModel, Field


class GeneratedImageCreate(BaseModel):
    """Создание записи о генерации изображения."""
    scene_id: str
    prompt: str
    negative_prompt: Optional[str] = None
    generation_params: Optional[dict] = None
    variant_number: int = Field(1, ge=1, le=4)


class GeneratedImageRead(BaseModel):
    """Чтение информации о сгенерированном изображении."""
    id: str
    scene_id: str
    author_id: str
    task_id: Optional[str]
    prompt: str
    negative_prompt: Optional[str]
    generation_params: Optional[dict]
    image_path: Optional[str]
    thumbnail_path: Optional[str]
    status: str
    moderation_notes: Optional[str]
    moderated_by_id: Optional[str]
    moderated_at: Optional[str]
    variant_number: int
    is_selected: bool
    generation_time_seconds: Optional[int]
    file_size_bytes: Optional[int]
    created_at: str
    updated_at: str

    model_config = {'from_attributes': True}


class GeneratedImageList(BaseModel):
    """Список сгенерированных изображений."""
    items: List[GeneratedImageRead]
    total: int
    page: int
    page_size: int


class ModerationAction(BaseModel):
    """Действие модерации."""
    action: str = Field(..., description="approve или reject")
    notes: Optional[str] = Field(None, description="Комментарий модератора")


class ModerationStats(BaseModel):
    """Статистика модерации."""
    total_images: int
    pending: int
    generating: int
    generated: int
    approved: int
    rejected: int
    failed: int


class ImageSelectionRequest(BaseModel):
    """Запрос на выбор изображения."""
    image_id: str


class BulkModerationRequest(BaseModel):
    """Массовая модерация."""
    image_ids: List[str]
    action: str = Field(..., description="approve или reject")
    notes: Optional[str] = None


class SceneImagesResponse(BaseModel):
    """Изображения сцены."""
    scene_id: str
    images: List[GeneratedImageRead]
    selected_image: Optional[GeneratedImageRead]


class ModerationQueueItem(BaseModel):
    """Элемент очереди модерации."""
    image: GeneratedImageRead
    scene_title: Optional[str]
    quest_title: Optional[str]
    author_username: str

    model_config = {'from_attributes': True}


class ModerationQueueResponse(BaseModel):
    """Очередь модерации."""
    items: List[ModerationQueueItem]
    total: int
    page: int
    page_size: int
