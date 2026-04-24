from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_project_service
from app.core.deps import get_current_active_user
from app.domain.models import User
from app.schemas.projects import ProjectCreate, ProjectList, ProjectRead, ProjectReadWithGraphs, ProjectUpdate
from app.schemas.scenario import ScenarioGraphCreate, ScenarioGraphRead
from app.services.projects import ProjectService

router = APIRouter(prefix="/v1/projects", tags=["projects"])


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    current_user: User = Depends(get_current_active_user),
    service: ProjectService = Depends(get_project_service),
) -> ProjectRead:
    project = await service.create_project(payload, actor=current_user)
    return project


@router.get("", response_model=ProjectList)
async def list_projects(
    current_user: User = Depends(get_current_active_user),
    service: ProjectService = Depends(get_project_service),
) -> ProjectList:
    items = await service.list_projects(current_user)
    return ProjectList(items=[ProjectRead.model_validate(item) for item in items])


@router.get("/{project_id}", response_model=ProjectReadWithGraphs)
async def get_project(
    project_id: str,
    current_user: User = Depends(get_current_active_user),
    service: ProjectService = Depends(get_project_service),
) -> ProjectReadWithGraphs:
    project = await service.get_project(project_id, actor=current_user)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: str,
    payload: ProjectUpdate,
    current_user: User = Depends(get_current_active_user),
    service: ProjectService = Depends(get_project_service),
) -> ProjectRead:
    project = await service.update_project(project_id, payload, actor=current_user)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_project(
    project_id: str,
    current_user: User = Depends(get_current_active_user),
    service: ProjectService = Depends(get_project_service),
) -> None:
    ok = await service.archive_project(project_id, actor=current_user)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@router.post(
    "/{project_id}/graphs",
    response_model=ScenarioGraphRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_graph_for_project(
    project_id: str,
    payload: ScenarioGraphCreate,
    current_user: User = Depends(get_current_active_user),
    service: ProjectService = Depends(get_project_service),
) -> ScenarioGraphRead:
    graph_payload = ScenarioGraphCreate(project_id=project_id, **payload.dict(exclude={"project_id"}))
    graph = await service.create_graph(project_id, graph_payload, actor=current_user)
    if graph is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return graph
