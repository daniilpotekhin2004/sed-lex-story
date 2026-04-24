from typing import Optional

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_world_service
from app.core.deps import get_db_session, require_author
from app.domain.models import User, GenerationTaskType
from app.schemas.world import (
    ArtifactCreate,
    ArtifactList,
    ArtifactRead,
    ArtifactUpdate,
    DocumentTemplateCreate,
    DocumentTemplateList,
    DocumentTemplateRead,
    DocumentTemplateUpdate,
    LocationCreate,
    LocationList,
    LocationRead,
    LocationUpdate,
    StyleBibleCreate,
    StyleBibleRead,
    StyleBibleUpdate,
)
from app.schemas.generation_overrides import GenerationOverrides
from app.schemas.generation_job import AssetGenerationJobCreate, GenerationJobRead
from app.services.generation_job import GenerationJobService
from app.services.asset_uploads import read_uploaded_image
from app.services.world import WorldService

router = APIRouter(prefix="/v1", tags=["world"])


@router.get("/projects/{project_id}/style-bible", response_model=StyleBibleRead)
async def get_style_bible(
    project_id: str,
    service: WorldService = Depends(get_world_service),
) -> StyleBibleRead:
    bible = await service.get_style_bible(project_id)
    if bible is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Style bible not found")
    return bible


@router.put("/projects/{project_id}/style-bible", response_model=StyleBibleRead)
async def upsert_style_bible(
    project_id: str,
    payload: StyleBibleCreate | StyleBibleUpdate,
    service: WorldService = Depends(get_world_service),
) -> StyleBibleRead:
    bible = await service.upsert_style_bible(project_id, payload)
    if bible is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return bible


@router.get("/projects/{project_id}/locations", response_model=LocationList)
async def list_locations(
    project_id: str,
    service: WorldService = Depends(get_world_service),
) -> LocationList:
    items = await service.list_locations(project_id)
    return LocationList(items=items)


@router.post(
    "/projects/{project_id}/locations",
    response_model=LocationRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_location(
    project_id: str,
    payload: LocationCreate,
    service: WorldService = Depends(get_world_service),
) -> LocationRead:
    location = await service.create_location(project_id, payload)
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return location


@router.get("/locations/{location_id}", response_model=LocationRead)
async def get_location(
    location_id: str,
    service: WorldService = Depends(get_world_service),
) -> LocationRead:
    location = await service.get_location(location_id)
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    return location


@router.patch("/locations/{location_id}", response_model=LocationRead)
async def update_location(
    location_id: str,
    payload: LocationUpdate,
    unsafe: bool = Query(False, description="Allow overwriting imported assets"),
    service: WorldService = Depends(get_world_service),
) -> LocationRead:
    location = await service.update_location(location_id, payload, unsafe=unsafe)
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    return location


@router.post(
    "/locations/{location_id}/sketch",
    response_model=GenerationJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_location_sketch(
    location_id: str,
    overrides: Optional[GenerationOverrides] = Body(None),
    current_user: User = Depends(require_author),
    db: AsyncSession = Depends(get_db_session),
) -> GenerationJobRead:
    service = GenerationJobService(db)
    job = await service.create_asset_job(
        AssetGenerationJobCreate(
            task_type=GenerationTaskType.LOCATION_SKETCH,
            entity_type="location",
            entity_id=location_id,
            overrides=overrides,
        ),
        user_id=current_user.id,
    )
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    return job




@router.post(
    "/locations/{location_id}/sheet",
    response_model=GenerationJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_location_sheet(
    location_id: str,
    overrides: Optional[GenerationOverrides] = Body(None),
    current_user: User = Depends(require_author),
    db: AsyncSession = Depends(get_db_session),
) -> GenerationJobRead:
    """Enqueue generation of a small reference set (establishing/interior/detail) for a location."""
    service = GenerationJobService(db)
    job = await service.create_asset_job(
        AssetGenerationJobCreate(
            task_type=GenerationTaskType.LOCATION_SHEET,
            entity_type="location",
            entity_id=location_id,
            overrides=overrides,
        ),
        user_id=current_user.id,
    )
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    return job


@router.post("/locations/{location_id}/preview/upload", response_model=LocationRead)
async def upload_location_preview(
    location_id: str,
    file: UploadFile = File(...),
    unsafe: bool = Query(False, description="Allow overwriting imported assets"),
    current_user: User = Depends(require_author),
    service: WorldService = Depends(get_world_service),
) -> LocationRead:
    image_bytes, filename = await read_uploaded_image(file)
    location = await service.upload_location_preview(
        location_id,
        user_id=current_user.id,
        image_bytes=image_bytes,
        filename=filename,
        unsafe=unsafe,
    )
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    return location


@router.post("/locations/{location_id}/references/{kind}/upload", response_model=LocationRead)
async def upload_location_reference(
    location_id: str,
    kind: str,
    file: UploadFile = File(...),
    set_as_preview: bool = Form(False),
    unsafe: bool = Query(False, description="Allow overwriting imported assets"),
    current_user: User = Depends(require_author),
    service: WorldService = Depends(get_world_service),
) -> LocationRead:
    image_bytes, filename = await read_uploaded_image(file)
    location = await service.upload_location_reference(
        location_id,
        kind,
        user_id=current_user.id,
        image_bytes=image_bytes,
        filename=filename,
        unsafe=unsafe,
        set_as_preview=set_as_preview,
    )
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    return location


@router.post(
    "/projects/{project_id}/locations/import",
    response_model=LocationRead,
    status_code=status.HTTP_201_CREATED,
)
async def import_location(
    project_id: str,
    location_id: str = Query(..., description="Studio location id"),
    current_user: User = Depends(require_author),
    service: WorldService = Depends(get_world_service),
) -> LocationRead:
    location = await service.import_location(project_id, location_id, current_user.id)
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    return location
@router.delete("/locations/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_location(
    location_id: str,
    service: WorldService = Depends(get_world_service),
) -> None:
    ok = await service.delete_location(location_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")


@router.get("/projects/{project_id}/artifacts", response_model=ArtifactList)
async def list_artifacts(
    project_id: str,
    service: WorldService = Depends(get_world_service),
) -> ArtifactList:
    items = await service.list_artifacts(project_id)
    return ArtifactList(items=items)


@router.post(
    "/projects/{project_id}/artifacts",
    response_model=ArtifactRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_artifact(
    project_id: str,
    payload: ArtifactCreate,
    service: WorldService = Depends(get_world_service),
) -> ArtifactRead:
    artifact = await service.create_artifact(project_id, payload)
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return artifact


@router.get("/artifacts/{artifact_id}", response_model=ArtifactRead)
async def get_artifact(
    artifact_id: str,
    service: WorldService = Depends(get_world_service),
) -> ArtifactRead:
    artifact = await service.get_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
    return artifact


@router.patch("/artifacts/{artifact_id}", response_model=ArtifactRead)
async def update_artifact(
    artifact_id: str,
    payload: ArtifactUpdate,
    unsafe: bool = Query(False, description="Allow overwriting imported assets"),
    service: WorldService = Depends(get_world_service),
) -> ArtifactRead:
    artifact = await service.update_artifact(artifact_id, payload, unsafe=unsafe)
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
    return artifact


@router.post(
    "/artifacts/{artifact_id}/sketch",
    response_model=GenerationJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_artifact_sketch(
    artifact_id: str,
    current_user: User = Depends(require_author),
    db: AsyncSession = Depends(get_db_session),
    overrides: GenerationOverrides | None = Body(None),
) -> GenerationJobRead:
    service = GenerationJobService(db)
    job = await service.create_asset_job(
        AssetGenerationJobCreate(
            task_type=GenerationTaskType.ARTIFACT_SKETCH,
            entity_type="artifact",
            entity_id=artifact_id,
            overrides=overrides,
        ),
        user_id=current_user.id,
    )
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
    return job


@router.post("/artifacts/{artifact_id}/preview/upload", response_model=ArtifactRead)
async def upload_artifact_preview(
    artifact_id: str,
    file: UploadFile = File(...),
    unsafe: bool = Query(False, description="Allow overwriting imported assets"),
    current_user: User = Depends(require_author),
    service: WorldService = Depends(get_world_service),
) -> ArtifactRead:
    image_bytes, filename = await read_uploaded_image(file)
    artifact = await service.upload_artifact_preview(
        artifact_id,
        user_id=current_user.id,
        image_bytes=image_bytes,
        filename=filename,
        unsafe=unsafe,
    )
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
    return artifact


@router.post(
    "/projects/{project_id}/artifacts/import",
    response_model=ArtifactRead,
    status_code=status.HTTP_201_CREATED,
)
async def import_artifact(
    project_id: str,
    artifact_id: str = Query(..., description="Studio artifact id"),
    current_user: User = Depends(require_author),
    service: WorldService = Depends(get_world_service),
) -> ArtifactRead:
    artifact = await service.import_artifact(project_id, artifact_id, current_user.id)
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
    return artifact


@router.delete("/artifacts/{artifact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_artifact(
    artifact_id: str,
    service: WorldService = Depends(get_world_service),
) -> None:
    ok = await service.delete_artifact(artifact_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")


@router.get("/projects/{project_id}/document-templates", response_model=DocumentTemplateList)
async def list_document_templates(
    project_id: str,
    service: WorldService = Depends(get_world_service),
) -> DocumentTemplateList:
    items = await service.list_document_templates(project_id)
    return DocumentTemplateList(items=items)


@router.post(
    "/projects/{project_id}/document-templates",
    response_model=DocumentTemplateRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_document_template(
    project_id: str,
    payload: DocumentTemplateCreate,
    service: WorldService = Depends(get_world_service),
) -> DocumentTemplateRead:
    doc = await service.create_document_template(project_id, payload)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return doc


@router.get("/document-templates/{template_id}", response_model=DocumentTemplateRead)
async def get_document_template(
    template_id: str,
    service: WorldService = Depends(get_world_service),
) -> DocumentTemplateRead:
    doc = await service.get_document_template(template_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return doc


@router.patch("/document-templates/{template_id}", response_model=DocumentTemplateRead)
async def update_document_template(
    template_id: str,
    payload: DocumentTemplateUpdate,
    unsafe: bool = Query(False, description="Allow overwriting imported assets"),
    service: WorldService = Depends(get_world_service),
) -> DocumentTemplateRead:
    doc = await service.update_document_template(template_id, payload, unsafe=unsafe)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return doc


@router.post(
    "/projects/{project_id}/document-templates/import",
    response_model=DocumentTemplateRead,
    status_code=status.HTTP_201_CREATED,
)
async def import_document_template(
    project_id: str,
    template_id: str = Query(..., description="Studio document template id"),
    current_user: User = Depends(require_author),
    service: WorldService = Depends(get_world_service),
) -> DocumentTemplateRead:
    doc = await service.import_document_template(project_id, template_id, current_user.id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document template not found")
    return doc


@router.delete("/document-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document_template(
    template_id: str,
    service: WorldService = Depends(get_world_service),
) -> None:
    ok = await service.delete_document_template(template_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
