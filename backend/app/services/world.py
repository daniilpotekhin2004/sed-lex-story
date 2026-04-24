from __future__ import annotations

from datetime import datetime
from typing import Awaitable, Callable, List, Optional
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Artifact, DocumentTemplate, Location, Project, StyleBible, StyleProfile, GenerationJob
from app.infra.sd_request_layer import get_sd_layer
from app.services.prompt_templates import PromptTemplateLibrary
from app.services.visuals import VisualGenerationService
from app.utils.sd_tokens import collect_lora_tokens
from app.schemas.generation_overrides import GenerationOverrides
from app.schemas.world import (
    ArtifactCreate,
    ArtifactUpdate,
    DocumentTemplateCreate,
    DocumentTemplateUpdate,
    LocationCreate,
    LocationUpdate,
    StyleBibleCreate,
    StyleBibleUpdate,
)
from app.services.asset_metadata import (
    build_generated_marker,
    build_uploaded_marker,
    merge_ref_meta,
    upsert_asset_marker,
)
from app.services.asset_uploads import save_uploaded_image


class WorldService:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _mark_location_preview_generated(self, location: Location, *, slot: str = "preview") -> None:
        location.location_metadata = upsert_asset_marker(
            location.location_metadata,
            "preview",
            build_generated_marker(asset_kind="preview", slot=slot),
        )

    def _mark_artifact_preview_generated(self, artifact: Artifact, *, slot: str = "preview") -> None:
        artifact.artifact_metadata = upsert_asset_marker(
            artifact.artifact_metadata,
            "preview",
            build_generated_marker(asset_kind="preview", slot=slot),
        )

    def _ensure_world_owner_access(self, owner_id: Optional[str], user_id: str) -> None:
        if owner_id and owner_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    async def upload_location_preview(
        self,
        location_id: str,
        *,
        user_id: str,
        image_bytes: bytes,
        filename: str,
        unsafe: bool = False,
    ) -> Optional[Location]:
        location = await self._get_active_location(location_id)
        if location is None:
            return None
        if location.project_id is None:
            self._ensure_world_owner_access(location.owner_id, user_id)
        if location.project_id and location.source_location_id and not unsafe:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Imported location is locked. Pass unsafe=true to overwrite.",
            )
        previous_preview = location.preview_image_url
        url = save_uploaded_image("locations", location.id, "preview", image_bytes)
        location.preview_image_url = url
        location.preview_thumbnail_url = url
        location.location_metadata = upsert_asset_marker(
            location.location_metadata,
            "preview",
            build_uploaded_marker(
                filename=filename,
                asset_kind="preview",
                slot="preview",
                replaced_url=previous_preview,
            ),
        )
        await self.session.commit()
        await self.session.refresh(location)
        return location

    async def upload_location_reference(
        self,
        location_id: str,
        kind: str,
        *,
        user_id: str,
        image_bytes: bytes,
        filename: str,
        unsafe: bool = False,
        set_as_preview: bool = False,
    ) -> Optional[Location]:
        location = await self._get_active_location(location_id)
        if location is None:
            return None
        if location.project_id is None:
            self._ensure_world_owner_access(location.owner_id, user_id)
        if location.project_id and location.source_location_id and not unsafe:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Imported location is locked. Pass unsafe=true to overwrite.",
            )
        existing_refs = [ref for ref in (location.reference_images or []) if isinstance(ref, dict)]
        previous_ref = next((ref for ref in existing_refs if ref.get("kind") == kind), None)
        previous_url = previous_ref.get("url") if isinstance(previous_ref, dict) else None
        previous_preview = location.preview_image_url
        url = save_uploaded_image("locations", location.id, kind or "reference", image_bytes)
        item = {
            "id": f"{kind}-{location.id}-{uuid4().hex[:8]}",
            "kind": kind,
            "url": url,
            "thumb_url": url,
            "meta": merge_ref_meta(
                None,
                build_uploaded_marker(
                    filename=filename,
                    asset_kind="reference",
                    slot=kind,
                    replaced_url=previous_url,
                ),
            ),
        }
        location.reference_images = [ref for ref in existing_refs if ref.get("kind") != kind] + [item]
        if set_as_preview:
            location.preview_image_url = url
            location.preview_thumbnail_url = url
            location.location_metadata = upsert_asset_marker(
                location.location_metadata,
                "preview",
                build_uploaded_marker(
                    filename=filename,
                    asset_kind="preview",
                    slot=kind,
                    replaced_url=previous_preview,
                ),
            )
        await self.session.commit()
        await self.session.refresh(location)
        return location

    async def upload_artifact_preview(
        self,
        artifact_id: str,
        *,
        user_id: str,
        image_bytes: bytes,
        filename: str,
        unsafe: bool = False,
    ) -> Optional[Artifact]:
        artifact = await self._get_active_artifact(artifact_id)
        if artifact is None:
            return None
        if artifact.project_id is None:
            self._ensure_world_owner_access(artifact.owner_id, user_id)
        if artifact.project_id and artifact.source_artifact_id and not unsafe:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Imported artifact is locked. Pass unsafe=true to overwrite.",
            )
        previous_preview = artifact.preview_image_url
        url = save_uploaded_image("artifacts", artifact.id, "preview", image_bytes)
        artifact.preview_image_url = url
        artifact.preview_thumbnail_url = url
        artifact.artifact_metadata = upsert_asset_marker(
            artifact.artifact_metadata,
            "preview",
            build_uploaded_marker(
                filename=filename,
                asset_kind="preview",
                slot="preview",
                replaced_url=previous_preview,
            ),
        )
        await self.session.commit()
        await self.session.refresh(artifact)
        return artifact

    async def _get_active_project(self, project_id: str) -> Optional[Project]:
        result = await self.session.execute(
            select(Project).where(
                Project.id == project_id,
                Project.archived_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def _get_active_location(self, location_id: str) -> Optional[Location]:
        result = await self.session.execute(
            select(Location).where(
                Location.id == location_id,
                Location.archived_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def _get_active_artifact(self, artifact_id: str) -> Optional[Artifact]:
        result = await self.session.execute(
            select(Artifact).where(
                Artifact.id == artifact_id,
                Artifact.archived_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def _get_active_document_template(self, template_id: str) -> Optional[DocumentTemplate]:
        result = await self.session.execute(
            select(DocumentTemplate).where(
                DocumentTemplate.id == template_id,
                DocumentTemplate.archived_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_style_bible(self, project_id: str) -> Optional[StyleBible]:
        result = await self.session.execute(
            select(StyleBible).where(StyleBible.project_id == project_id)
        )
        return result.scalar_one_or_none()

    async def upsert_style_bible(
        self,
        project_id: str,
        payload: StyleBibleCreate | StyleBibleUpdate,
    ) -> Optional[StyleBible]:
        project = await self._get_active_project(project_id)
        if project is None:
            return None

        existing = await self.get_style_bible(project_id)
        if existing:
            for field, value in payload.dict(exclude_unset=True).items():
                setattr(existing, field, value)
            await self.session.commit()
            await self.session.refresh(existing)
            return existing

        bible = StyleBible(project_id=project_id, **payload.dict(exclude_unset=True))
        self.session.add(bible)
        await self.session.commit()
        await self.session.refresh(bible)
        return bible

    async def list_locations(self, project_id: str) -> List[Location]:
        result = await self.session.execute(
            select(Location).where(
                Location.project_id == project_id,
                Location.archived_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def list_studio_locations(
        self,
        user_id: Optional[str],
        *,
        only_public: bool = False,
        only_mine: bool = False,
    ) -> List[Location]:
        query = select(Location).where(
            Location.project_id.is_(None),
            Location.archived_at.is_(None),
        )
        if only_public:
            query = query.where(Location.is_public.is_(True))
        elif only_mine and user_id:
            query = query.where(Location.owner_id == user_id)
        elif user_id:
            query = query.where(or_(Location.owner_id == user_id, Location.is_public.is_(True)))
        else:
            query = query.where(Location.is_public.is_(True))
        result = await self.session.execute(query.order_by(Location.created_at.desc()))
        return list(result.scalars().all())

    async def create_location(self, project_id: str, payload: LocationCreate) -> Optional[Location]:
        project = await self._get_active_project(project_id)
        if project is None:
            return None

        data = payload.dict(exclude_unset=True)
        # Auto-generate a stable diffusion-friendly anchor token if not provided
        if not data.get("anchor_token"):
            data["anchor_token"] = f"wlloc_{uuid4().hex[:8]}"
        location = Location(project_id=project_id, **data)
        self.session.add(location)
        await self.session.commit()

        await self.session.refresh(location)
        return location

    async def create_studio_location(self, payload: LocationCreate, owner_id: str) -> Location:
        data = payload.dict(exclude_unset=True)
        if not data.get("anchor_token"):
            data["anchor_token"] = f"wlloc_{uuid4().hex[:8]}"
        location = Location(project_id=None, owner_id=owner_id, **data)
        self.session.add(location)
        await self.session.commit()
        await self.session.refresh(location)
        return location

    async def get_location(self, location_id: str) -> Optional[Location]:
        return await self._get_active_location(location_id)

    async def update_location(
        self,
        location_id: str,
        payload: LocationUpdate,
        *,
        unsafe: bool = False,
    ) -> Optional[Location]:
        location = await self._get_active_location(location_id)
        if location is None:
            return None

        job: GenerationJob | None = None
        if job_id:
            job = await self.session.get(GenerationJob, job_id)
            if job is not None:
                job.stage = 'location_sheet'
                job.progress = 0
                await self.session.commit()
        if location.project_id and location.source_location_id and not unsafe:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Imported location is locked. Pass unsafe=true to overwrite.",
            )

        for field, value in payload.dict(exclude_unset=True).items():
            setattr(location, field, value)
        if location.project_id is None:
            location.version = (location.version or 1) + 1
        await self.session.commit()
        await self.session.refresh(location)
        return location

    async def update_studio_location(
        self,
        location_id: str,
        payload: LocationUpdate,
        owner_id: str,
    ) -> Optional[Location]:
        location = await self._get_active_location(location_id)
        if location is None or location.project_id is not None:
            return None
        if location.owner_id != owner_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        for field, value in payload.dict(exclude_unset=True).items():
            setattr(location, field, value)
        location.version = (location.version or 1) + 1
        await self.session.commit()
        await self.session.refresh(location)
        return location

    async def delete_location(self, location_id: str) -> bool:
        location = await self._get_active_location(location_id)
        if location is None:
            return False
        location.archived_at = datetime.utcnow()
        await self.session.commit()
        return True

    async def import_location(self, project_id: str, location_id: str, user_id: Optional[str]) -> Optional[Location]:
        source = await self._get_active_location(location_id)
        if source is None or source.project_id is not None:
            return None
        if not source.is_public and source.owner_id and source.owner_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        data = {
            "name": source.name,
            "description": source.description,
            "visual_reference": source.visual_reference,
            "anchor_token": source.anchor_token,
            "negative_prompt": source.negative_prompt,
            "reference_images": source.reference_images,
            "preview_image_url": source.preview_image_url,
            "preview_thumbnail_url": source.preview_thumbnail_url,
            "atmosphere_rules": source.atmosphere_rules,
            "tags": source.tags,
            "location_metadata": source.location_metadata,
            "project_id": project_id,
            "owner_id": source.owner_id,
            "is_public": False,
            "source_location_id": source.id,
            "source_version": source.version,
            "version": source.version or 1,
        }
        location = Location(**data)
        self.session.add(location)
        await self.session.commit()
        await self.session.refresh(location)
        return location

    async def list_artifacts(self, project_id: str) -> List[Artifact]:
        result = await self.session.execute(
            select(Artifact).where(
                Artifact.project_id == project_id,
                Artifact.archived_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def list_studio_artifacts(
        self,
        user_id: Optional[str],
        *,
        only_public: bool = False,
        only_mine: bool = False,
    ) -> List[Artifact]:
        query = select(Artifact).where(
            Artifact.project_id.is_(None),
            Artifact.archived_at.is_(None),
        )
        if only_public:
            query = query.where(Artifact.is_public.is_(True))
        elif only_mine and user_id:
            query = query.where(Artifact.owner_id == user_id)
        elif user_id:
            query = query.where(or_(Artifact.owner_id == user_id, Artifact.is_public.is_(True)))
        else:
            query = query.where(Artifact.is_public.is_(True))
        result = await self.session.execute(query.order_by(Artifact.created_at.desc()))
        return list(result.scalars().all())

    async def create_artifact(self, project_id: str, payload: ArtifactCreate) -> Optional[Artifact]:
        project = await self._get_active_project(project_id)
        if project is None:
            return None

        artifact = Artifact(project_id=project_id, **payload.dict(exclude_unset=True))
        self.session.add(artifact)
        await self.session.commit()
        await self.session.refresh(artifact)
        return artifact

    async def create_studio_artifact(self, payload: ArtifactCreate, owner_id: str) -> Artifact:
        artifact = Artifact(project_id=None, owner_id=owner_id, **payload.dict(exclude_unset=True))
        self.session.add(artifact)
        await self.session.commit()
        await self.session.refresh(artifact)
        return artifact

    async def get_artifact(self, artifact_id: str) -> Optional[Artifact]:
        return await self._get_active_artifact(artifact_id)

    async def update_artifact(
        self,
        artifact_id: str,
        payload: ArtifactUpdate,
        *,
        unsafe: bool = False,
    ) -> Optional[Artifact]:
        artifact = await self._get_active_artifact(artifact_id)
        if artifact is None:
            return None
        if artifact.project_id and artifact.source_artifact_id and not unsafe:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Imported artifact is locked. Pass unsafe=true to overwrite.",
            )

        for field, value in payload.dict(exclude_unset=True).items():
            setattr(artifact, field, value)
        if artifact.project_id is None:
            artifact.version = (artifact.version or 1) + 1
        await self.session.commit()
        await self.session.refresh(artifact)
        return artifact

    async def update_studio_artifact(
        self,
        artifact_id: str,
        payload: ArtifactUpdate,
        owner_id: str,
    ) -> Optional[Artifact]:
        artifact = await self._get_active_artifact(artifact_id)
        if artifact is None or artifact.project_id is not None:
            return None
        if artifact.owner_id != owner_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        for field, value in payload.dict(exclude_unset=True).items():
            setattr(artifact, field, value)
        artifact.version = (artifact.version or 1) + 1
        await self.session.commit()
        await self.session.refresh(artifact)
        return artifact

    async def delete_artifact(self, artifact_id: str) -> bool:
        artifact = await self._get_active_artifact(artifact_id)
        if artifact is None:
            return False
        artifact.archived_at = datetime.utcnow()
        await self.session.commit()
        return True

    async def import_artifact(self, project_id: str, artifact_id: str, user_id: Optional[str]) -> Optional[Artifact]:
        source = await self._get_active_artifact(artifact_id)
        if source is None or source.project_id is not None:
            return None
        if not source.is_public and source.owner_id and source.owner_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        data = {
            "name": source.name,
            "description": source.description,
            "artifact_type": source.artifact_type,
            "legal_significance": source.legal_significance,
            "status": source.status,
            "preview_image_url": source.preview_image_url,
            "preview_thumbnail_url": source.preview_thumbnail_url,
            "artifact_metadata": source.artifact_metadata,
            "tags": source.tags,
            "project_id": project_id,
            "owner_id": source.owner_id,
            "is_public": False,
            "source_artifact_id": source.id,
            "source_version": source.version,
            "version": source.version or 1,
        }
        artifact = Artifact(**data)
        self.session.add(artifact)
        await self.session.commit()
        await self.session.refresh(artifact)
        return artifact

    async def list_document_templates(self, project_id: str) -> List[DocumentTemplate]:
        result = await self.session.execute(
            select(DocumentTemplate).where(
                DocumentTemplate.project_id == project_id,
                DocumentTemplate.archived_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def list_studio_document_templates(
        self,
        user_id: Optional[str],
        *,
        only_public: bool = False,
        only_mine: bool = False,
    ) -> List[DocumentTemplate]:
        query = select(DocumentTemplate).where(
            DocumentTemplate.project_id.is_(None),
            DocumentTemplate.archived_at.is_(None),
        )
        if only_public:
            query = query.where(DocumentTemplate.is_public.is_(True))
        elif only_mine and user_id:
            query = query.where(DocumentTemplate.owner_id == user_id)
        elif user_id:
            query = query.where(or_(DocumentTemplate.owner_id == user_id, DocumentTemplate.is_public.is_(True)))
        else:
            query = query.where(DocumentTemplate.is_public.is_(True))
        result = await self.session.execute(query.order_by(DocumentTemplate.created_at.desc()))
        return list(result.scalars().all())

    async def create_document_template(
        self, project_id: str, payload: DocumentTemplateCreate
    ) -> Optional[DocumentTemplate]:
        project = await self._get_active_project(project_id)
        if project is None:
            return None

        doc = DocumentTemplate(project_id=project_id, **payload.dict(exclude_unset=True))
        self.session.add(doc)
        await self.session.commit()
        await self.session.refresh(doc)
        return doc

    async def create_studio_document_template(
        self,
        payload: DocumentTemplateCreate,
        owner_id: str,
    ) -> DocumentTemplate:
        doc = DocumentTemplate(project_id=None, owner_id=owner_id, **payload.dict(exclude_unset=True))
        self.session.add(doc)
        await self.session.commit()
        await self.session.refresh(doc)
        return doc

    async def get_document_template(self, template_id: str) -> Optional[DocumentTemplate]:
        return await self._get_active_document_template(template_id)

    async def update_document_template(
        self, template_id: str, payload: DocumentTemplateUpdate, *, unsafe: bool = False
    ) -> Optional[DocumentTemplate]:
        doc = await self._get_active_document_template(template_id)
        if doc is None:
            return None
        if doc.project_id and doc.source_template_id and not unsafe:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Imported template is locked. Pass unsafe=true to overwrite.",
            )

        for field, value in payload.dict(exclude_unset=True).items():
            setattr(doc, field, value)
        if doc.project_id is None:
            doc.version = (doc.version or 1) + 1
        await self.session.commit()
        await self.session.refresh(doc)
        return doc

    async def update_studio_document_template(
        self,
        template_id: str,
        payload: DocumentTemplateUpdate,
        owner_id: str,
    ) -> Optional[DocumentTemplate]:
        doc = await self._get_active_document_template(template_id)
        if doc is None or doc.project_id is not None:
            return None
        if doc.owner_id != owner_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        for field, value in payload.dict(exclude_unset=True).items():
            setattr(doc, field, value)
        doc.version = (doc.version or 1) + 1
        await self.session.commit()
        await self.session.refresh(doc)
        return doc

    async def delete_document_template(self, template_id: str) -> bool:
        doc = await self._get_active_document_template(template_id)
        if doc is None:
            return False
        doc.archived_at = datetime.utcnow()
        await self.session.commit()
        return True

    async def import_document_template(
        self, project_id: str, template_id: str, user_id: Optional[str]
    ) -> Optional[DocumentTemplate]:
        source = await self._get_active_document_template(template_id)
        if source is None or source.project_id is not None:
            return None
        if not source.is_public and source.owner_id and source.owner_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        data = {
            "name": source.name,
            "template_type": source.template_type,
            "template_body": source.template_body,
            "placeholders": source.placeholders,
            "formatting": source.formatting,
            "tags": source.tags,
            "project_id": project_id,
            "owner_id": source.owner_id,
            "is_public": False,
            "source_template_id": source.id,
            "source_version": source.version,
            "version": source.version or 1,
        }
        doc = DocumentTemplate(**data)
        self.session.add(doc)
        await self.session.commit()
        await self.session.refresh(doc)
        return doc

    async def generate_location_sketch(
        self,
        location_id: str,
        *,
        overrides: Optional[GenerationOverrides] = None,
        style_profile_id: str | None = None,
        job_id: Optional[str] = None,
    ) -> Optional[Location]:
        location = await self._get_active_location(location_id)
        if location is None:
            return None

        job: GenerationJob | None = None
        if job_id:
            job = await self.session.get(GenerationJob, job_id)
            if job is not None:
                job.stage = "location_sketch"
                job.progress = 5
                await self.session.commit()

        is_cloud = self._is_cloud_comfy()
        if is_cloud:
            prompt = self._build_cloud_location_prompt(location)
        else:
            prompt = location.description or location.name
        style = self._resolve_location_style(location)

        # Pull defaults from a style profile (project-level unless overridden) and let overrides win.
        style_profile: StyleProfile | None = None
        if style_profile_id:
            style_profile = await self.session.get(StyleProfile, style_profile_id)
        if style_profile is None:
            style_profile = await self._load_project_style_profile(location.project_id)

        cfg_scale = (
            overrides.cfg_scale
            if overrides and overrides.cfg_scale is not None
            else (style_profile.cfg_scale if style_profile and style_profile.cfg_scale is not None else None)
        )
        steps = (
            overrides.steps
            if overrides and overrides.steps is not None
            else (style_profile.steps if style_profile and style_profile.steps is not None else None)
        )
        sampler = (
            overrides.sampler
            if overrides and overrides.sampler
            else (style_profile.sampler if style_profile and style_profile.sampler else None)
        )
        model_id = overrides.model_id if overrides and overrides.model_id else None
        loras = overrides.loras if overrides and overrides.loras else None
        negative_default = location.negative_prompt or (style_profile.negative_prompt if style_profile else None)
        if is_cloud:
            negative_default = None

        width = overrides.width if overrides and overrides.width else None
        height = overrides.height if overrides and overrides.height else None
        seed = overrides.seed if overrides and overrides.seed is not None else -1

        generator = VisualGenerationService()
        url = await generator.generate_preview(
            f"locations/{location_id}",
            prompt,
            negative_prompt=negative_default,
            width=width,
            height=height,
            seed=seed,
            style=style if style else None,
            model_id=model_id,
            vae_id=overrides.vae_id if overrides else None,
            loras=loras,
            sampler=sampler,
            scheduler=overrides.scheduler if overrides else None,
            cfg_scale=cfg_scale,
            steps=steps,
            use_option_overrides=False,
            workflow_task="location",
        )

        location.preview_image_url = url
        location.preview_thumbnail_url = url
        self._mark_location_preview_generated(location)
        await self.session.commit()
        await self.session.refresh(location)

        if job is not None:
            job.progress = 100
            job.stage = None
            job.results = {
                "entity_type": "location",
                "entity_id": location.id,
                "preview_image_url": location.preview_image_url,
            }
            await self.session.commit()

        return location


    async def generate_location_sheet(
        self,
        location_id: str,
        *,
        overrides: Optional[GenerationOverrides] = None,
        style_profile_id: str | None = None,
        job_id: Optional[str] = None,
        on_progress: Optional[Callable[[int, int, str], Awaitable[None]]] = None,
    ) -> Optional[Location]:
        location = await self._get_active_location(location_id)
        if location is None:
            return None

        job: GenerationJob | None = None
        if job_id:
            job = await self.session.get(GenerationJob, job_id)
            if job is not None:
                job.stage = "location_sheet"
                job.progress = 0
                await self.session.commit()

        # Use stored per-location style settings if available
        style = self._resolve_location_style(location)

        # Generate 4 reference images: exterior, interior, detail, map
        slots = [
            ("exterior", "Wide exterior view, establishing shot"),
            ("interior", "Interior view, main room"),
            ("detail", "Close-up detail, object or feature"),
            ("map", "Top-down map view, simple layout"),
        ]
        total_slots = len(slots)

        generator = VisualGenerationService()

        # Reset existing reference images for these slots
        existing_refs = location.reference_images if location.reference_images else []
        remaining_refs = [r for r in existing_refs if isinstance(r, dict) and r.get("kind") not in {s[0] for s in slots}]
        location.reference_images = remaining_refs
        await self.session.commit()

        width = overrides.width if overrides and overrides.width else None
        height = overrides.height if overrides and overrides.height else None

        # Resolve generation defaults from a style profile (project-level unless overridden) and let overrides win.
        style_profile: StyleProfile | None = None
        if style_profile_id:
            style_profile = await self.session.get(StyleProfile, style_profile_id)
        if style_profile is None:
            style_profile = await self._load_project_style_profile(location.project_id)

        cfg_scale = (
            overrides.cfg_scale
            if overrides and overrides.cfg_scale is not None
            else (style_profile.cfg_scale if style_profile and style_profile.cfg_scale is not None else None)
        )
        steps = (
            overrides.steps
            if overrides and overrides.steps is not None
            else (style_profile.steps if style_profile and style_profile.steps is not None else None)
        )
        sampler = (
            overrides.sampler
            if overrides and overrides.sampler
            else (style_profile.sampler if style_profile and style_profile.sampler else None)
        )
        model_id = (
            overrides.model_id
            if overrides and overrides.model_id
            else (style_profile.model_checkpoint if style_profile and style_profile.model_checkpoint else None)
        )
        loras = (
            overrides.loras
            if overrides and overrides.loras
            else (style_profile.lora_refs if style_profile and style_profile.lora_refs else None)
        )
        scheduler = overrides.scheduler if overrides and overrides.scheduler else None
        vae_id = overrides.vae_id if overrides and overrides.vae_id else None
        is_cloud = self._is_cloud_comfy()
        negative_default = location.negative_prompt or (style_profile.negative_prompt if style_profile else None)
        if is_cloud:
            negative_default = None

        refs: list[dict] = list(remaining_refs)
        for slot_idx, (kind, hint) in enumerate(slots, start=1):
            if is_cloud:
                prompt = self._build_cloud_location_prompt(location, hint)
            else:
                prompt_base = location.description or location.name
                prompt = f"{prompt_base}. {hint}."

            seed_override = None
            if overrides and overrides.seed is not None:
                if overrides.seed == -1:
                    seed_override = None
                else:
                    seed_override = overrides.seed + slot_idx

            url = await generator.generate_preview(
                f"locations/{location_id}/{kind}",
                prompt,
                negative_prompt=negative_default,
                width=width,
                height=height,
                seed=seed_override,
                style=style if style else None,
                model_id=model_id,
                vae_id=vae_id,
                loras=loras,
                sampler=sampler,
                scheduler=scheduler,
                cfg_scale=cfg_scale,
                steps=steps,
                workflow_task="location",
            )

            item = {
                "id": f"{kind}-{location_id}",
                "kind": kind,
                "url": url,
                "thumb_url": url,
                "created_at": None,
                "meta": merge_ref_meta(
                    None,
                    build_generated_marker(asset_kind="reference", slot=kind),
                ),
            }
            refs = [r for r in refs if not (isinstance(r, dict) and r.get("kind") == kind)]
            refs.append(item)
            location.reference_images = refs

            if job is not None:
                job.stage = f"location_sheet {slot_idx}/{total_slots} ({kind})"
                job.progress = int((slot_idx / max(total_slots, 1)) * 100)
                job.results = {
                    "entity_type": "location",
                    "entity_id": location.id,
                    "items": [r for r in (location.reference_images or []) if isinstance(r, dict)],
                    "updated_kind": kind,
                }

            await self.session.commit()
            await self.session.refresh(location)

            if on_progress is not None:
                await on_progress(slot_idx, total_slots, kind)

        if job is not None:
            job.progress = 100
            job.stage = None
            job.results = {
                "entity_type": "location",
                "entity_id": location.id,
                "items": [r for r in (location.reference_images or []) if isinstance(r, dict)],
            }
            await self.session.commit()

        return location


    async def generate_artifact_sketch(
        self,
        artifact_id: str,
        *,
        overrides: Optional[GenerationOverrides] = None,
        style_profile_id: str | None = None,
        job_id: Optional[str] = None,
    ) -> Optional[Artifact]:
        artifact = await self._get_active_artifact(artifact_id)
        if artifact is None:
            return None

        job: GenerationJob | None = None
        if job_id:
            job = await self.session.get(GenerationJob, job_id)
            if job is not None:
                job.stage = "artifact_sketch"
                job.progress = 5
                await self.session.commit()

        name = artifact.name or ""
        description = artifact.description or ""
        prompt = ("Concept art, clean background. " + " ".join([name, description])).strip()
        negative = None

        width = overrides.width if overrides and overrides.width else None
        height = overrides.height if overrides and overrides.height else None
        seed = overrides.seed if overrides and overrides.seed is not None else -1

        # Resolve generation defaults from a style profile (project-level unless overridden) and let overrides win.
        style_profile: StyleProfile | None = None
        if style_profile_id:
            style_profile = await self.session.get(StyleProfile, style_profile_id)
        if style_profile is None and artifact.project_id:
            style_profile = await self._load_project_style_profile(artifact.project_id)

        cfg_scale = overrides.cfg_scale if overrides and overrides.cfg_scale is not None else (
            style_profile.cfg_scale if style_profile and style_profile.cfg_scale is not None else None
        )
        steps = overrides.steps if overrides and overrides.steps is not None else (
            style_profile.steps if style_profile and style_profile.steps is not None else None
        )
        sampler = overrides.sampler if overrides and overrides.sampler else (
            style_profile.sampler if style_profile and style_profile.sampler else None
        )
        model_id = overrides.model_id if overrides and overrides.model_id else None
        loras = overrides.loras if overrides and overrides.loras else None
        if negative is None and style_profile and style_profile.negative_prompt:
            negative = style_profile.negative_prompt

        generator = VisualGenerationService()
        url = await generator.generate_preview(
            f"artifacts/{artifact_id}",
            prompt,
            negative_prompt=negative,
            width=width,
            height=height,
            seed=seed,
            style=None,
            model_id=model_id,
            vae_id=overrides.vae_id if overrides else None,
            loras=loras,
            sampler=sampler,
            scheduler=overrides.scheduler if overrides else None,
            cfg_scale=cfg_scale,
            steps=steps,
            use_option_overrides=False,
        )

        artifact.preview_image_url = url
        artifact.preview_thumbnail_url = url
        self._mark_artifact_preview_generated(artifact)
        await self.session.commit()
        await self.session.refresh(artifact)

        if job is not None:
            job.progress = 100
            job.stage = None
            job.results = {
                "entity_type": "artifact",
                "entity_id": artifact.id,
                "preview_image_url": artifact.preview_image_url,
            }
            await self.session.commit()

        return artifact
    async def _load_project_style_profile(self, project_id: str) -> Optional[StyleProfile]:
        """Load project's active style profile (or the first one) if it exists."""
        project = await self._get_active_project(project_id)
        if project and getattr(project, "style_profile_id", None):
            style = await self.session.get(StyleProfile, project.style_profile_id)
            if style is not None:
                return style

        result = await self.session.execute(
            select(StyleProfile).where(StyleProfile.project_id == project_id).limit(1)
        )
        return result.scalar_one_or_none()

    def _resolve_location_style(self, location: Location) -> Optional[str]:
        meta = location.location_metadata if isinstance(location.location_metadata, dict) else {}
        for key in ("style", "style_prompt", "style_name"):
            value = meta.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _is_cloud_comfy(self) -> bool:
        try:
            sd_layer = get_sd_layer()
            return bool(getattr(sd_layer.client, "_is_cloud", False))
        except Exception:
            return False

    def _build_location_sentence(self, location: Location, hint: Optional[str] = None) -> str:
        def _finish(text: str) -> str:
            cleaned = text.strip()
            if not cleaned:
                return ""
            if cleaned[-1] not in ".!?":
                cleaned += "."
            return cleaned

        parts: list[str] = []
        base = location.description or location.name or ""
        base = _finish(base)
        if base:
            parts.append(base)

        visual = _finish(location.visual_reference or "")
        if visual:
            parts.append(visual)

        if hint:
            hint_text = _finish(hint)
            if hint_text:
                parts.append(hint_text)

        return " ".join(parts).strip()

    def _build_cloud_location_prompt(self, location: Location, hint: Optional[str] = None) -> str:
        sentence = self._build_location_sentence(location, hint)
        tags: list[str] = []
        seen: set[str] = set()

        def _add_tag(tag: str) -> None:
            cleaned = tag.strip()
            if not cleaned:
                return
            lowered = cleaned.lower()
            if lowered in seen:
                return
            seen.add(lowered)
            tags.append(cleaned)

        style = self._resolve_location_style(location)
        if style:
            for part in style.split(","):
                _add_tag(part)

        if location.tags:
            for tag in location.tags:
                _add_tag(str(tag))

        defaults = [
            "cinematic",
            "atmospheric",
            "high detail",
            "realistic",
            "moody lighting",
            "wide shot",
            "photorealistic",
            "dramatic",
        ]
        for tag in defaults:
            if len(tags) >= 8:
                break
            _add_tag(tag)

        if tags:
            if sentence:
                return ", ".join(tags[:8] + [sentence])
            return ", ".join(tags[:8])
        return sentence

    def _build_location_description(self, location: Location) -> str:
        """Build a stable, reusable prompt-like description for a location."""
        parts: list[str] = [location.name]

        # Consistency token for SD (if you train a location LoRA/TI, use the same token)
        if getattr(location, "anchor_token", None):
            parts.append(location.anchor_token)

        if location.description:
            parts.append(location.description)
        if location.visual_reference:
            parts.append(location.visual_reference)
        if location.tags:
            try:
                parts.append("tags: " + ", ".join(str(t) for t in location.tags if t))
            except Exception:
                pass
        if location.atmosphere_rules:
            parts.append(self._stringify_rules(location.atmosphere_rules))

        return ", ".join([part for part in parts if part])

    def _build_artifact_description(self, artifact: Artifact) -> str:
        parts: list[str] = [artifact.name]
        if artifact.description:
            parts.append(artifact.description)
        if artifact.artifact_type:
            parts.append(artifact.artifact_type)
        if artifact.legal_significance:
            parts.append(artifact.legal_significance)
        return ", ".join([part for part in parts if part])

    def _stringify_rules(self, rules: dict) -> str:
        fragments: list[str] = []
        for key, value in rules.items():
            if isinstance(value, (list, tuple)):
                fragments.append(f"{key}: {', '.join(str(v) for v in value)}")
            else:
                fragments.append(f"{key}: {value}")
        return "; ".join(fragments)
