from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class QuestCreate(BaseModel):
    title: str = Field(..., max_length=255)
    description: Optional[str] = None
    audience: Optional[str] = Field(None, max_length=128)


class SceneCreate(BaseModel):
    title: Optional[str] = Field(None, max_length=255)
    text: str
    order: Optional[int] = None


class SceneRead(BaseModel):
    id: str
    quest_id: str
    title: Optional[str]
    text: str
    order: Optional[int]
    image_path: Optional[str] = None

    model_config = {'from_attributes': True}


class QuestRead(BaseModel):
    id: str
    title: str
    description: Optional[str]
    audience: Optional[str]
    scenes: List[SceneRead] = Field(default_factory=list)

    model_config = {'from_attributes': True}
