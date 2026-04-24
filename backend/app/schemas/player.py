from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.export import ProjectExport


class PlayableProjectRead(BaseModel):
    project_id: str
    project_name: str
    project_description: Optional[str] = None
    graph_id: str
    graph_title: str
    graph_description: Optional[str] = None
    root_scene_id: Optional[str] = None
    scene_count: int
    choice_count: int
    package_version: str
    updated_at: datetime


class PlayerCatalogResponse(BaseModel):
    items: List[PlayableProjectRead] = Field(default_factory=list)


class PlayerPackageRead(BaseModel):
    manifest: PlayableProjectRead
    export: ProjectExport


class PlayerRunEventInput(BaseModel):
    id: str = Field(..., max_length=64)
    type: str = Field(..., max_length=64)
    timestamp: datetime
    payload: dict = Field(default_factory=dict)


class PlayerRunSyncRequest(BaseModel):
    run_id: str = Field(..., max_length=64)
    graph_id: str
    package_version: Optional[str] = Field(None, max_length=64)
    current_node_id: Optional[str] = None
    status: Literal["active", "completed"] = "active"
    events: List[PlayerRunEventInput] = Field(default_factory=list)


class PlayerRunSyncResponse(BaseModel):
    run_id: str
    accepted_count: int
    duplicate_count: int
    status: str
    last_synced_at: datetime


class PlayerChoiceAggregateRead(BaseModel):
    choice_id: str
    label: str
    selection_count: int


class PlayerOwnStatsRead(BaseModel):
    total_runs: int = 0
    completed_runs: int = 0
    last_run_id: Optional[str] = None
    last_completed_at: Optional[datetime] = None
    last_synced_at: Optional[datetime] = None
    current_node_id: Optional[str] = None


class PlayerProjectStatsRead(BaseModel):
    project_id: str
    graph_id: str
    package_version: str
    updated_at: datetime
    total_runs: int = 0
    completed_runs: int = 0
    unique_players: int = 0
    completion_rate: float = 0.0
    choices: List[PlayerChoiceAggregateRead] = Field(default_factory=list)
    mine: PlayerOwnStatsRead = Field(default_factory=PlayerOwnStatsRead)


class PlayerResumeRead(BaseModel):
    available: bool = False
    run_id: Optional[str] = None
    graph_id: Optional[str] = None
    package_version: Optional[str] = None
    current_node_id: Optional[str] = None
    status: Optional[Literal["active", "completed"]] = None
    started_at: Optional[datetime] = None
    last_synced_at: Optional[datetime] = None
    scene_history: List[str] = Field(default_factory=list)
    session_values: dict[str, str] = Field(default_factory=dict)
