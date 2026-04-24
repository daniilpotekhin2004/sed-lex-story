from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.legal import LegalConceptRead
from app.schemas.world import LocationRead, SceneArtifactInput, SceneArtifactRead


class ScenarioGraphCreate(BaseModel):
    project_id: str
    title: str = Field(..., max_length=255)
    description: Optional[str] = None
    root_scene_id: Optional[str] = None


class ScenarioGraphUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    root_scene_id: Optional[str] = None


class ScenarioGraphRead(BaseModel):
    model_config = {'from_attributes': True}
    
    id: str
    project_id: str
    title: str
    description: Optional[str]
    root_scene_id: Optional[str]
    scenes: List["SceneNodeRead"] = Field(default_factory=list)
    edges: List["EdgeRead"] = Field(default_factory=list)


class SceneNodeCreate(BaseModel):
    title: str
    content: str
    synopsis: Optional[str] = None
    scene_type: Optional[str] = Field("story", pattern="^(story|decision)$")
    order_index: Optional[int] = None
    context: Optional[dict] = None
    location_id: Optional[str] = None
    location_material_set_id: Optional[str] = None
    location_overrides: Optional[dict] = None
    artifacts: Optional[List[SceneArtifactInput]] = None
    legal_concept_ids: Optional[List[str]] = None


class SceneNodeUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    synopsis: Optional[str] = None
    scene_type: Optional[str] = Field(None, pattern="^(story|decision)$")
    order_index: Optional[int] = None
    context: Optional[dict] = None
    location_id: Optional[str] = None
    location_material_set_id: Optional[str] = None
    location_overrides: Optional[dict] = None
    artifacts: Optional[List[SceneArtifactInput]] = None
    legal_concept_ids: Optional[List[str]] = None


class SceneNodeRead(BaseModel):
    model_config = {'from_attributes': True}
    
    id: str
    graph_id: str
    location_id: Optional[str]
    location_material_set_id: Optional[str]
    title: str
    content: str
    synopsis: Optional[str]
    scene_type: str
    order_index: Optional[int]
    context: Optional[dict]
    location_overrides: Optional[dict]
    location: Optional[LocationRead] = None
    artifacts: List[SceneArtifactRead] = Field(default_factory=list)
    legal_concepts: List[LegalConceptRead] = Field(default_factory=list)


class EdgeCreate(BaseModel):
    from_scene_id: str
    to_scene_id: str
    condition: Optional[str] = None
    choice_label: Optional[str] = None
    edge_metadata: Optional[dict] = None


class EdgeRead(BaseModel):
    model_config = {'from_attributes': True}
    
    id: str
    graph_id: str
    from_scene_id: str
    to_scene_id: str
    condition: Optional[str]
    choice_label: Optional[str]
    edge_metadata: Optional[dict]


class EdgeUpdate(BaseModel):
    choice_label: Optional[str] = None
    condition: Optional[str] = None
    edge_metadata: Optional[dict] = None


class GraphValidationIssue(BaseModel):
    code: str
    severity: str
    message: str
    scene_id: Optional[str] = None
    edge_id: Optional[str] = None
    metadata: Optional[dict] = None


class GraphValidationReport(BaseModel):
    graph_id: str
    issues: List[GraphValidationIssue] = Field(default_factory=list)
    summary: dict = Field(default_factory=dict)


class SceneUsageItem(BaseModel):
    scene_id: str
    title: str
    scene_type: str
    reason: str


class SceneUsageResponse(BaseModel):
    items: List[SceneUsageItem] = Field(default_factory=list)


ScenarioGraphRead.update_forward_refs()
SceneNodeRead.update_forward_refs()
