from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_wizard_service
from app.core.deps import get_optional_user
from app.domain.models import User
from app.schemas.wizard import (
    WizardDeployResponse,
    WizardExportPackage,
    WizardSessionCreateRequest,
    WizardSessionRead,
    WizardStep7DeployOverrideRequest,
    WizardSessionUpdateRequest,
    WizardStepApproveRequest,
    WizardStepRunRequest,
    WizardStepSaveRequest,
)
from app.schemas.projects import ProjectRead
from app.services.wizard import WizardService


router = APIRouter(prefix="/v1/wizard", tags=["wizard"])


@router.post("/sessions", response_model=WizardSessionRead, status_code=status.HTTP_201_CREATED)
async def create_wizard_session(
    payload: WizardSessionCreateRequest,
    service: WizardService = Depends(get_wizard_service),
) -> WizardSessionRead:
    session = await service.create_session(payload)
    return WizardSessionRead.model_validate(session)


@router.get("/sessions/latest", response_model=WizardSessionRead)
async def get_latest_wizard_session(
    project_id: str = Query(..., description="Project id"),
    service: WizardService = Depends(get_wizard_service),
) -> WizardSessionRead:
    session = await service.get_latest_session(project_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wizard session not found")
    return WizardSessionRead.model_validate(session)


@router.get("/sessions/{session_id}", response_model=WizardSessionRead)
async def get_wizard_session(
    session_id: str,
    service: WizardService = Depends(get_wizard_service),
) -> WizardSessionRead:
    session = await service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wizard session not found")
    return WizardSessionRead.model_validate(session)


@router.patch("/sessions/{session_id}", response_model=WizardSessionRead)
async def update_wizard_session(
    session_id: str,
    payload: WizardSessionUpdateRequest,
    service: WizardService = Depends(get_wizard_service),
) -> WizardSessionRead:
    session = await service.update_session(session_id, payload)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wizard session not found")
    return WizardSessionRead.model_validate(session)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_wizard_session(
    session_id: str,
    service: WizardService = Depends(get_wizard_service),
) -> None:
    deleted = await service.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wizard session not found")
    return None


@router.get("/sessions/{session_id}/steps/{step}")
async def get_wizard_step(
    session_id: str,
    step: int,
    service: WizardService = Depends(get_wizard_service),
) -> Dict[str, Any]:
    result = await service.get_step(session_id, step)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wizard step not found")
    return result


@router.put("/sessions/{session_id}/steps/{step}")
async def save_wizard_step(
    session_id: str,
    step: int,
    payload: WizardStepSaveRequest,
    service: WizardService = Depends(get_wizard_service),
) -> Dict[str, Any]:
    result = await service.save_step(session_id, step, payload.data, meta=payload.meta)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wizard session not found")
    return result


@router.post("/sessions/{session_id}/steps/{step}/run")
async def run_wizard_step(
    session_id: str,
    step: int,
    payload: WizardStepRunRequest,
    service: WizardService = Depends(get_wizard_service),
) -> Dict[str, Any]:
    return await service.run_step(session_id, step, payload)


@router.post("/sessions/{session_id}/steps/{step}/approve")
async def approve_wizard_step(
    session_id: str,
    step: int,
    payload: WizardStepApproveRequest,
    service: WizardService = Depends(get_wizard_service),
) -> Dict[str, Any]:
    result = await service.approve_step(session_id, step, payload)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wizard session not found")
    return result


@router.get("/sessions/{session_id}/export", response_model=WizardExportPackage)
async def export_wizard_session(
    session_id: str,
    service: WizardService = Depends(get_wizard_service),
) -> WizardExportPackage:
    session = await service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wizard session not found")
    return service.build_export_package(session)


@router.post("/sessions/{session_id}/deploy", response_model=WizardDeployResponse)
async def deploy_wizard_session(
    session_id: str,
    current_user: User | None = Depends(get_optional_user),
    service: WizardService = Depends(get_wizard_service),
) -> WizardDeployResponse:
    author_id = current_user.id if current_user else None
    return await service.deploy_to_project(session_id, author_id=author_id)


@router.post("/sessions/{session_id}/step7/deploy-override", response_model=WizardSessionRead)
async def set_step7_deploy_override(
    session_id: str,
    payload: WizardStep7DeployOverrideRequest,
    current_user: User | None = Depends(get_optional_user),
    service: WizardService = Depends(get_wizard_service),
) -> WizardSessionRead:
    actor_user_id = current_user.id if current_user else None
    session = await service.set_step7_deploy_override(
        session_id=session_id,
        payload=payload,
        actor_user_id=actor_user_id,
    )
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wizard session not found")
    return WizardSessionRead.model_validate(session)


@router.post("/sessions/{session_id}/reset-project", response_model=ProjectRead)
async def reset_wizard_project(
    session_id: str,
    current_user: User | None = Depends(get_optional_user),
    service: WizardService = Depends(get_wizard_service),
) -> ProjectRead:
    author_id = current_user.id if current_user else None
    project = await service.reset_project(session_id, author_id=author_id)
    return ProjectRead.model_validate(project)
