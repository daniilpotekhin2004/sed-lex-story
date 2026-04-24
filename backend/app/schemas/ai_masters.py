from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


MasterIntent = Literal[
    "scenario_draft",
    "scene_draft",
    "entity_draft",
    "renderspec_compile",
    "character_voice_sample",
    "scene_tts",
]


class AIMasterDispatchRequest(BaseModel):
    """Dispatch request for AI masters (optional creative mode).

    This endpoint is intentionally generic so the frontend can use one entrypoint while
    the backend routes the request to the correct master implementation.
    """

    intent: MasterIntent = Field(..., description="Which master to invoke.")
    # Raw payload passed to the underlying master. It will be validated per intent.
    payload: Dict[str, Any] = Field(default_factory=dict)
    # Additional routing fields used by some masters.
    project_id: Optional[str] = None
    graph_id: Optional[str] = None
    scene_id: Optional[str] = None
    preset_id: Optional[str] = None


class AIMasterDispatchResponse(BaseModel):
    intent: MasterIntent
    result: Dict[str, Any] = Field(default_factory=dict)
