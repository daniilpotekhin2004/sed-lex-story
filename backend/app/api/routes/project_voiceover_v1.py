from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.schemas.project_voiceover import (
    ProjectVoiceoverApproveLineRequest,
    ProjectVoiceoverGenerateAllRequest,
    ProjectVoiceoverGenerateAllResponse,
    ProjectVoiceoverGenerateLineRequest,
    ProjectVoiceoverLineActionResponse,
    ProjectVoiceoverRead,
    ProjectVoiceoverSettingsResponse,
    ProjectVoiceoverSettingsUpdateRequest,
)
from app.services.project_voiceover import ProjectVoiceoverService


router = APIRouter(prefix="/v1/projects", tags=["project-voiceover"])


@router.get("/{project_id}/voiceover", response_model=ProjectVoiceoverRead)
async def get_project_voiceover(
    project_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> ProjectVoiceoverRead:
    service = ProjectVoiceoverService(session)
    result = await service.get_project_voiceover(project_id)
    return ProjectVoiceoverRead(**result)


@router.patch(
    "/{project_id}/voiceover/settings",
    response_model=ProjectVoiceoverSettingsResponse,
)
async def update_project_voiceover_settings(
    project_id: str,
    payload: ProjectVoiceoverSettingsUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ProjectVoiceoverSettingsResponse:
    service = ProjectVoiceoverService(session)
    result = await service.update_settings(
        project_id,
        patch=payload.model_dump(exclude_unset=True),
    )
    return ProjectVoiceoverSettingsResponse(**result)


@router.post(
    "/{project_id}/voiceover/generate-all",
    response_model=ProjectVoiceoverGenerateAllResponse,
)
async def generate_project_voiceover_all(
    project_id: str,
    payload: ProjectVoiceoverGenerateAllRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ProjectVoiceoverGenerateAllResponse:
    service = ProjectVoiceoverService(session)
    result = await service.generate_all_variants(
        project_id,
        language=payload.language,
        default_voice_profile=payload.default_voice_profile,
        replace_existing=payload.replace_existing,
        skip_approved=payload.skip_approved,
    )
    return ProjectVoiceoverGenerateAllResponse(**result)


@router.post(
    "/{project_id}/voiceover/lines/generate",
    response_model=ProjectVoiceoverLineActionResponse,
)
async def generate_project_voiceover_line(
    project_id: str,
    payload: ProjectVoiceoverGenerateLineRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ProjectVoiceoverLineActionResponse:
    service = ProjectVoiceoverService(session)
    result = await service.generate_line_variant(
        project_id,
        line_id=payload.line_id,
        language=payload.language,
        voice_profile=payload.voice_profile,
        replace_existing=payload.replace_existing,
    )
    return ProjectVoiceoverLineActionResponse(**result)


@router.post(
    "/{project_id}/voiceover/lines/approve",
    response_model=ProjectVoiceoverLineActionResponse,
)
async def approve_project_voiceover_line(
    project_id: str,
    payload: ProjectVoiceoverApproveLineRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ProjectVoiceoverLineActionResponse:
    service = ProjectVoiceoverService(session)
    result = await service.approve_variant(
        project_id,
        line_id=payload.line_id,
        variant_id=payload.variant_id,
    )
    return ProjectVoiceoverLineActionResponse(**result)
