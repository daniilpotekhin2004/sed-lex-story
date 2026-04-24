from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel


class TelemetryEventCreate(BaseModel):
    event_name: str
    payload: Optional[Dict[str, Any]] = None


class TelemetryEventRead(BaseModel):
    id: str
    user_id: Optional[str]
    event_name: str
    payload: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime

    model_config = {'from_attributes': True}
