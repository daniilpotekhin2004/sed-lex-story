"""add generation jobs and image variants

Revision ID: 006
Revises: 005
Create Date: 2025-12-05 01:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "generation_jobs",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("task_id", sa.String(length=255), nullable=True),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("scene_id", sa.String(length=32), nullable=False),
        sa.Column("style_profile_id", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("negative_prompt", sa.Text(), nullable=True),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scene_id"], ["scene_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["style_profile_id"], ["style_profiles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_generation_jobs_project_id"), "generation_jobs", ["project_id"], unique=False)
    op.create_index(op.f("ix_generation_jobs_scene_id"), "generation_jobs", ["scene_id"], unique=False)
    op.create_index(op.f("ix_generation_jobs_status"), "generation_jobs", ["status"], unique=False)
    op.create_index(op.f("ix_generation_jobs_task_id"), "generation_jobs", ["task_id"], unique=False)

    op.create_table(
        "image_variants",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("job_id", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("scene_id", sa.String(length=32), nullable=False),
        sa.Column("url", sa.String(length=512), nullable=False),
        sa.Column("thumbnail_url", sa.String(length=512), nullable=True),
        sa.Column("image_metadata", sa.JSON(), nullable=True),  # Renamed from 'metadata' to avoid SQLAlchemy conflict
        sa.Column("is_approved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["generation_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scene_id"], ["scene_nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_image_variants_job_id"), "image_variants", ["job_id"], unique=False)
    op.create_index(op.f("ix_image_variants_scene_id"), "image_variants", ["scene_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_image_variants_scene_id"), table_name="image_variants")
    op.drop_index(op.f("ix_image_variants_job_id"), table_name="image_variants")
    op.drop_table("image_variants")
    op.drop_index(op.f("ix_generation_jobs_task_id"), table_name="generation_jobs")
    op.drop_index(op.f("ix_generation_jobs_status"), table_name="generation_jobs")
    op.drop_index(op.f("ix_generation_jobs_scene_id"), table_name="generation_jobs")
    op.drop_index(op.f("ix_generation_jobs_project_id"), table_name="generation_jobs")
    op.drop_table("generation_jobs")
