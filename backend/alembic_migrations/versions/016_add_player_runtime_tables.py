"""add player runtime tables

Revision ID: 016
Revises: 015
Create Date: 2026-03-12 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return name in insp.get_table_names()


def upgrade() -> None:
    if not _table_exists("player_runs"):
        op.create_table(
            "player_runs",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("project_id", sa.String(length=32), nullable=False),
            sa.Column("graph_id", sa.String(length=32), nullable=False),
            sa.Column("user_id", sa.String(length=32), nullable=False),
            sa.Column("package_version", sa.String(length=64), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
            sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("last_synced_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("last_node_id", sa.String(length=32), nullable=True),
            sa.Column("run_metadata", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_player_runs_project_id", "player_runs", ["project_id"])
        op.create_index("ix_player_runs_graph_id", "player_runs", ["graph_id"])
        op.create_index("ix_player_runs_user_id", "player_runs", ["user_id"])
        op.create_index("ix_player_runs_status", "player_runs", ["status"])

    if not _table_exists("player_run_events"):
        op.create_table(
            "player_run_events",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("run_id", sa.String(length=64), nullable=False),
            sa.Column("project_id", sa.String(length=32), nullable=False),
            sa.Column("user_id", sa.String(length=32), nullable=False),
            sa.Column("event_type", sa.String(length=64), nullable=False),
            sa.Column("event_timestamp", sa.DateTime(), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_player_run_events_run_id", "player_run_events", ["run_id"])
        op.create_index("ix_player_run_events_project_id", "player_run_events", ["project_id"])
        op.create_index("ix_player_run_events_user_id", "player_run_events", ["user_id"])
        op.create_index("ix_player_run_events_event_type", "player_run_events", ["event_type"])
        op.create_index("ix_player_run_events_event_timestamp", "player_run_events", ["event_timestamp"])


def downgrade() -> None:
    if _table_exists("player_run_events"):
        op.drop_index("ix_player_run_events_event_timestamp", table_name="player_run_events")
        op.drop_index("ix_player_run_events_event_type", table_name="player_run_events")
        op.drop_index("ix_player_run_events_user_id", table_name="player_run_events")
        op.drop_index("ix_player_run_events_project_id", table_name="player_run_events")
        op.drop_index("ix_player_run_events_run_id", table_name="player_run_events")
        op.drop_table("player_run_events")

    if _table_exists("player_runs"):
        op.drop_index("ix_player_runs_status", table_name="player_runs")
        op.drop_index("ix_player_runs_user_id", table_name="player_runs")
        op.drop_index("ix_player_runs_graph_id", table_name="player_runs")
        op.drop_index("ix_player_runs_project_id", table_name="player_runs")
        op.drop_table("player_runs")
