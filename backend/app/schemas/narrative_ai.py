from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class NarrativeScriptLine(BaseModel):
    """Single line/beat that can be narrated via TTS."""

    kind: str = Field(..., pattern="^(exposition|thought|dialogue)$")
    text: str = Field(..., min_length=1)

    # Optional speaker metadata.
    speaker_name: Optional[str] = None
    character_id: Optional[str] = None
    emotion: Optional[str] = None


class AISceneDraftRequest(BaseModel):
    """Generate a draft for a single SceneNode (story or decision)."""

    instruction: Optional[str] = Field(
        None,
        description="What should happen in this scene (free-form).",
    )
    language: str = Field("ru", description="Output language")
    detail_level: str = Field("standard", description="narrow|standard|detailed")

    # Plot context controls
    previous_scene_id: Optional[str] = Field(
        None,
        description="If provided, draft the next scene after this one.",
    )
    target_total_scenes: Optional[int] = Field(
        None,
        ge=2,
        le=50,
        description="If known, helps the model place the scene in the overall arc.",
    )

    # Audio / script
    sound_mode: bool = Field(
        False,
        description="If true, include a scene script (lines) suitable for TTS.",
    )
    include_render_hints: bool = Field(
        True,
        description="If true, include render hints (shot/lighting/mood) in context.",
    )


class AISceneDraftResponse(BaseModel):
    title: str
    synopsis: str
    content: str
    scene_type: str = Field("story", pattern="^(story|decision)$")
    order_index: Optional[int] = None

    # Suggested attachments
    location_id: Optional[str] = None
    suggested_character_ids: List[str] = Field(default_factory=list)
    script: List[NarrativeScriptLine] = Field(default_factory=list)
    context: Dict[str, Any] = Field(default_factory=dict)

    # For decision scenes
    choices: List[Dict[str, Any]] = Field(default_factory=list)

    model: Optional[str] = None
    usage: Optional[dict] = None
    request_id: Optional[str] = None


class AIScenarioDraftRequest(BaseModel):
    """Generate a branching scenario draft for a project."""

    target_scenes: int = Field(8, ge=2, le=50)
    max_branching: int = Field(
        2,
        ge=1,
        le=4,
        description="Max number of choices per decision node.",
    )
    language: str = Field("ru")
    detail_level: str = Field("standard")
    extra_context: Optional[str] = None
    sound_mode: bool = False

    # Persistence
    persist: bool = Field(
        False,
        description="If true, create graph+scenes+edges in DB and return ids.",
    )
    graph_title: Optional[str] = None
    graph_description: Optional[str] = None


class AIScenarioDraftScene(BaseModel):
    temp_id: str
    title: str
    synopsis: str
    content: str
    scene_type: str = Field("story", pattern="^(story|decision)$")
    order_index: int
    location_id: Optional[str] = None
    suggested_character_ids: List[str] = Field(default_factory=list)
    script: List[NarrativeScriptLine] = Field(default_factory=list)
    context: Dict[str, Any] = Field(default_factory=dict)
    choices: List[Dict[str, Any]] = Field(default_factory=list)

    # Filled only when persist=True
    scene_id: Optional[str] = None


class AIScenarioDraftEdge(BaseModel):
    from_temp_id: str
    to_temp_id: str
    choice_label: Optional[str] = None
    condition: Optional[str] = None

    # Filled only when persist=True
    edge_id: Optional[str] = None


class AIScenarioDraftResponse(BaseModel):
    graph_title: str
    graph_description: Optional[str] = None
    scenes: List[AIScenarioDraftScene]
    edges: List[AIScenarioDraftEdge] = Field(default_factory=list)

    # Filled only when persist=True
    graph_id: Optional[str] = None
    root_scene_id: Optional[str] = None

    model: Optional[str] = None
    usage: Optional[dict] = None
    request_id: Optional[str] = None


class SceneTTSSynthesizeRequest(BaseModel):
    """Generate per-line audio for a SceneNode script."""

    language: str = Field("ru")
    overwrite: bool = Field(False)

    # If context/script is missing, we can synthesize the whole scene as narration.
    fallback_mode: str = Field(
        "narration",
        description="narration|none",
    )


class SceneTTSSynthesizeResponse(BaseModel):
    success: bool
    audio_items: List[Dict[str, Any]] = Field(default_factory=list)
    message: Optional[str] = None


class CharacterVoiceSampleRequest(BaseModel):
    """Generate a short voice sample for a CharacterPreset."""

    language: str = Field("ru")
    sample_text: Optional[str] = Field(
        None,
        description="If omitted, a short default phrase will be used.",
    )
    overwrite: bool = Field(False)


class CharacterVoiceSampleResponse(BaseModel):
    success: bool
    voice_profile: Optional[str] = None
    audio_url: Optional[str] = None
    message: Optional[str] = None
