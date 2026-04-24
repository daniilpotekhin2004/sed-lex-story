from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

VoiceoverKind = Literal["scene_narration", "exposition", "thought", "dialogue"]


class ProjectVoiceoverVariantRead(BaseModel):
    id: str
    audio_url: str
    content_type: Optional[str] = None
    language: Optional[str] = None
    voice_profile: Optional[str] = None
    created_at: Optional[str] = None


class ProjectVoiceoverLineRead(BaseModel):
    id: str
    scene_id: str
    scene_title: str
    scene_order: int
    slide_index: Optional[int] = None
    slide_title: Optional[str] = None
    kind: VoiceoverKind
    speaker: Optional[str] = None
    character_id: Optional[str] = None
    dialogue_id: Optional[str] = None
    dialogue_index: Optional[int] = None
    voice_profile: Optional[str] = None
    text: str
    order: int
    variants: List[ProjectVoiceoverVariantRead] = Field(default_factory=list)
    approved_variant_id: Optional[str] = None
    approved_audio_url: Optional[str] = None


class ProjectVoiceoverSummary(BaseModel):
    total_lines: int = 0
    generated_lines: int = 0
    approved_lines: int = 0
    total_variants: int = 0


class ProjectVoiceoverRolePrompts(BaseModel):
    narrator: Optional[str] = None
    inner_voice: Optional[str] = None
    interlocutor: Optional[str] = None


class ProjectVoiceoverSettings(BaseModel):
    language: Optional[str] = None
    voice_profile: Optional[str] = None
    role_prompts: ProjectVoiceoverRolePrompts = Field(default_factory=ProjectVoiceoverRolePrompts)
    character_prompts: Dict[str, str] = Field(default_factory=dict)
    speaker_prompts: Dict[str, str] = Field(default_factory=dict)


class ProjectVoiceoverRead(BaseModel):
    project_id: str
    graph_id: str
    lines: List[ProjectVoiceoverLineRead] = Field(default_factory=list)
    summary: ProjectVoiceoverSummary
    settings: ProjectVoiceoverSettings = Field(default_factory=ProjectVoiceoverSettings)
    suggested_role_prompts: ProjectVoiceoverRolePrompts = Field(default_factory=ProjectVoiceoverRolePrompts)
    updated_at: Optional[str] = None


class ProjectVoiceoverGenerateLineRequest(BaseModel):
    line_id: str = Field(..., min_length=1)
    language: str = Field("ru", min_length=2, max_length=16)
    voice_profile: Optional[str] = None
    replace_existing: bool = False


class ProjectVoiceoverApproveLineRequest(BaseModel):
    line_id: str = Field(..., min_length=1)
    variant_id: str = Field(..., min_length=1)


class ProjectVoiceoverGenerateAllRequest(BaseModel):
    language: str = Field("ru", min_length=2, max_length=16)
    default_voice_profile: Optional[str] = None
    replace_existing: bool = False
    skip_approved: bool = True


class ProjectVoiceoverSettingsUpdateRequest(BaseModel):
    language: Optional[str] = None
    voice_profile: Optional[str] = None
    role_prompts: Optional[ProjectVoiceoverRolePrompts] = None
    character_prompts: Optional[Dict[str, str]] = None
    speaker_prompts: Optional[Dict[str, str]] = None


class ProjectVoiceoverLineActionResponse(BaseModel):
    project_id: str
    graph_id: str
    line: ProjectVoiceoverLineRead
    summary: ProjectVoiceoverSummary
    settings: ProjectVoiceoverSettings = Field(default_factory=ProjectVoiceoverSettings)
    suggested_role_prompts: ProjectVoiceoverRolePrompts = Field(default_factory=ProjectVoiceoverRolePrompts)


class ProjectVoiceoverGenerateAllResponse(BaseModel):
    project_id: str
    graph_id: str
    generated_count: int
    skipped_count: int
    summary: ProjectVoiceoverSummary
    settings: ProjectVoiceoverSettings = Field(default_factory=ProjectVoiceoverSettings)
    suggested_role_prompts: ProjectVoiceoverRolePrompts = Field(default_factory=ProjectVoiceoverRolePrompts)


class ProjectVoiceoverSettingsResponse(BaseModel):
    project_id: str
    graph_id: str
    settings: ProjectVoiceoverSettings = Field(default_factory=ProjectVoiceoverSettings)
    suggested_role_prompts: ProjectVoiceoverRolePrompts = Field(default_factory=ProjectVoiceoverRolePrompts)
    updated_at: Optional[str] = None
