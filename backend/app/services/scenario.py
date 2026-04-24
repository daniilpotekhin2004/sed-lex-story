from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.models import (
    Artifact,
    Edge,
    LegalConcept,
    Location,
    Project,
    SceneArtifact,
    SceneLegalConcept,
    SceneNode,
    ScenarioGraph,
    User,
    UserRole,
)
from app.schemas.scenario import EdgeCreate, EdgeUpdate, SceneNodeCreate, SceneNodeUpdate, ScenarioGraphUpdate


class ScenarioValidationError(Exception):
    pass


class ScenarioService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _get_active_graph_entity(self, graph_id: str, actor: User) -> Optional[ScenarioGraph]:
        query = (
            select(ScenarioGraph)
            .join(Project, Project.id == ScenarioGraph.project_id)
            .where(
                ScenarioGraph.id == graph_id,
                ScenarioGraph.archived_at.is_(None),
                Project.archived_at.is_(None),
            )
        )
        if actor.role != UserRole.ADMIN:
            query = query.where(Project.owner_id == actor.id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_graph(self, graph_id: str, actor: User) -> Optional[ScenarioGraph]:
        query = (
            select(ScenarioGraph)
            .join(Project, Project.id == ScenarioGraph.project_id)
            .options(
                selectinload(ScenarioGraph.scenes).selectinload(SceneNode.legal_concepts),
                selectinload(ScenarioGraph.scenes).selectinload(SceneNode.location),
                selectinload(ScenarioGraph.scenes)
                .selectinload(SceneNode.scene_artifacts)
                .selectinload(SceneArtifact.artifact),
                selectinload(ScenarioGraph.edges),
            )
            .where(
                ScenarioGraph.id == graph_id,
                ScenarioGraph.archived_at.is_(None),
                Project.archived_at.is_(None),
            )
        )
        if actor.role != UserRole.ADMIN:
            query = query.where(Project.owner_id == actor.id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def update_graph(self, graph_id: str, payload: ScenarioGraphUpdate, actor: User) -> Optional[ScenarioGraph]:
        graph = await self._get_active_graph_entity(graph_id, actor=actor)
        if graph is None:
            return None

        for field, value in payload.dict(exclude_unset=True).items():
            setattr(graph, field, value)

        await self.session.commit()
        return await self.get_graph(graph_id, actor=actor)

    async def archive_graph(self, graph_id: str, actor: User) -> bool:
        graph = await self._get_active_graph_entity(graph_id, actor=actor)
        if graph is None:
            return False
        graph.archived_at = datetime.utcnow()
        await self.session.commit()
        return True

    async def add_scene(
        self, graph_id: str, payload: SceneNodeCreate, actor: User
    ) -> Optional[SceneNode]:
        graph = await self._get_active_graph_entity(graph_id, actor=actor)
        if graph is None:
            return None

        if payload.location_id:
            await self._validate_location(payload.location_id, graph.project_id)

        order_index = payload.order_index
        if order_index is None:
            result = await self.session.execute(
                select(func.count()).select_from(SceneNode).where(SceneNode.graph_id == graph_id)
            )
            order_index = (result.scalar_one() or 0) + 1

        scene = SceneNode(
            graph_id=graph_id,
            title=payload.title,
            content=payload.content,
            synopsis=payload.synopsis,
            scene_type=payload.scene_type or "story",
            order_index=order_index,
            context=payload.context,
            location_id=payload.location_id,
            location_material_set_id=payload.location_material_set_id,
            location_overrides=payload.location_overrides,
        )
        self.session.add(scene)
        await self.session.flush()

        if payload.legal_concept_ids:
            await self._set_scene_legal_concepts(scene, payload.legal_concept_ids)

        if payload.artifacts is not None:
            await self._set_scene_artifacts(scene, payload.artifacts, graph.project_id)

        await self.session.commit()
        # Eager load relationships to avoid lazy load issues
        await self.session.refresh(
            scene,
            [
                "graph",
                "legal_concepts",
                "legal_links",
                "outgoing_edges",
                "incoming_edges",
                "scene_characters_v2",
                "location",
                "scene_artifacts",
            ],
        )
        for link in scene.scene_artifacts or []:
            await self.session.refresh(link, ["artifact"])
        return scene

    async def update_scene(
        self, scene_id: str, payload: SceneNodeUpdate, actor: User
    ) -> Optional[SceneNode]:
        scene = await self._get_active_scene_entity(scene_id, actor=actor)
        if scene is None:
            return None
        graph = await self.session.get(ScenarioGraph, scene.graph_id)
        project_id = graph.project_id if graph else None

        update_data = payload.dict(exclude_unset=True, exclude={"legal_concept_ids", "artifacts"})
        if "location_id" in update_data and project_id and update_data["location_id"]:
            await self._validate_location(update_data["location_id"], project_id)

        for field, value in update_data.items():
            setattr(scene, field, value)

        if payload.legal_concept_ids is not None:
            await self._set_scene_legal_concepts(scene, payload.legal_concept_ids)

        if payload.artifacts is not None and project_id:
            await self._set_scene_artifacts(scene, payload.artifacts, project_id)

        await self.session.commit()
        # Eager load relationships to avoid lazy load issues
        await self.session.refresh(
            scene,
            [
                "graph",
                "legal_concepts",
                "legal_links",
                "outgoing_edges",
                "incoming_edges",
                "scene_characters_v2",
                "location",
                "scene_artifacts",
            ],
        )
        for link in scene.scene_artifacts or []:
            await self.session.refresh(link, ["artifact"])
        return scene

    async def add_edge(self, graph_id: str, payload: EdgeCreate, actor: User) -> Optional[Edge]:
        graph = await self._get_active_graph_entity(graph_id, actor=actor)
        if graph is None:
            return None
        # Validate scenes belong to same graph
        from_scene = await self.session.get(SceneNode, payload.from_scene_id)
        to_scene = await self.session.get(SceneNode, payload.to_scene_id)
        if not from_scene or not to_scene:
            return None
        if from_scene.graph_id != graph_id or to_scene.graph_id != graph_id:
            return None

        edge = Edge(
            graph_id=graph_id,
            from_scene_id=payload.from_scene_id,
            to_scene_id=payload.to_scene_id,
            condition=payload.condition,
            choice_label=payload.choice_label,
            edge_metadata=payload.edge_metadata,
        )
        self.session.add(edge)
        await self.session.commit()
        # Eager load relationships to avoid lazy load issues
        await self.session.refresh(edge, ["graph", "from_scene", "to_scene"])
        return edge

    async def list_edges(self, graph_id: str) -> List[Edge]:
        result = await self.session.execute(select(Edge).where(Edge.graph_id == graph_id))
        return list(result.scalars().all())

    async def update_edge(self, edge_id: str, payload: EdgeUpdate, actor: User) -> Optional[Edge]:
        edge = await self._get_active_edge_entity(edge_id, actor=actor)
        if edge is None:
            return None

        update_data = payload.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(edge, field, value)

        await self.session.commit()
        await self.session.refresh(edge, ["graph", "from_scene", "to_scene"])
        return edge

    async def _set_scene_legal_concepts(self, scene: SceneNode, concept_ids: List[str]) -> None:
        await self.session.execute(
            SceneLegalConcept.__table__.delete().where(SceneLegalConcept.scene_id == scene.id)
        )

        if not concept_ids:
            return

        concepts = (
            (await self.session.execute(select(LegalConcept).where(LegalConcept.id.in_(concept_ids))))
            .scalars()
            .all()
        )
        for concept in concepts:
            link = SceneLegalConcept(scene_id=scene.id, concept_id=concept.id)
            self.session.add(link)
        await self.session.flush()

    async def _validate_location(self, location_id: str, project_id: str) -> None:
        location = await self.session.get(Location, location_id)
        if location is None or location.project_id != project_id:
            raise ScenarioValidationError("Invalid location reference")

    async def _set_scene_artifacts(
        self,
        scene: SceneNode,
        artifacts: List,
        project_id: str,
    ) -> None:
        await self.session.execute(
            SceneArtifact.__table__.delete().where(SceneArtifact.scene_id == scene.id)
        )

        if not artifacts:
            return

        artifact_ids = [self._read_artifact_field(item, "artifact_id") for item in artifacts]
        result = await self.session.execute(select(Artifact).where(Artifact.id.in_(artifact_ids)))
        found = {artifact.id: artifact for artifact in result.scalars().all()}
        missing = [artifact_id for artifact_id in artifact_ids if artifact_id not in found]
        if missing:
            raise ScenarioValidationError(f"Unknown artifact ids: {', '.join(missing)}")

        for artifact in found.values():
            if artifact.project_id != project_id:
                raise ScenarioValidationError("Artifact does not belong to project")

        for item in artifacts:
            artifact_id = self._read_artifact_field(item, "artifact_id")
            state = self._read_artifact_field(item, "state")
            notes = self._read_artifact_field(item, "notes")
            importance = self._read_artifact_field(item, "importance", default=1.0)
            link = SceneArtifact(
                scene_id=scene.id,
                artifact_id=artifact_id,
                state=state,
                notes=notes,
                importance=importance,
            )
            self.session.add(link)
        await self.session.flush()

    @staticmethod
    def _read_artifact_field(item, field: str, default=None):
        if hasattr(item, field):
            return getattr(item, field)
        if isinstance(item, dict):
            return item.get(field, default)
        return default

    @staticmethod
    def _is_final_scene(scene: SceneNode) -> bool:
        ctx = scene.context or {}
        return bool(ctx.get("final") or ctx.get("is_final") or ctx.get("finale"))

    async def validate_graph(self, graph_id: str, actor: User) -> Optional[dict]:
        graph = await self.get_graph(graph_id, actor=actor)
        if graph is None:
            return None

        scenes = graph.scenes or []
        edges = graph.edges or []
        scene_ids = {scene.id for scene in scenes}
        outgoing: dict[str, list[str]] = {scene_id: [] for scene_id in scene_ids}
        issues: list[dict] = []

        for edge in edges:
            if edge.from_scene_id in outgoing:
                outgoing[edge.from_scene_id].append(edge.to_scene_id)
            if edge.from_scene_id not in scene_ids or edge.to_scene_id not in scene_ids:
                issues.append(
                    {
                        "code": "dangling_edge",
                        "severity": "error",
                        "message": "Edge references missing scene",
                        "edge_id": edge.id,
                        "metadata": {
                            "from": edge.from_scene_id,
                            "to": edge.to_scene_id,
                        },
                    }
                )

        root_id = graph.root_scene_id or (scenes[0].id if scenes else None)
        visited: set[str] = set()
        if root_id:
            queue = [root_id]
            visited.add(root_id)
            while queue:
                current = queue.pop(0)
                for target in outgoing.get(current, []):
                    if target not in visited and target in scene_ids:
                        visited.add(target)
                        queue.append(target)

        for scene in scenes:
            if root_id and scene.id not in visited:
                issues.append(
                    {
                        "code": "unreachable_scene",
                        "severity": "warning",
                        "message": "Scene is unreachable from root",
                        "scene_id": scene.id,
                    }
                )
            if not outgoing.get(scene.id) and not self._is_final_scene(scene):
                issues.append(
                    {
                        "code": "dead_end",
                        "severity": "warning",
                        "message": "Scene has no outgoing edges",
                        "scene_id": scene.id,
                    }
                )
            if scene.location_id is None:
                issues.append(
                    {
                        "code": "missing_location",
                        "severity": "info",
                        "message": "Scene has no location reference",
                        "scene_id": scene.id,
                    }
                )

        sccs = self._find_scc(scene_ids, outgoing)
        for scc in sccs:
            has_self_loop = any(node in outgoing.get(node, []) for node in scc)
            if len(scc) <= 1 and not has_self_loop:
                continue
            has_exit = False
            for node in scc:
                for target in outgoing.get(node, []):
                    if target not in scc:
                        has_exit = True
                        break
                if has_exit:
                    break
            if not has_exit:
                issues.append(
                    {
                        "code": "cycle_no_exit",
                        "severity": "warning",
                        "message": "Cycle has no outgoing exit",
                        "metadata": {"cycle": sorted(list(scc))},
                    }
                )

        summary: dict[str, int] = {"error": 0, "warning": 0, "info": 0}
        for issue in issues:
            severity = issue.get("severity")
            if severity in summary:
                summary[severity] += 1

        return {"graph_id": graph_id, "issues": issues, "summary": summary}

    async def list_usage(
        self,
        graph_id: str,
        *,
        actor: User,
        location_id: Optional[str] = None,
        character_id: Optional[str] = None,
        artifact_id: Optional[str] = None,
    ) -> Optional[list[dict]]:
        graph = await self.get_graph(graph_id, actor=actor)
        if graph is None:
            return None

        scenes = graph.scenes or []
        scene_map = {scene.id: scene for scene in scenes}
        scene_ids = list(scene_map.keys())
        items: list[dict] = []

        if location_id:
            for scene in scenes:
                if scene.location_id == location_id:
                    items.append(
                        {
                            "scene_id": scene.id,
                            "title": scene.title,
                            "scene_type": scene.scene_type,
                            "reason": "location",
                        }
                    )
            return items

        if character_id:
            from app.domain.models import SceneNodeCharacter

            result = await self.session.execute(
                select(SceneNodeCharacter)
                .where(SceneNodeCharacter.scene_id.in_(scene_ids))
                .where(SceneNodeCharacter.character_preset_id == character_id)
            )
            links = result.scalars().all()
            for link in links:
                scene = scene_map.get(link.scene_id)
                if scene:
                    items.append(
                        {
                            "scene_id": scene.id,
                            "title": scene.title,
                            "scene_type": scene.scene_type,
                            "reason": "character",
                        }
                    )
            return items

        if artifact_id:
            result = await self.session.execute(
                select(SceneArtifact)
                .where(SceneArtifact.scene_id.in_(scene_ids))
                .where(SceneArtifact.artifact_id == artifact_id)
            )
            links = result.scalars().all()
            for link in links:
                scene = scene_map.get(link.scene_id)
                if scene:
                    items.append(
                        {
                            "scene_id": scene.id,
                            "title": scene.title,
                            "scene_type": scene.scene_type,
                            "reason": "artifact",
                        }
                    )
            return items

        return []

    async def _get_active_scene_entity(self, scene_id: str, actor: User) -> Optional[SceneNode]:
        query = (
            select(SceneNode)
            .join(ScenarioGraph, ScenarioGraph.id == SceneNode.graph_id)
            .join(Project, Project.id == ScenarioGraph.project_id)
            .where(
                SceneNode.id == scene_id,
                ScenarioGraph.archived_at.is_(None),
                Project.archived_at.is_(None),
            )
        )
        if actor.role != UserRole.ADMIN:
            query = query.where(Project.owner_id == actor.id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def _get_active_edge_entity(self, edge_id: str, actor: User) -> Optional[Edge]:
        query = (
            select(Edge)
            .join(ScenarioGraph, ScenarioGraph.id == Edge.graph_id)
            .join(Project, Project.id == ScenarioGraph.project_id)
            .where(
                Edge.id == edge_id,
                ScenarioGraph.archived_at.is_(None),
                Project.archived_at.is_(None),
            )
        )
        if actor.role != UserRole.ADMIN:
            query = query.where(Project.owner_id == actor.id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    def _find_scc(nodes: set[str], edges: dict[str, list[str]]) -> list[set[str]]:
        index = 0
        indices: dict[str, int] = {}
        lowlinks: dict[str, int] = {}
        stack: list[str] = []
        on_stack: set[str] = set()
        components: list[set[str]] = []

        def strongconnect(node: str) -> None:
            nonlocal index
            indices[node] = index
            lowlinks[node] = index
            index += 1
            stack.append(node)
            on_stack.add(node)

            for neighbor in edges.get(node, []):
                if neighbor not in indices:
                    strongconnect(neighbor)
                    lowlinks[node] = min(lowlinks[node], lowlinks[neighbor])
                elif neighbor in on_stack:
                    lowlinks[node] = min(lowlinks[node], indices[neighbor])

            if lowlinks[node] == indices[node]:
                component: set[str] = set()
                while True:
                    w = stack.pop()
                    on_stack.remove(w)
                    component.add(w)
                    if w == node:
                        break
                components.append(component)

        for node in nodes:
            if node not in indices:
                strongconnect(node)

        return components
