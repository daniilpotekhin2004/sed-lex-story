from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


RenderMode = Literal["generation", "multipass"]


class RenderSpecCompileRequest(BaseModel):
    """Compile a scene into a render spec compatible with existing endpoints."""

    mode: RenderMode = Field("multipass", description="Target pipeline")
    width: Optional[int] = Field(None, ge=256, le=2048)
    height: Optional[int] = Field(None, ge=256, le=2048)
    num_variants: Optional[int] = Field(None, ge=1, le=8, description="Only for generation mode")
    pipeline_profile_id: Optional[str] = None
    pipeline_profile_version: Optional[int] = None
    include_controlnet: bool = Field(False, description="Add ControlNet hints if present")
    include_ip_adapter: bool = Field(False, description="Add IP-Adapter hints if present")
    persist: bool = Field(False, description="If true, store spec under scene.context['render_spec']")


class RenderSpecCompileResponse(BaseModel):
    mode: RenderMode
    spec: Dict[str, Any] = Field(default_factory=dict)
    stored: bool = False
    warnings: list[str] = Field(default_factory=list)
