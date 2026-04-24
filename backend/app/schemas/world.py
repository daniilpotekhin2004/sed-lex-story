from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class StyleBibleBase(BaseModel):
    tone: Optional[str] = None
    glossary: Optional[dict] = None
    constraints: Optional[list] = None
    dialogue_format: Optional[dict] = None
    document_format: Optional[dict] = None
    ui_theme: Optional[dict] = None
    narrative_rules: Optional[str] = None


class StyleBibleCreate(StyleBibleBase):
    pass


class StyleBibleUpdate(StyleBibleBase):
    pass


class StyleBibleRead(StyleBibleBase):
    id: str
    project_id: str

    model_config = {'from_attributes': True}


class LocationBase(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    visual_reference: Optional[str] = None
    anchor_token: Optional[str] = None
    negative_prompt: Optional[str] = None
    reference_images: Optional[list] = None
    preview_image_url: Optional[str] = None
    preview_thumbnail_url: Optional[str] = None
    atmosphere_rules: Optional[dict] = None
    tags: Optional[list] = None
    location_metadata: Optional[dict] = None
    is_public: Optional[bool] = None


class LocationCreate(LocationBase):
    pass


class LocationUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    visual_reference: Optional[str] = None
    anchor_token: Optional[str] = None
    negative_prompt: Optional[str] = None
    reference_images: Optional[list] = None
    preview_image_url: Optional[str] = None
    preview_thumbnail_url: Optional[str] = None
    atmosphere_rules: Optional[dict] = None
    tags: Optional[list] = None
    location_metadata: Optional[dict] = None
    is_public: Optional[bool] = None


class LocationRead(LocationBase):
    id: str
    project_id: Optional[str]
    owner_id: Optional[str]
    version: int
    source_location_id: Optional[str]
    source_version: Optional[int]

    model_config = {'from_attributes': True}


class LocationList(BaseModel):
    items: List[LocationRead] = Field(default_factory=list)


class ArtifactBase(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    artifact_type: Optional[str] = None
    legal_significance: Optional[str] = None
    status: Optional[str] = None
    preview_image_url: Optional[str] = None
    preview_thumbnail_url: Optional[str] = None
    artifact_metadata: Optional[dict] = None
    tags: Optional[list] = None
    is_public: Optional[bool] = None


class ArtifactCreate(ArtifactBase):
    pass


class ArtifactUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    artifact_type: Optional[str] = None
    legal_significance: Optional[str] = None
    status: Optional[str] = None
    preview_image_url: Optional[str] = None
    preview_thumbnail_url: Optional[str] = None
    artifact_metadata: Optional[dict] = None
    tags: Optional[list] = None
    is_public: Optional[bool] = None


class ArtifactRead(ArtifactBase):
    id: str
    project_id: Optional[str]
    owner_id: Optional[str]
    version: int
    source_artifact_id: Optional[str]
    source_version: Optional[int]

    model_config = {'from_attributes': True}


class ArtifactList(BaseModel):
    items: List[ArtifactRead] = Field(default_factory=list)


class DocumentTemplateBase(BaseModel):
    name: str = Field(..., max_length=255)
    template_type: Optional[str] = None
    template_body: Optional[str] = None
    placeholders: Optional[dict] = None
    formatting: Optional[dict] = None
    tags: Optional[list] = None
    is_public: Optional[bool] = None


class DocumentTemplateCreate(DocumentTemplateBase):
    pass


class DocumentTemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    template_type: Optional[str] = None
    template_body: Optional[str] = None
    placeholders: Optional[dict] = None
    formatting: Optional[dict] = None
    tags: Optional[list] = None
    is_public: Optional[bool] = None


class DocumentTemplateRead(DocumentTemplateBase):
    id: str
    project_id: Optional[str]
    owner_id: Optional[str]
    version: int
    source_template_id: Optional[str]
    source_version: Optional[int]

    model_config = {'from_attributes': True}


class DocumentTemplateList(BaseModel):
    items: List[DocumentTemplateRead] = Field(default_factory=list)


class SceneArtifactInput(BaseModel):
    artifact_id: str
    state: Optional[str] = None
    notes: Optional[str] = None
    importance: float = Field(1.0, ge=0.0, le=1.0)


class SceneArtifactRead(BaseModel):
    id: str
    scene_id: str
    artifact_id: str
    state: Optional[str]
    notes: Optional[str]
    importance: float
    artifact: Optional[ArtifactRead] = None

    model_config = {'from_attributes': True}
