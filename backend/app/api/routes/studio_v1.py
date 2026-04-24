from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_world_service
from app.core.deps import get_current_active_user, get_optional_user, require_author
from app.domain.models import User
from app.schemas.world import (
    LocationCreate,
    LocationList,
    LocationRead,
    LocationUpdate,
    ArtifactCreate,
    ArtifactList,
    ArtifactRead,
    ArtifactUpdate,
    DocumentTemplateCreate,
    DocumentTemplateList,
    DocumentTemplateRead,
    DocumentTemplateUpdate,
)
from app.services.world import WorldService

router = APIRouter(prefix="/v1/studio", tags=["studio-assets"])


@router.get("/locations", response_model=LocationList)
async def list_studio_locations(
    only_public: bool = Query(False),
    only_mine: bool = Query(False),
    current_user: User | None = Depends(get_optional_user),
    service: WorldService = Depends(get_world_service),
) -> LocationList:
    items = await service.list_studio_locations(
        current_user.id if current_user else None,
        only_public=only_public,
        only_mine=only_mine,
    )
    return LocationList(items=items)


@router.post("/locations", response_model=LocationRead, status_code=status.HTTP_201_CREATED)
async def create_studio_location(
    payload: LocationCreate,
    current_user: User = Depends(require_author),
    service: WorldService = Depends(get_world_service),
) -> LocationRead:
    return await service.create_studio_location(payload, current_user.id)


@router.patch("/locations/{location_id}", response_model=LocationRead)
async def update_studio_location(
    location_id: str,
    payload: LocationUpdate,
    current_user: User = Depends(require_author),
    service: WorldService = Depends(get_world_service),
) -> LocationRead:
    location = await service.update_studio_location(location_id, payload, current_user.id)
    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")
    return location


@router.delete("/locations/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_studio_location(
    location_id: str,
    current_user: User = Depends(require_author),
    service: WorldService = Depends(get_world_service),
) -> None:
    ok = await service.delete_location(location_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Location not found")


@router.get("/artifacts", response_model=ArtifactList)
async def list_studio_artifacts(
    only_public: bool = Query(False),
    only_mine: bool = Query(False),
    current_user: User | None = Depends(get_optional_user),
    service: WorldService = Depends(get_world_service),
) -> ArtifactList:
    items = await service.list_studio_artifacts(
        current_user.id if current_user else None,
        only_public=only_public,
        only_mine=only_mine,
    )
    return ArtifactList(items=items)


@router.post("/artifacts", response_model=ArtifactRead, status_code=status.HTTP_201_CREATED)
async def create_studio_artifact(
    payload: ArtifactCreate,
    current_user: User = Depends(require_author),
    service: WorldService = Depends(get_world_service),
) -> ArtifactRead:
    return await service.create_studio_artifact(payload, current_user.id)


@router.patch("/artifacts/{artifact_id}", response_model=ArtifactRead)
async def update_studio_artifact(
    artifact_id: str,
    payload: ArtifactUpdate,
    current_user: User = Depends(require_author),
    service: WorldService = Depends(get_world_service),
) -> ArtifactRead:
    artifact = await service.update_studio_artifact(artifact_id, payload, current_user.id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return artifact


@router.delete("/artifacts/{artifact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_studio_artifact(
    artifact_id: str,
    current_user: User = Depends(require_author),
    service: WorldService = Depends(get_world_service),
) -> None:
    ok = await service.delete_artifact(artifact_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Artifact not found")


@router.get("/document-templates", response_model=DocumentTemplateList)
async def list_studio_document_templates(
    only_public: bool = Query(False),
    only_mine: bool = Query(False),
    current_user: User | None = Depends(get_optional_user),
    service: WorldService = Depends(get_world_service),
) -> DocumentTemplateList:
    items = await service.list_studio_document_templates(
        current_user.id if current_user else None,
        only_public=only_public,
        only_mine=only_mine,
    )
    return DocumentTemplateList(items=items)


@router.post("/document-templates", response_model=DocumentTemplateRead, status_code=status.HTTP_201_CREATED)
async def create_studio_document_template(
    payload: DocumentTemplateCreate,
    current_user: User = Depends(require_author),
    service: WorldService = Depends(get_world_service),
) -> DocumentTemplateRead:
    return await service.create_studio_document_template(payload, current_user.id)


@router.patch("/document-templates/{template_id}", response_model=DocumentTemplateRead)
async def update_studio_document_template(
    template_id: str,
    payload: DocumentTemplateUpdate,
    current_user: User = Depends(require_author),
    service: WorldService = Depends(get_world_service),
) -> DocumentTemplateRead:
    doc = await service.update_studio_document_template(template_id, payload, current_user.id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document template not found")
    return doc


@router.delete("/document-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_studio_document_template(
    template_id: str,
    current_user: User = Depends(require_author),
    service: WorldService = Depends(get_world_service),
) -> None:
    ok = await service.delete_document_template(template_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Document template not found")
