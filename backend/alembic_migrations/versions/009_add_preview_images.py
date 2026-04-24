"""add preview image urls

Revision ID: 009_add_preview_images
Revises: 008_add_telemetry_events
Create Date: 2025-02-20
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = [c["name"] for c in insp.get_columns(table)]
    return column in cols

def upgrade():
    if not _column_exists("character_presets", "preview_image_url"):
        op.add_column("character_presets", sa.Column("preview_image_url", sa.String(length=512), nullable=True))
    if not _column_exists("character_presets", "preview_thumbnail_url"):
        op.add_column("character_presets", sa.Column("preview_thumbnail_url", sa.String(length=512), nullable=True))
    if not _column_exists("locations", "preview_image_url"):
        op.add_column("locations", sa.Column("preview_image_url", sa.String(length=512), nullable=True))
    if not _column_exists("locations", "preview_thumbnail_url"):
        op.add_column("locations", sa.Column("preview_thumbnail_url", sa.String(length=512), nullable=True))
    if not _column_exists("artifacts", "preview_image_url"):
        op.add_column("artifacts", sa.Column("preview_image_url", sa.String(length=512), nullable=True))
    if not _column_exists("artifacts", "preview_thumbnail_url"):
        op.add_column("artifacts", sa.Column("preview_thumbnail_url", sa.String(length=512), nullable=True))


def downgrade():
    op.drop_column("artifacts", "preview_thumbnail_url")
    op.drop_column("artifacts", "preview_image_url")

    op.drop_column("locations", "preview_thumbnail_url")
    op.drop_column("locations", "preview_image_url")

    op.drop_column("character_presets", "preview_thumbnail_url")
    op.drop_column("character_presets", "preview_image_url")
