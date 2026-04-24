"""add projects, scenario graphs, scenes, edges, legal concepts, styles

Revision ID: 005
Revises: 004
Create Date: 2025-12-05 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_id", sa.String(length=32), nullable=True),
        sa.Column("style_profile_id", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_projects_owner_id"), "projects", ["owner_id"], unique=False)

    op.create_table(
        "scenario_graphs",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("root_scene_id", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_scenario_graphs_project_id"), "scenario_graphs", ["project_id"], unique=False)

    op.create_table(
        "style_profiles",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("base_prompt", sa.Text(), nullable=True),
        sa.Column("negative_prompt", sa.Text(), nullable=True),
        sa.Column("model_checkpoint", sa.String(length=255), nullable=True),
        sa.Column("lora_refs", sa.JSON(), nullable=True),
        sa.Column("aspect_ratio", sa.String(length=32), nullable=True),
        sa.Column("resolution", sa.JSON(), nullable=True),
        sa.Column("sampler", sa.String(length=64), nullable=True),
        sa.Column("steps", sa.Integer(), nullable=True),
        sa.Column("cfg_scale", sa.Float(), nullable=True),
        sa.Column("seed_policy", sa.String(length=32), nullable=True),
        sa.Column("palette", sa.JSON(), nullable=True),
        sa.Column("forbidden", sa.JSON(), nullable=True),
        sa.Column("style_metadata", sa.JSON(), nullable=True),  # Renamed from 'metadata' to avoid SQLAlchemy conflict
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_style_profiles_project_id"), "style_profiles", ["project_id"], unique=False)

    # scene_nodes depends on scenario_graphs
    op.create_table(
        "scene_nodes",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("graph_id", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("synopsis", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("scene_type", sa.String(length=32), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=True),
        sa.Column("context", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["graph_id"], ["scenario_graphs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_scene_nodes_graph_id"), "scene_nodes", ["graph_id"], unique=False)

    # edges references scene_nodes
    op.create_table(
        "edges",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("graph_id", sa.String(length=32), nullable=False),
        sa.Column("from_scene_id", sa.String(length=32), nullable=False),
        sa.Column("to_scene_id", sa.String(length=32), nullable=False),
        sa.Column("condition", sa.Text(), nullable=True),
        sa.Column("choice_label", sa.String(length=255), nullable=True),
        sa.Column("edge_metadata", sa.JSON(), nullable=True),  # Renamed from 'metadata' to avoid SQLAlchemy conflict
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["graph_id"], ["scenario_graphs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["from_scene_id"], ["scene_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_scene_id"], ["scene_nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_edges_graph_id"), "edges", ["graph_id"], unique=False)

    op.create_table(
        "legal_concepts",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("difficulty", sa.Integer(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(op.f("ix_legal_concepts_code"), "legal_concepts", ["code"], unique=True)

    op.create_table(
        "scene_legal_concepts",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("scene_id", sa.String(length=32), nullable=False),
        sa.Column("concept_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["scene_id"], ["scene_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["concept_id"], ["legal_concepts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_scene_legal_concepts_scene_id"), "scene_legal_concepts", ["scene_id"], unique=False)
    op.create_index(op.f("ix_scene_legal_concepts_concept_id"), "scene_legal_concepts", ["concept_id"], unique=False)

    # Add FK from scenario_graphs.root_scene_id now that scene_nodes exists
    op.create_foreign_key(
        "fk_scenario_graphs_root_scene_id",
        "scenario_graphs",
        "scene_nodes",
        ["root_scene_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # Add FK from projects.style_profile_id now that style_profiles exists
    op.create_foreign_key(
        "fk_projects_style_profile_id",
        "projects",
        "style_profiles",
        ["style_profile_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_projects_style_profile_id", "projects", type_="foreignkey")
    op.drop_constraint("fk_scenario_graphs_root_scene_id", "scenario_graphs", type_="foreignkey")
    op.drop_index(op.f("ix_scene_legal_concepts_concept_id"), table_name="scene_legal_concepts")
    op.drop_index(op.f("ix_scene_legal_concepts_scene_id"), table_name="scene_legal_concepts")
    op.drop_table("scene_legal_concepts")
    op.drop_index(op.f("ix_legal_concepts_code"), table_name="legal_concepts")
    op.drop_table("legal_concepts")
    op.drop_index(op.f("ix_edges_graph_id"), table_name="edges")
    op.drop_table("edges")
    op.drop_index(op.f("ix_scene_nodes_graph_id"), table_name="scene_nodes")
    op.drop_table("scene_nodes")
    op.drop_index(op.f("ix_style_profiles_project_id"), table_name="style_profiles")
    op.drop_table("style_profiles")
    op.drop_index(op.f("ix_scenario_graphs_project_id"), table_name="scenario_graphs")
    op.drop_table("scenario_graphs")
    op.drop_index(op.f("ix_projects_owner_id"), table_name="projects")
    op.drop_table("projects")
