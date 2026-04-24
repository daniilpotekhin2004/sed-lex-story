from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class AdminUserSummary(BaseModel):
    id: str
    username: str
    email: str
    full_name: Optional[str] = None
    cohort_code: Optional[str] = None
    role: str
    is_active: bool
    created_at: datetime
    assets_total: int = 0
    quests_total: int = 0
    completed_jobs_total: int = 0
    comfy_units_total: float = 0.0


class AdminUserListResponse(BaseModel):
    items: list[AdminUserSummary] = Field(default_factory=list)
    total: int
    page: int
    page_size: int
    grouped_counts: dict[str, int] = Field(default_factory=dict)


class RoleUpdateRequest(BaseModel):
    role: str
    reason: Optional[str] = None
    confirm_assign_admin: bool = False


class RoleBulkUpdateRequest(BaseModel):
    user_ids: list[str] = Field(default_factory=list)
    role: str
    reason: Optional[str] = None
    confirm_assign_admin: bool = False


class RoleUpdateResult(BaseModel):
    user_id: str
    previous_role: str
    new_role: str
    changed: bool


class CohortUpdateRequest(BaseModel):
    cohort_code: Optional[str] = Field(None, max_length=64)


class CohortUpdateResult(BaseModel):
    user_id: str
    previous_cohort_code: Optional[str] = None
    cohort_code: Optional[str] = None
    changed: bool


class RoleBulkUpdateResponse(BaseModel):
    updated: int
    skipped: int
    batch_id: Optional[str] = None
    results: list[RoleUpdateResult] = Field(default_factory=list)


class WeeklyMetric(BaseModel):
    week: str
    value: float


class AssetListItem(BaseModel):
    id: str
    type: str
    name: str
    project_id: Optional[str] = None
    created_at: datetime


class QuestListItem(BaseModel):
    id: str
    title: str
    project_id: str
    project_name: Optional[str] = None
    created_at: datetime


class UserAssetStats(BaseModel):
    total: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)
    weekly: list[WeeklyMetric] = Field(default_factory=list)
    items: list[AssetListItem] = Field(default_factory=list)


class UserTimeStats(BaseModel):
    total_seconds: float = 0.0
    total_hours: float = 0.0
    completed_jobs_total: int = 0
    weekly_seconds: list[WeeklyMetric] = Field(default_factory=list)


class UserQuestStats(BaseModel):
    total: int = 0
    weekly: list[WeeklyMetric] = Field(default_factory=list)
    items: list[QuestListItem] = Field(default_factory=list)


class UserComfyStats(BaseModel):
    units_total: float = 0.0
    units_period: float = 0.0
    cost_per_unit_usd: Optional[float] = None
    estimated_spend_total_usd: Optional[float] = None
    estimated_spend_period_usd: Optional[float] = None
    configured_balance_usd: Optional[float] = None
    estimated_remaining_balance_usd: Optional[float] = None
    is_estimated: bool = True


class UserStatsResponse(BaseModel):
    user: AdminUserSummary
    assets: UserAssetStats
    time: UserTimeStats
    quests: UserQuestStats
    comfy: Optional[UserComfyStats] = None


class RoleAggregateStats(BaseModel):
    users: int = 0
    assets_total: int = 0
    quests_total: int = 0
    time_seconds_total: float = 0.0
    comfy_units_total: float = 0.0
    estimated_spend_usd_total: Optional[float] = None


class AdminOverviewResponse(BaseModel):
    users_total: int
    users_by_role: dict[str, int] = Field(default_factory=dict)
    aggregates_by_role: dict[str, RoleAggregateStats] = Field(default_factory=dict)
    generated_at: datetime


class ComfySpendByUser(BaseModel):
    user_id: str
    username: str
    units: float
    estimated_spend_usd: Optional[float] = None


class ComfyOverviewResponse(BaseModel):
    total_units: float
    cost_per_unit_usd: Optional[float] = None
    estimated_spend_total_usd: Optional[float] = None
    configured_balance_usd: Optional[float] = None
    estimated_remaining_balance_usd: Optional[float] = None
    users: list[ComfySpendByUser] = Field(default_factory=list)
    is_estimated: bool = True


class RoleAuditRead(BaseModel):
    id: str
    user_id: str
    actor_user_id: str
    from_role: str
    to_role: str
    reason: Optional[str] = None
    batch_id: Optional[str] = None
    created_at: datetime
    user_username: Optional[str] = None
    actor_username: Optional[str] = None


class RoleAuditListResponse(BaseModel):
    items: list[RoleAuditRead] = Field(default_factory=list)
    total: int
    page: int
    page_size: int


class ErrorFeedItem(BaseModel):
    source: str
    level: str
    message: str
    timestamp: Optional[str] = None


class ErrorFeedResponse(BaseModel):
    items: list[ErrorFeedItem] = Field(default_factory=list)
