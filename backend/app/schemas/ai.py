from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class AIDescriptionRequest(BaseModel):
    entity_type: str = Field(..., description="character, location, artifact, etc")
    name: str = Field(..., min_length=1, max_length=255)
    context: Optional[str] = Field(None, description="Optional context for the LLM")
    language: str = Field("ru", description="Output language")
    tone: Optional[str] = Field(None, description="Optional tone guidance")


class AIDescriptionResponse(BaseModel):
    description: str
    model: Optional[str] = None
    usage: Optional[dict] = None
    request_id: Optional[str] = None


class AIFieldSpec(BaseModel):
    key: str = Field(..., min_length=1, max_length=120)
    label: Optional[str] = None
    type: str = Field("string", description="string, number, integer, boolean, array, object")
    options: Optional[list[str]] = None
    description: Optional[str] = None


class AIFormFillRequest(BaseModel):
    form_type: str = Field(..., min_length=1, max_length=120)
    fields: list[AIFieldSpec]
    current_values: Optional[dict] = None
    context: Optional[str] = None
    extra_context: Optional[str] = None
    language: str = Field("ru", description="Output language for strings")
    detail_level: str = Field("standard", description="narrow, standard, detailed")
    fill_only_empty: bool = Field(True, description="Only fill empty fields")


class AIFormFillResponse(BaseModel):
    values: dict
    model: Optional[str] = None
    usage: Optional[dict] = None
    request_id: Optional[str] = None


class AIVoicePreviewRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    voice_profile: Optional[str] = Field(None, description="Voice style descriptor for TTS")
    language: str = Field("en", description="Language hint for TTS")
