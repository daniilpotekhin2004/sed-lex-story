from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class LegalConceptCreate(BaseModel):
    code: str = Field(..., max_length=64)
    title: str = Field(..., max_length=255)
    description: Optional[str] = None
    difficulty: Optional[int] = None
    tags: Optional[List[str]] = None


class LegalConceptRead(BaseModel):
    id: str
    code: str
    title: str
    description: Optional[str]
    difficulty: Optional[int]
    tags: Optional[List[str]]

    model_config = {'from_attributes': True}


class LegalConceptList(BaseModel):
    items: List[LegalConceptRead] = Field(default_factory=list)
