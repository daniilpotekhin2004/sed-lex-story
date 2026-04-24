from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_legal_concept_service, get_scenario_service
from app.core.deps import get_current_active_user
from app.domain.models import User
from app.schemas.scenario import (
    EdgeCreate,
    EdgeRead,
    EdgeUpdate,
    GraphValidationReport,
    SceneNodeCreate,
    SceneNodeRead,
    SceneNodeUpdate,
    SceneUsageResponse,
    ScenarioGraphRead,
    ScenarioGraphUpdate,
)
from app.services.legal import LegalConceptService
from app.services.scenario import ScenarioService, ScenarioValidationError

router = APIRouter(prefix="/v1", tags=["scenario"])


@router.get("/graphs/{graph_id}", response_model=ScenarioGraphRead)
async def get_graph(
    graph_id: str,
    current_user: User = Depends(get_current_active_user),
    service: ScenarioService = Depends(get_scenario_service),
) -> ScenarioGraphRead:
    graph = await service.get_graph(graph_id, actor=current_user)
    if graph is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Graph not found")
    return graph


@router.patch("/graphs/{graph_id}", response_model=ScenarioGraphRead)
async def update_graph(
    graph_id: str,
    payload: ScenarioGraphUpdate,
    current_user: User = Depends(get_current_active_user),
    service: ScenarioService = Depends(get_scenario_service),
) -> ScenarioGraphRead:
    graph = await service.update_graph(graph_id, payload, actor=current_user)
    if graph is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Graph not found")
    return graph


@router.delete("/graphs/{graph_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_graph(
    graph_id: str,
    current_user: User = Depends(get_current_active_user),
    service: ScenarioService = Depends(get_scenario_service),
) -> None:
    ok = await service.archive_graph(graph_id, actor=current_user)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Graph not found")


@router.post(
    "/graphs/{graph_id}/scenes",
    response_model=SceneNodeRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_scene(
    graph_id: str,
    payload: SceneNodeCreate,
    current_user: User = Depends(get_current_active_user),
    service: ScenarioService = Depends(get_scenario_service),
    legal_service: LegalConceptService = Depends(get_legal_concept_service),
) -> SceneNodeRead:
    # Ensure legal concepts exist if provided
    if payload.legal_concept_ids:
        known = await legal_service.get_by_ids(payload.legal_concept_ids)
        if len(known) != len(payload.legal_concept_ids):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown legal concept id")

    try:
        scene = await service.add_scene(graph_id, payload, actor=current_user)
    except ScenarioValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if scene is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Graph not found")
    return scene


@router.patch("/scenes/{scene_id}", response_model=SceneNodeRead)
async def update_scene(
    scene_id: str,
    payload: SceneNodeUpdate,
    current_user: User = Depends(get_current_active_user),
    service: ScenarioService = Depends(get_scenario_service),
    legal_service: LegalConceptService = Depends(get_legal_concept_service),
) -> SceneNodeRead:
    if payload.legal_concept_ids:
        known = await legal_service.get_by_ids(payload.legal_concept_ids)
        if len(known) != len(payload.legal_concept_ids):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown legal concept id")

    try:
        scene = await service.update_scene(scene_id, payload, actor=current_user)
    except ScenarioValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if scene is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")
    return scene


@router.post(
    "/graphs/{graph_id}/edges",
    response_model=EdgeRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_edge(
    graph_id: str,
    payload: EdgeCreate,
    current_user: User = Depends(get_current_active_user),
    service: ScenarioService = Depends(get_scenario_service),
) -> EdgeRead:
    edge = await service.add_edge(graph_id, payload, actor=current_user)
    if edge is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid graph or scenes")
    return edge


@router.patch("/edges/{edge_id}", response_model=EdgeRead)
async def update_edge(
    edge_id: str,
    payload: EdgeUpdate,
    current_user: User = Depends(get_current_active_user),
    service: ScenarioService = Depends(get_scenario_service),
) -> EdgeRead:
    edge = await service.update_edge(edge_id, payload, actor=current_user)
    if edge is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Edge not found")
    return edge


@router.get("/graphs/{graph_id}/validate", response_model=GraphValidationReport)
async def validate_graph(
    graph_id: str,
    current_user: User = Depends(get_current_active_user),
    service: ScenarioService = Depends(get_scenario_service),
) -> GraphValidationReport:
    report = await service.validate_graph(graph_id, actor=current_user)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Graph not found")
    return report


@router.get("/graphs/{graph_id}/usage", response_model=SceneUsageResponse)
async def get_usage(
    graph_id: str,
    location_id: str | None = Query(None),
    character_id: str | None = Query(None),
    artifact_id: str | None = Query(None),
    current_user: User = Depends(get_current_active_user),
    service: ScenarioService = Depends(get_scenario_service),
) -> SceneUsageResponse:
    if not any([location_id, character_id, artifact_id]):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provide a filter")
    items = await service.list_usage(
        graph_id,
        actor=current_user,
        location_id=location_id,
        character_id=character_id,
        artifact_id=artifact_id,
    )
    if items is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Graph not found")
    return SceneUsageResponse(items=items)
