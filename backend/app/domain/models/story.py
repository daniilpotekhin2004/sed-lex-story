from __future__ import annotations

from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.domain.models.base import Base, TimestampMixin


class ScenarioGraph(Base, TimestampMixin):
    """Graph of scenes inside a project."""

    __tablename__ = "scenario_graphs"

    id = Column(String(32), primary_key=True, default=lambda: uuid4().hex)
    project_id = Column(String(32), ForeignKey("projects.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    # use_alter=True to break circular dependency with scene_nodes
    root_scene_id = Column(
        String(32),
        ForeignKey("scene_nodes.id", use_alter=True, name="fk_scenario_graphs_root_scene_id"),
        nullable=True,
    )
    archived_at = Column(DateTime, nullable=True, index=True)

    project = relationship("Project", back_populates="graphs", foreign_keys=[project_id])
    scenes = relationship(
        "SceneNode",
        back_populates="graph",
        foreign_keys="SceneNode.graph_id",
        cascade="all, delete-orphan"
    )
    edges = relationship("Edge", back_populates="graph", cascade="all, delete-orphan")


class SceneNode(Base, TimestampMixin):
    """Scene/cadence within a scenario graph."""

    __tablename__ = "scene_nodes"

    id = Column(String(32), primary_key=True, default=lambda: uuid4().hex)
    graph_id = Column(String(32), ForeignKey("scenario_graphs.id"), nullable=False, index=True)
    location_id = Column(String(32), ForeignKey("locations.id"), nullable=True, index=True)
    location_material_set_id = Column(String(32), ForeignKey("material_sets.id"), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    synopsis = Column(Text, nullable=True)
    content = Column(Text, nullable=False)
    scene_type = Column(String(32), nullable=False, default="story")
    order_index = Column(Integer, nullable=True)
    context = Column(JSON, nullable=True)
    location_overrides = Column(JSON, nullable=True)

    graph = relationship(
        "ScenarioGraph",
        back_populates="scenes",
        foreign_keys=[graph_id]
    )
    outgoing_edges = relationship(
        "Edge",
        foreign_keys="Edge.from_scene_id",
        back_populates="from_scene",
        cascade="all, delete-orphan",
    )
    incoming_edges = relationship(
        "Edge",
        foreign_keys="Edge.to_scene_id",
        back_populates="to_scene",
        cascade="all, delete-orphan",
    )
    legal_links = relationship(
        "SceneLegalConcept", back_populates="scene", cascade="all, delete-orphan"
    )
    legal_concepts = relationship(
        "LegalConcept",
        secondary="scene_legal_concepts",
        back_populates="scenes",
        overlaps="legal_links",
    )
    scene_characters_v2 = relationship(
        "SceneNodeCharacter",
        back_populates="scene",
        cascade="all, delete-orphan",
        foreign_keys="SceneNodeCharacter.scene_id",
    )
    location = relationship("Location", back_populates="scenes", foreign_keys=[location_id])
    location_material_set = relationship("MaterialSet", foreign_keys=[location_material_set_id])
    scene_artifacts = relationship(
        "SceneArtifact",
        back_populates="scene",
        cascade="all, delete-orphan",
        foreign_keys="SceneArtifact.scene_id",
    )

    @property
    def artifacts(self):
        return self.scene_artifacts


class Edge(Base, TimestampMixin):
    """Directed transition between scenes."""

    __tablename__ = "edges"

    id = Column(String(32), primary_key=True, default=lambda: uuid4().hex)
    graph_id = Column(String(32), ForeignKey("scenario_graphs.id"), nullable=False, index=True)
    from_scene_id = Column(String(32), ForeignKey("scene_nodes.id"), nullable=False)
    to_scene_id = Column(String(32), ForeignKey("scene_nodes.id"), nullable=False)
    condition = Column(Text, nullable=True)
    choice_label = Column(String(255), nullable=True)
    edge_metadata = Column(JSON, nullable=True)  # Renamed from 'metadata' to avoid SQLAlchemy conflict

    graph = relationship("ScenarioGraph", back_populates="edges")
    from_scene = relationship("SceneNode", foreign_keys=[from_scene_id], back_populates="outgoing_edges")
    to_scene = relationship("SceneNode", foreign_keys=[to_scene_id], back_populates="incoming_edges")
