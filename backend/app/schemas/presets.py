from typing import List, Optional

from pydantic import BaseModel


class SimplePreset(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    preview_thumbnail_url: Optional[str] = None


class PresetsResponse(BaseModel):
    characters: List[SimplePreset]
    loras: List[SimplePreset]
