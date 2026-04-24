from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.models import (
    Artifact,
    DocumentTemplate,
    ImageVariant,
    LegalConcept,
    Location,
    Project,
    ScenarioGraph,
    SceneArtifact,
    SceneNode,
    SceneNodeCharacter,
    StyleBible,
    StyleProfile,
)
from app.schemas.export import ProjectExport, SceneExport
from app.schemas.legal import LegalConceptRead


class ExportService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def export_project(self, project_id: str, graph_id: str | None = None) -> Optional[ProjectExport]:
        project_result = await self.session.execute(
            select(Project)
            .options(
                selectinload(Project.style_profile),
                selectinload(Project.style_profiles),
                selectinload(Project.style_bible),
                selectinload(Project.locations),
                selectinload(Project.artifacts),
                selectinload(Project.document_templates),
                selectinload(Project.graphs).selectinload(ScenarioGraph.scenes),
                selectinload(Project.graphs).selectinload(ScenarioGraph.edges),
            )
            .where(Project.id == project_id)
        )
        project = project_result.scalars().unique().one_or_none()
        if project is None:
            return None

        graph_query = (
            select(ScenarioGraph)
            .options(
                selectinload(ScenarioGraph.scenes).selectinload(SceneNode.legal_concepts),
                selectinload(ScenarioGraph.scenes).selectinload(SceneNode.location),
                selectinload(ScenarioGraph.scenes)
                .selectinload(SceneNode.scene_artifacts)
                .selectinload(SceneArtifact.artifact),
                selectinload(ScenarioGraph.edges),
            )
            .where(ScenarioGraph.project_id == project_id, ScenarioGraph.archived_at.is_(None))
            .order_by(ScenarioGraph.created_at.desc())
            .limit(1)
        )
        if graph_id is not None:
            graph_query = graph_query.where(ScenarioGraph.id == graph_id)

        graph = (await self.session.execute(graph_query)).scalars().first()
        if graph is None:
            return None

        # approved images per scene
        approved_images = (
            await self.session.execute(
                select(ImageVariant)
                .where(ImageVariant.scene_id.in_([s.id for s in graph.scenes]))
                .where(ImageVariant.is_approved.is_(True))
            )
        ).scalars().all()
        approved_map = {img.scene_id: img for img in approved_images}

        # scene characters
        scene_chars = (
            await self.session.execute(
                select(SceneNodeCharacter).where(SceneNodeCharacter.scene_id.in_([s.id for s in graph.scenes]))
            )
        ).scalars().all()
        chars_by_scene: dict[str, list[SceneNodeCharacter]] = {}
        for sc in scene_chars:
            chars_by_scene.setdefault(sc.scene_id, []).append(sc)

        # legal concepts referenced
        concept_ids = {lc.id for scene in graph.scenes for lc in (scene.legal_concepts or [])}
        concepts: list[LegalConcept] = []
        if concept_ids:
            concepts = (
                await self.session.execute(select(LegalConcept).where(LegalConcept.id.in_(concept_ids)))
            ).scalars().all()

        scene_exports: list[SceneExport] = []
        for scene in graph.scenes:
            scene_exports.append(
                SceneExport(
                    scene=scene,
                    characters=chars_by_scene.get(scene.id, []),
                    approved_image=approved_map.get(scene.id),
                    artifacts=list(scene.scene_artifacts or []),
                    location=scene.location,
                )
            )

        style_profile = project.style_profile

        return ProjectExport(
            project=project,
            graph=graph,
            legal_concepts=[LegalConceptRead.from_orm(c) for c in concepts],
            scenes=scene_exports,
            style_profile=style_profile,
            style_bible=project.style_bible,
            locations=list(project.locations or []),
            artifacts=list(project.artifacts or []),
            document_templates=list(project.document_templates or []),
        )
