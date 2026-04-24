"""extend generation jobs for asset generation

Revision ID: 013
Revises: 012
Create Date: 2026-01-15 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


def _is_sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"

def _sqlite_table_exists(name: str) -> bool:
    conn = op.get_bind()
    row = conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
        {"name": name},
    ).fetchone()
    return row is not None


def _upgrade_sqlite() -> None:
    # SQLite cannot ALTER COLUMN; recreate the table instead.
    op.execute("PRAGMA foreign_keys=OFF")

    if _sqlite_table_exists("generation_jobs_old"):
        op.execute("DROP TABLE IF EXISTS generation_jobs")
    else:
        op.rename_table("generation_jobs", "generation_jobs_old")
    op.execute("DROP INDEX IF EXISTS generation_jobs_old")

    op.create_table(
        "generation_jobs",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("task_id", sa.String(length=255), nullable=True),
        sa.Column("user_id", sa.String(length=32), nullable=True),
        sa.Column("project_id", sa.String(length=32), nullable=True),
        sa.Column("scene_id", sa.String(length=32), nullable=True),
        sa.Column("style_profile_id", sa.String(length=32), nullable=True),
        sa.Column("task_type", sa.String(length=64), nullable=False, server_default="scene_generate"),
        sa.Column("entity_type", sa.String(length=64), nullable=False, server_default="scene"),
        sa.Column("entity_id", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stage", sa.String(length=64), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("negative_prompt", sa.Text(), nullable=True),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column("results", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scene_id"], ["scene_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["style_profile_id"], ["style_profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )

    op.execute(
        """
        INSERT INTO generation_jobs (
            id,
            task_id,
            user_id,
            project_id,
            scene_id,
            style_profile_id,
            task_type,
            entity_type,
            entity_id,
            status,
            progress,
            stage,
            prompt,
            negative_prompt,
            config,
            results,
            error,
            started_at,
            finished_at,
            created_at,
            updated_at
        )
        SELECT
            id,
            task_id,
            NULL,
            project_id,
            scene_id,
            style_profile_id,
            'scene_generate',
            'scene',
            COALESCE(scene_id, id),
            status,
            0,
            NULL,
            prompt,
            negative_prompt,
            config,
            NULL,
            error,
            started_at,
            finished_at,
            created_at,
            updated_at
        FROM generation_jobs_old
        """
    )

    op.drop_table("generation_jobs_old")

    op.create_index(op.f("ix_generation_jobs_project_id"), "generation_jobs", ["project_id"], unique=False)
    op.create_index(op.f("ix_generation_jobs_scene_id"), "generation_jobs", ["scene_id"], unique=False)
    op.create_index(op.f("ix_generation_jobs_status"), "generation_jobs", ["status"], unique=False)
    op.create_index(op.f("ix_generation_jobs_task_id"), "generation_jobs", ["task_id"], unique=False)
    op.create_index(op.f("ix_generation_jobs_user_id"), "generation_jobs", ["user_id"], unique=False)
    op.create_index(op.f("ix_generation_jobs_task_type"), "generation_jobs", ["task_type"], unique=False)
    op.create_index(op.f("ix_generation_jobs_entity_type"), "generation_jobs", ["entity_type"], unique=False)
    op.create_index(op.f("ix_generation_jobs_entity_id"), "generation_jobs", ["entity_id"], unique=False)

    op.execute("PRAGMA foreign_keys=ON")


# revision identifiers, used by Alembic.
revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if _is_sqlite():
        _upgrade_sqlite()
        return
    # Allow jobs that are not tied to a scene/project and add asset routing fields.
    # Use batch mode for SQLite compatibility.
    with op.batch_alter_table("generation_jobs") as batch:
        batch.alter_column(
            "project_id",
            existing_type=sa.String(length=32),
            nullable=True,
        )
        batch.alter_column(
            "scene_id",
            existing_type=sa.String(length=32),
            nullable=True,
        )
        # Prompt becomes optional for non-text-to-image jobs (some asset jobs derive prompts).
        batch.alter_column(
            "prompt",
            existing_type=sa.Text(),
            nullable=True,
        )

        batch.add_column(sa.Column("user_id", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("task_type", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("entity_type", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("entity_id", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("stage", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("progress", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("results", sa.JSON(), nullable=True))

        batch.create_index(op.f("ix_generation_jobs_user_id"), ["user_id"], unique=False)
        batch.create_index(op.f("ix_generation_jobs_task_type"), ["task_type"], unique=False)
        batch.create_index(op.f("ix_generation_jobs_entity_type"), ["entity_type"], unique=False)
        batch.create_index(op.f("ix_generation_jobs_entity_id"), ["entity_id"], unique=False)
        batch.create_foreign_key(
            "fk_generation_jobs_user_id_users",
            "users",
            ["user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # Backfill existing scene jobs.
    op.execute("UPDATE generation_jobs SET task_type = 'scene_generate' WHERE task_type IS NULL")
    op.execute("UPDATE generation_jobs SET entity_type = 'scene' WHERE entity_type IS NULL")
    op.execute("UPDATE generation_jobs SET entity_id = scene_id WHERE entity_id IS NULL")

    with op.batch_alter_table("generation_jobs") as batch:
        batch.alter_column(
            "task_type",
            existing_type=sa.String(length=64),
            nullable=False,
            server_default="scene_generate",
        )
        batch.alter_column(
            "entity_type",
            existing_type=sa.String(length=64),
            nullable=False,
            server_default="scene",
        )
        batch.alter_column(
            "entity_id",
            existing_type=sa.String(length=32),
            nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("generation_jobs") as batch:
        batch.drop_index(op.f("ix_generation_jobs_entity_id"))
        batch.drop_index(op.f("ix_generation_jobs_entity_type"))
        batch.drop_index(op.f("ix_generation_jobs_task_type"))
        batch.drop_index(op.f("ix_generation_jobs_user_id"))
        batch.drop_constraint("fk_generation_jobs_user_id_users", type_="foreignkey")

        batch.drop_column("results")
        batch.drop_column("progress")
        batch.drop_column("stage")
        batch.drop_column("entity_id")
        batch.drop_column("entity_type")
        batch.drop_column("task_type")
        batch.drop_column("user_id")

        batch.alter_column(
            "prompt",
            existing_type=sa.Text(),
            nullable=False,
        )
        batch.alter_column(
            "scene_id",
            existing_type=sa.String(length=32),
            nullable=False,
        )
        batch.alter_column(
            "project_id",
            existing_type=sa.String(length=32),
            nullable=False,
        )
