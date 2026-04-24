from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class PromptBundle(BaseModel):
    prompt: str
    negative_prompt: Optional[str] = None
    config: dict = Field(default_factory=dict)
