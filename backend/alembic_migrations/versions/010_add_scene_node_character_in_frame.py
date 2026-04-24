"""add in_frame flag for scene node characters

Revision ID: 010
Revises: 009
Create Date: 2025-12-22 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Default to true so existing rows behave as before (character is in frame).
    op.add_column(
        "scene_node_characters",
        sa.Column("in_frame", sa.Boolean(), nullable=False, server_default=sa.text("1")),
    )
    # Remove server default after backfill (optional but cleaner).
    op.alter_column("scene_node_characters", "in_frame", server_default=None)


def downgrade() -> None:
    op.drop_column("scene_node_characters", "in_frame")
