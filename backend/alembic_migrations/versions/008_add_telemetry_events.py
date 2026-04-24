"""add telemetry events table

Revision ID: 008_add_telemetry_events
Revises: 007_add_scene_node_characters
Create Date: 2025-02-18
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return name in insp.get_table_names()

def upgrade():
    if _table_exists("telemetry_events"):
        return

    op.create_table(
        "telemetry_events",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("user_id", sa.String(length=32)),
        sa.Column("event_name", sa.String(length=255), nullable=False),
        sa.Column("payload", sa.JSON()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )

def downgrade():
    op.drop_table("telemetry_events")
