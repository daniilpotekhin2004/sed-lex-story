from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Generic, List, Literal, Optional, TypeVar

from pydantic import BaseModel, Field
from pydantic.generics import GenericModel


WizardMode = Literal["draft", "final"]
WizardMetaStatus = Literal["ok", "warning", "error"]
WizardItemStatus = Literal["draft", "approved", "rejected"]
WizardAssetAction = Literal["create", "update", "skip"]
WizardAssetPriority = Literal["high", "medium", "low"]


class ProjectContext(BaseModel):
    genre: Optional[str] = None
    tone: Optional[str] = None
    style_refs: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    target_audience: Optional[str] = None


class LegalTopicsConfig(BaseModel):
    required: List[str] = Field(default_factory=list)
    optional: List[str] = Field(default_factory=list)
    auto_generate_if_empty: bool = True


class ExistingAssets(BaseModel):
    characters: List[str] = Field(default_factory=list)
    locations: List[str] = Field(default_factory=list)


class WizardPreferences(BaseModel):
    language: str = "ru"
    max_scenes: Optional[int] = Field(None, ge=1, le=50)
    branching: bool = True


class StoryInput(BaseModel):
    input_type: Literal["short_brief", "full_story", "structured"]
    story_text: str = Field(..., min_length=20)
    project_context: Optional[ProjectContext] = None
    legal_topics: Optional[LegalTopicsConfig] = None
    existing_assets: Optional[ExistingAssets] = None
    preferences: Optional[WizardPreferences] = None


class WizardIssue(BaseModel):
    code: str
    message: str
    field: Optional[str] = None
    severity: Optional[Literal["low", "medium", "high"]] = None
    hint: Optional[str] = None


class WizardMeta(BaseModel):
    step: int = Field(..., ge=1)
    mode: WizardMode
    status: WizardMetaStatus
    warnings: List[WizardIssue] = Field(default_factory=list)
    errors: List[WizardIssue] = Field(default_factory=list)
    usage: Optional[Dict[str, Any]] = None
    trace_id: Optional[str] = None
    generated_at: Optional[str] = None


T = TypeVar("T")


class WizardResponse(GenericModel, Generic[T]):
    data: T
    meta: WizardMeta


class WizardSessionCreateRequest(BaseModel):
    project_id: Optional[str] = None
    story_input: StoryInput
    auto_run_step1: bool = False


class WizardSessionUpdateRequest(BaseModel):
    story_input: Optional[StoryInput] = None


class WizardStepRunRequest(BaseModel):
    language: Optional[str] = None
    detail_level: Optional[Literal["narrow", "standard", "detailed"]] = None
    strict: Optional[bool] = None
    force: Optional[bool] = None


class WizardStep7DeployOverrideRequest(BaseModel):
    enabled: bool
    reason: Optional[str] = Field(None, max_length=1000)


class WizardDeployItem(BaseModel):
    id: str
    name: str
    action: Literal["reused", "imported", "created", "skipped", "missing"]
    asset_id: Optional[str] = None
    source: Optional[Literal["project", "library", "wizard", "unknown"]] = None
    note: Optional[str] = None


class WizardDeployReport(BaseModel):
    characters: List[WizardDeployItem] = Field(default_factory=list)
    locations: List[WizardDeployItem] = Field(default_factory=list)


class WizardDeployResponse(BaseModel):
    graph_id: str
    graph_title: str
    scenes_created: int
    edges_created: int
    characters_created: int
    characters_imported: int = 0
    characters_reused: int = 0
    locations_created: int
    locations_imported: int = 0
    locations_reused: int = 0
    warnings: List[WizardIssue] = Field(default_factory=list)
    report: Optional[WizardDeployReport] = None


class WizardExportPackage(BaseModel):
    session_id: str
    project_id: Optional[str] = None
    generated_at: Optional[str] = None
    story_input: Optional[StoryInput] = None
    steps: Dict[str, Any] = Field(default_factory=dict)
    meta: Optional[Dict[str, Any]] = None
    approvals: Optional[Dict[str, Any]] = None
    summary: Optional[Dict[str, Any]] = None


class WizardStepApproveRequest(BaseModel):
    status: Literal["approved", "rejected"]
    notes: Optional[str] = None


class WizardStepSaveRequest(BaseModel):
    data: Dict[str, Any]
    meta: Optional[WizardMeta] = None


class WizardSessionRead(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    project_id: Optional[str] = None
    owner_id: Optional[str] = None
    status: str
    current_step: int
    input_payload: Optional[Dict[str, Any]] = None
    drafts: Optional[Dict[str, Any]] = None
    approvals: Optional[Dict[str, Any]] = None
    meta: Optional[Dict[str, Any]] = None
    last_error: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class Step1Character(BaseModel):
    id: str
    name: str
    summary: str
    role: str
    age: Optional[str] = None
    notes: Optional[str] = None
    confidence: float = Field(..., ge=0, le=1)
    status: WizardItemStatus
    source: Optional[Literal["new", "existing"]] = None
    existing_asset_id: Optional[str] = None


class Step1Location(BaseModel):
    id: str
    name: str
    summary: str
    type: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    confidence: float = Field(..., ge=0, le=1)
    status: WizardItemStatus
    source: Optional[Literal["new", "existing"]] = None
    existing_asset_id: Optional[str] = None


class Step1Scene(BaseModel):
    id: str
    title: str
    summary: str
    location_id: Optional[str] = None
    cast_ids: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    confidence: float = Field(..., ge=0, le=1)
    status: WizardItemStatus


class Step1LegalTopic(BaseModel):
    id: str
    title: str
    summary: str
    status: WizardItemStatus


class Step1Data(BaseModel):
    characters: List[Step1Character] = Field(default_factory=list)
    locations: List[Step1Location] = Field(default_factory=list)
    scenes: List[Step1Scene] = Field(default_factory=list)
    legal_topics: List[Step1LegalTopic] = Field(default_factory=list)


class Step2Appearance(BaseModel):
    age_group: Optional[str] = None
    build: Optional[str] = None
    face_traits: Optional[str] = None
    hair: Optional[str] = None
    accessories: Optional[str] = None
    outfit: Optional[str] = None
    palette: Optional[str] = None
    distinctive_features: Optional[str] = None
    demeanor: Optional[str] = None


class Step2Character(BaseModel):
    id: str
    source: Optional[Literal["new", "existing"]] = None
    existing_asset_id: Optional[str] = None
    name: str
    description: str
    role: str
    character_type: Optional[Literal["protagonist", "antagonist", "supporting", "background"]] = None
    appearance: Step2Appearance
    voice_profile: Optional[str] = None
    motivation: Optional[str] = None
    legal_status: Optional[str] = None
    competencies: Optional[str] = None
    taboo: Optional[str] = None
    style_tags: Optional[str] = None
    prompt: Optional[str] = None
    negative_prompt: Optional[str] = None
    status: WizardItemStatus
    notes: Optional[str] = None


class Step2Location(BaseModel):
    id: str
    source: Optional[Literal["new", "existing"]] = None
    existing_asset_id: Optional[str] = None
    name: str
    description: str
    location_type: Optional[str] = None
    interior_exterior: Optional[str] = None
    era: Optional[str] = None
    time_of_day: Optional[str] = None
    style: Optional[str] = None
    materials: Optional[str] = None
    mood: Optional[str] = None
    props: Optional[str] = None
    tags: Optional[str] = None
    notes: Optional[str] = None
    visual_reference: str
    negative_prompt: Optional[str] = None
    advanced_prompt: Optional[str] = None
    status: WizardItemStatus


class Step2Data(BaseModel):
    characters: List[Step2Character] = Field(default_factory=list)
    locations: List[Step2Location] = Field(default_factory=list)


class Step3DialogueLine(BaseModel):
    speaker: str
    text: str


class Step3Slide(BaseModel):
    id: str
    order: int
    title: Optional[str] = None
    exposition: Optional[str] = None
    thought: Optional[str] = None
    dialogue: List[Step3DialogueLine] = Field(default_factory=list)
    visual: str
    composition_prompt: Optional[str] = None  # Qwen-generated composition prompt for img2img
    cast_ids: List[str] = Field(default_factory=list)
    location_id: Optional[str] = None
    framing: Optional[Literal["full", "half", "portrait"]] = None
    allow_background_extras: Optional[bool] = None
    background_extras_count: Optional[int] = None
    background_extras_min: Optional[int] = None
    background_extras_max: Optional[int] = None
    background_extras_note: Optional[str] = None


class Step3SceneSlides(BaseModel):
    scene_id: str
    slides: List[Step3Slide] = Field(default_factory=list)


class Step3Data(BaseModel):
    scenes: List[Step3SceneSlides] = Field(default_factory=list)


class Step4AssetPlan(BaseModel):
    id: str
    type: Literal["character", "location"]
    source_id: str
    action: WizardAssetAction
    priority: WizardAssetPriority
    dependencies: List[str] = Field(default_factory=list)
    reason: Optional[str] = None
    status: WizardItemStatus


class Step4Data(BaseModel):
    assets: List[Step4AssetPlan] = Field(default_factory=list)


class Step5BranchOption(BaseModel):
    id: str
    label: str
    summary: str
    is_mainline: bool
    next_scenes: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class Step5Branch(BaseModel):
    id: str
    scene_id: Optional[str] = None
    choice_key: str
    choice_prompt: str
    options: List[Step5BranchOption] = Field(default_factory=list)


class Step5Data(BaseModel):
    branches: List[Step5Branch] = Field(default_factory=list)


class Step6Link(BaseModel):
    scene_id: str
    slide_id: Optional[str] = None
    character_ids: List[str] = Field(default_factory=list)
    location_id: Optional[str] = None
    framing: Optional[Literal["full", "half", "portrait"]] = None
    notes: Optional[str] = None


class Step6Data(BaseModel):
    links: List[Step6Link] = Field(default_factory=list)


class Step7Check(BaseModel):
    id: str
    title: str
    status: Literal["pass", "warn", "fail"]
    note: str


class Step7Issue(BaseModel):
    id: str
    severity: Literal["low", "medium", "high"]
    title: str
    description: str
    recommendation: str
    affected_steps: List[int] = Field(default_factory=list)
    affected_ids: List[str] = Field(default_factory=list)
    evidence: Optional[str] = None
    blocking: bool = False
    resolved: bool = False
    resolution_note: Optional[str] = None


class Step7Data(BaseModel):
    overall_summary: str
    verdict: Literal["pass", "revise"]
    continuity_score: int = Field(..., ge=0, le=100)
    checks: List[Step7Check] = Field(default_factory=list)
    issues: List[Step7Issue] = Field(default_factory=list)
