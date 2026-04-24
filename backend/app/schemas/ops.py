from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class ServiceStatus(BaseModel):
    id: str
    name: str
    status: str
    url: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    details: Optional[dict] = None
    actions: List[str] = Field(default_factory=list)
    controllable: bool = False
    last_checked_at: datetime


class OpsStatusResponse(BaseModel):
    services: List[ServiceStatus] = Field(default_factory=list)
    compose_available: bool = False
    project_root: Optional[str] = None


class ServiceControlRequest(BaseModel):
    action: str = Field(..., description="start | restart | stop")


class ServiceControlResult(BaseModel):
    success: bool
    command: str
    output: Optional[str] = None
    service: Optional[ServiceStatus] = None
    error: Optional[str] = None
