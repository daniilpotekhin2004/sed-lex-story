from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import require_admin
from app.core.config import clear_settings_cache, get_settings
from app.schemas.ops import OpsStatusResponse, ServiceControlRequest, ServiceControlResult, ServiceStatus
from app.services.ops import OpsService

router = APIRouter(prefix="/v1/ops", tags=["ops"])


@router.post("/reload-config")
async def reload_config(_: object = Depends(require_admin)) -> dict:
    """Reload configuration from .env file."""
    clear_settings_cache()
    settings = get_settings()
    return {
        "status": "ok",
        "sd_api_url": settings.sd_api_url,
        "sd_mock_mode": settings.sd_mock_mode,
    }


@router.get("/services", response_model=OpsStatusResponse)
async def list_services(_: object = Depends(require_admin)) -> OpsStatusResponse:
    service = OpsService()
    services = service.list_services()
    return OpsStatusResponse(
        services=services,
        compose_available=service.compose_available,
        project_root=str(service.compose_file.parent) if service.compose_file else None,
    )


@router.post("/services/{service_id}/control", response_model=ServiceControlResult)
async def control_service(
    service_id: str,
    payload: ServiceControlRequest,
    _: object = Depends(require_admin),
) -> ServiceControlResult:
    service = OpsService()
    success, command, output = await service.control_service(service_id, payload.action)
    if not success:
        return ServiceControlResult(success=False, command=command, output=output, error=output)
    updated = None
    for item in service.list_services():
        if item.id == service_id:
            updated = item
            break
    return ServiceControlResult(success=True, command=command, output=output, service=updated)
