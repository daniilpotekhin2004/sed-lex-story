from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Project
from app.infra.llm_client import LLMConfigError, create_chat_completion
from app.schemas.characters import CharacterPresetCreate
from app.schemas.entity_ai import EntityDraftRequest, EntityDraftResponse
from app.schemas.world import ArtifactCreate, LocationCreate
from app.services.character import CharacterService
from app.services.world import WorldService

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> Dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {}
    return {}


def _first_line(text: str) -> str:
    return (text or "").strip().split("\n", 1)[0].strip()


def _default_character_payload(instruction: str) -> Dict[str, Any]:
    name = _first_line(instruction)[:64] or "Character"
    return {
        "name": name,
        "description": instruction.strip()[:600],
        "character_type": "supporting",
        "appearance_prompt": instruction.strip()[:800] or "portrait, character",
        "negative_prompt": None,
        "appearance_profile": None,
        "reference_images": None,
        "style_tags": None,
        "voice_profile": None,
        "motivation": None,
        "legal_status": None,
        "competencies": None,
        "relationships": None,
        "artifact_refs": None,
        "is_public": False,
    }


def _default_location_payload(instruction: str) -> Dict[str, Any]:
    name = _first_line(instruction)[:64] or "Location"
    return {
        "name": name,
        "description": instruction.strip()[:800],
        "visual_reference": None,
        "anchor_token": None,
        "negative_prompt": None,
        "reference_images": None,
        "atmosphere_rules": None,
        "tags": None,
        "location_metadata": None,
        "is_public": False,
    }


def _default_artifact_payload(instruction: str) -> Dict[str, Any]:
    name = _first_line(instruction)[:64] or "Artifact"
    return {
        "name": name,
        "description": instruction.strip()[:800],
        "artifact_type": None,
        "legal_significance": None,
        "status": None,
        "preview_image_url": None,
        "preview_thumbnail_url": None,
        "artifact_metadata": None,
        "tags": None,
        "is_public": False,
    }


class EntityAIService:
    """AI master that drafts entities while keeping schema compatibility."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def draft_entity(self, req: EntityDraftRequest) -> EntityDraftResponse:
        warnings: list[str] = []

        project_outline = None
        if req.project_id:
            project = await self.session.get(Project, req.project_id)
            if project is None:
                raise HTTPException(status_code=404, detail="Project not found")
            project_outline = (project.story_outline or project.description or "").strip()[:1200]

        # Schema hints for the LLM (strict JSON only)
        if req.kind == "character":
            schema_hint = (
                "Return a JSON object compatible with CharacterPresetCreate: "
                "{name, description?, character_type(one of protagonist|antagonist|supporting|background), "
                "appearance_prompt, negative_prompt?, appearance_profile?, reference_images?, style_tags?, voice_profile?, "
                "motivation?, legal_status?, competencies?, relationships?, artifact_refs?, is_public?}."
            )
            fallback = _default_character_payload(req.instruction)
        elif req.kind == "location":
            schema_hint = (
                "Return JSON compatible with LocationCreate: "
                "{name, description?, visual_reference?, anchor_token?, negative_prompt?, reference_images?, "
                "atmosphere_rules?, tags?, location_metadata?, is_public?}."
            )
            fallback = _default_location_payload(req.instruction)
        else:
            schema_hint = (
                "Return JSON compatible with ArtifactCreate: "
                "{name, description?, artifact_type?, legal_significance?, status?, preview_image_url?, "
                "preview_thumbnail_url?, artifact_metadata?, tags?, is_public?}."
            )
            fallback = _default_artifact_payload(req.instruction)

        system = (
            "You produce STRICT JSON for entity creation. "
            "Return ONLY a valid JSON object, no markdown, no extra text. "
            "Do not invent fields outside the schema."
        )

        user_parts = [f"Language: {req.language}"]
        if project_outline:
            user_parts.append(f"Project context: {project_outline}")
        if req.tags:
            user_parts.append(f"Tags to include: {req.tags}")
        if req.style:
            user_parts.append(f"Style hint: {req.style}")
        if req.safety_notes:
            user_parts.append(f"Constraints: {req.safety_notes}")
        user_parts.append(f"Instruction: {req.instruction}")
        user_parts.append(schema_hint)
        user = "\n".join(user_parts)

        payload: Dict[str, Any] = fallback
        llm_meta: Optional[dict] = None

        try:
            reply = await create_chat_completion(
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0.7,
                max_tokens=800,
            )
            llm_meta = {"model": reply.get("model"), "usage": reply.get("usage"), "request_id": reply.get("id")}
            text = reply.get("choices", [{}])[0].get("message", {}).get("content", "")
            extracted = _extract_json(text)
            if extracted:
                payload = extracted
            else:
                warnings.append("LLM reply did not contain valid JSON; used fallback payload")
        except LLMConfigError:
            warnings.append("LLM is not configured; used fallback payload")
        except Exception as e:
            logger.exception("entity_ai failed")
            warnings.append(f"LLM failed: {type(e).__name__}; used fallback payload")

        created_id: Optional[str] = None
        if req.persist:
            if req.kind == "character":
                if not req.author_id:
                    warnings.append("author_id is required to persist character presets; returning draft only")
                else:
                    service = CharacterService(self.session)
                    model = CharacterPresetCreate.model_validate(payload)
                    preset = await service.create_preset(model, author_id=req.author_id)
                    created_id = preset.id
            elif req.kind == "location":
                service = WorldService(self.session)
                model = LocationCreate.model_validate(payload)
                if req.studio or not req.project_id:
                    location = await service.create_studio_location(model, owner_id=req.author_id or None)
                else:
                    location = await service.create_location(req.project_id, model)
                if location is None:
                    raise HTTPException(status_code=404, detail="Project not found")
                created_id = location.id
            else:
                service = WorldService(self.session)
                model = ArtifactCreate.model_validate(payload)
                if req.studio or not req.project_id:
                    artifact = await service.create_studio_artifact(model, owner_id=req.author_id or None)
                else:
                    artifact = await service.create_artifact(req.project_id, model)
                if artifact is None:
                    raise HTTPException(status_code=404, detail="Project not found")
                created_id = artifact.id

        return EntityDraftResponse(kind=req.kind, draft=payload, created_id=created_id, warnings=warnings, llm=llm_meta)
