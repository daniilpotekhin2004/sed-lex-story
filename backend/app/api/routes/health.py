from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/api/health")
async def api_health() -> dict:
    return {"status": "ok"}


@router.get("/version")
async def version() -> dict:
    settings = get_settings()
    return {"version": settings.version, "environment": settings.environment}
