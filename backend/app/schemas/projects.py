from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.style_profiles import StyleProfileRead


class ProjectBase(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    story_outline: Optional[str] = None
    owner_id: Optional[str] = None
    style_profile_id: Optional[str] = None


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    story_outline: Optional[str] = None
    style_profile_id: Optional[str] = None


class ScenarioGraphSummary(BaseModel):
    """Lightweight graph summary for project listing (avoids deep nesting)."""
    model_config = {'from_attributes': True}
    
    id: str
    project_id: str
    title: str
    description: Optional[str]
    root_scene_id: Optional[str]


class ProjectRead(BaseModel):
    model_config = {'from_attributes': True}
    
    id: str
    name: str
    description: Optional[str]
    story_outline: Optional[str]
    owner_id: Optional[str]
    style_profile: Optional[StyleProfileRead] = None


class ProjectReadWithGraphs(BaseModel):
    """Full project with graphs (use for single project fetch)."""
    model_config = {'from_attributes': True}
    
    id: str
    name: str
    description: Optional[str]
    story_outline: Optional[str]
    owner_id: Optional[str]
    style_profile: Optional[StyleProfileRead] = None
    graphs: List[ScenarioGraphSummary] = Field(default_factory=list)


class ProjectList(BaseModel):
    items: List[ProjectRead] = Field(default_factory=list)
