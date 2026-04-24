from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


EntityKind = Literal["character", "location", "artifact"]


class EntityDraftRequest(BaseModel):
    """Request to draft (and optionally persist) an entity."""

    kind: EntityKind = Field(..., description="Which entity to create")
    instruction: str = Field(..., min_length=1, description="Natural language description")
    language: str = Field("ru", description="Language hint")
    author_id: Optional[str] = Field(None, description="Author/user id (required to persist character presets)")


    project_id: Optional[str] = Field(
        None,
        description="If set, create project-scoped entity for locations/artifacts. Characters default to studio presets.",
    )
    studio: bool = Field(
        True,
        description="If true and kind is location/artifact, create a studio entity (project_id=None) owned by the caller.",
    )
    is_public: bool = Field(False, description="Mark as public if supported")
    persist: bool = Field(False, description="If true, persist into DB")

    tags: Optional[list[str]] = None
    style: Optional[str] = None
    safety_notes: Optional[str] = None


class EntityDraftResponse(BaseModel):
    kind: EntityKind
    draft: Dict[str, Any] = Field(default_factory=dict, description="Create payload compatible with existing schemas")
    created_id: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
    llm: Optional[dict] = None
