from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class MaterialSetBase(BaseModel):
    asset_type: str = Field(..., description="character|location")
    asset_id: str
    label: str
    reference_images: Optional[list] = None
    material_metadata: Optional[dict] = None


class MaterialSetCreate(MaterialSetBase):
    pass


class MaterialSetRead(MaterialSetBase):
    id: str
    project_id: str
    created_at: datetime
    updated_at: datetime

    model_config = {'from_attributes': True}


class MaterialSetList(BaseModel):
    items: List[MaterialSetRead] = Field(default_factory=list)
