from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.scenario import ScenarioGraphRead, SceneNodeRead, EdgeRead
from app.schemas.projects import ProjectRead
from app.schemas.style_profiles import StyleProfileRead
from app.schemas.legal import LegalConceptRead
from app.schemas.generation_job import ImageVariantRead
from app.schemas.scene_characters_v2 import SceneNodeCharacterRead
from app.schemas.world import ArtifactRead, DocumentTemplateRead, LocationRead, SceneArtifactRead, StyleBibleRead


class SceneExport(BaseModel):
    scene: SceneNodeRead
    characters: List[SceneNodeCharacterRead] = Field(default_factory=list)
    approved_image: Optional[ImageVariantRead] = None
    artifacts: List[SceneArtifactRead] = Field(default_factory=list)
    location: Optional[LocationRead] = None


class ProjectExport(BaseModel):
    project: ProjectRead
    graph: ScenarioGraphRead
    legal_concepts: List[LegalConceptRead] = Field(default_factory=list)
    scenes: List[SceneExport] = Field(default_factory=list)
    style_profile: Optional[StyleProfileRead] = None
    style_bible: Optional[StyleBibleRead] = None
    locations: List[LocationRead] = Field(default_factory=list)
    artifacts: List[ArtifactRead] = Field(default_factory=list)
    document_templates: List[DocumentTemplateRead] = Field(default_factory=list)
