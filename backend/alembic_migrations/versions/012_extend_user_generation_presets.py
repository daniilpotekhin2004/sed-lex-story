"""extend user generation presets

Revision ID: 012_extend_user_generation_presets
Revises: 011_add_studio_assets_and_material_sets
Create Date: 2026-01-15 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user_generation_presets") as batch:
        batch.add_column(sa.Column("scheduler", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("model_id", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("vae_id", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("seed", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("pipeline_profile_id", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("pipeline_profile_version", sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table("user_generation_presets") as batch:
        batch.drop_column("pipeline_profile_version")
        batch.drop_column("pipeline_profile_id")
        batch.drop_column("seed")
        batch.drop_column("vae_id")
        batch.drop_column("model_id")
        batch.drop_column("scheduler")
