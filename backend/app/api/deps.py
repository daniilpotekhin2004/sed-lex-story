from __future__ import annotations

from typing import AsyncGenerator

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db import get_session
from app.services.generation import ImageGenerationService
from app.services.quests import QuestService
from app.services.projects import ProjectService
from app.services.scenario import ScenarioService
from app.services.legal import LegalConceptService
from app.services.style_profiles import StyleProfileService
from app.services.generation_job import GenerationJobService
from app.services.material_sets import MaterialSetService
from app.services.player import PlayerService
from app.services.project_releases import ProjectReleaseService
from app.services.world import WorldService
from app.services.wizard import WizardService
from app.utils.sd_provider import SDProviderOverrides


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_session():
        yield session


def get_quest_service(session: AsyncSession = Depends(get_db_session)) -> QuestService:
    return QuestService(session)


def get_generation_service() -> ImageGenerationService:
    return ImageGenerationService()


def get_project_service(session: AsyncSession = Depends(get_db_session)) -> ProjectService:
    return ProjectService(session)


def get_scenario_service(session: AsyncSession = Depends(get_db_session)) -> ScenarioService:
    return ScenarioService(session)


def get_legal_concept_service(
    session: AsyncSession = Depends(get_db_session),
) -> LegalConceptService:
    return LegalConceptService(session)


def get_style_profile_service(
    session: AsyncSession = Depends(get_db_session),
) -> StyleProfileService:
    return StyleProfileService(session)


def get_generation_service_v2(
    session: AsyncSession = Depends(get_db_session),
) -> GenerationJobService:
    return GenerationJobService(session)


def get_material_set_service(
    session: AsyncSession = Depends(get_db_session),
) -> MaterialSetService:
    return MaterialSetService(session)


def get_player_service(session: AsyncSession = Depends(get_db_session)) -> PlayerService:
    return PlayerService(session)


def get_project_release_service(
    session: AsyncSession = Depends(get_db_session),
) -> ProjectReleaseService:
    return ProjectReleaseService(session)


def get_world_service(session: AsyncSession = Depends(get_db_session)) -> WorldService:
    return WorldService(session)


def get_wizard_service(session: AsyncSession = Depends(get_db_session)) -> WizardService:
    return WizardService(session)


def get_sd_overrides(
    x_sd_provider: str | None = Header(None, alias="X-SD-Provider"),
    x_comfy_api_key: str | None = Header(None, alias="X-Comfy-Api-Key"),
    x_comfy_api_url: str | None = Header(None, alias="X-Comfy-Api-Url"),
    x_poe_api_key: str | None = Header(None, alias="X-Poe-Api-Key"),
    x_poe_api_url: str | None = Header(None, alias="X-Poe-Api-Url"),
    x_poe_model: str | None = Header(None, alias="X-Poe-Model"),
) -> SDProviderOverrides:
    return SDProviderOverrides(
        provider=x_sd_provider,
        comfy_api_key=x_comfy_api_key,
        comfy_url=x_comfy_api_url,
        poe_api_key=x_poe_api_key,
        poe_url=x_poe_api_url,
        poe_model=x_poe_model,
    ).normalized()

