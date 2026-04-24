"""add scene node characters for prompt engine

Revision ID: 007
Revises: 006
Create Date: 2025-12-05 02:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scene_node_characters",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("scene_id", sa.String(length=32), nullable=False),
        sa.Column("character_preset_id", sa.String(length=32), nullable=False),
        sa.Column("scene_context", sa.Text(), nullable=True),
        sa.Column("position", sa.String(length=50), nullable=True),
        sa.Column("importance", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("seed_override", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["scene_id"], ["scene_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["character_preset_id"], ["character_presets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_scene_node_characters_scene_id"), "scene_node_characters", ["scene_id"], unique=False)
    op.create_index(op.f("ix_scene_node_characters_character_preset_id"), "scene_node_characters", ["character_preset_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_scene_node_characters_character_preset_id"), table_name="scene_node_characters")
    op.drop_index(op.f("ix_scene_node_characters_scene_id"), table_name="scene_node_characters")
    op.drop_table("scene_node_characters")
