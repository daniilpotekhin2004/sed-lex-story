from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.player import PlayableProjectRead


class PublishProjectReleaseRequest(BaseModel):
    graph_id: Optional[str] = None
    notes: Optional[str] = None


class ReplaceProjectReleaseAccessRequest(BaseModel):
    user_ids: list[str] = Field(default_factory=list)
    cohort_codes: list[str] = Field(default_factory=list)


class ReleaseAssignedUserRead(BaseModel):
    id: str
    username: str
    email: str
    full_name: Optional[str] = None


class ProjectReleaseRead(BaseModel):
    id: str
    project_id: str
    graph_id: str
    version: int
    status: str
    package_version: str
    notes: Optional[str] = None
    published_at: datetime
    archived_at: Optional[datetime] = None
    manifest: PlayableProjectRead
    assigned_users: list[ReleaseAssignedUserRead] = Field(default_factory=list)
    assigned_cohorts: list[str] = Field(default_factory=list)


class ProjectReleaseListResponse(BaseModel):
    items: list[ProjectReleaseRead] = Field(default_factory=list)


class ReleaseCandidateUserListResponse(BaseModel):
    items: list[ReleaseAssignedUserRead] = Field(default_factory=list)
