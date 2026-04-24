from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_material_set_service
from app.schemas.material_sets import MaterialSetCreate, MaterialSetList, MaterialSetRead
from app.services.material_sets import MaterialSetService

router = APIRouter(prefix="/v1", tags=["material-sets"])


@router.get(
    "/projects/{project_id}/material-sets",
    response_model=MaterialSetList,
)
async def list_material_sets(
    project_id: str,
    asset_type: str | None = None,
    asset_id: str | None = None,
    service: MaterialSetService = Depends(get_material_set_service),
) -> MaterialSetList:
    items = await service.list_material_sets(project_id, asset_type=asset_type, asset_id=asset_id)
    return MaterialSetList(items=items)


@router.post(
    "/projects/{project_id}/material-sets",
    response_model=MaterialSetRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_material_set(
    project_id: str,
    payload: MaterialSetCreate,
    service: MaterialSetService = Depends(get_material_set_service),
) -> MaterialSetRead:
    if payload.asset_type not in {"character", "location"}:
        raise HTTPException(status_code=400, detail="Invalid asset_type")
    material = await service.create_material_set(project_id, payload)
    return material
