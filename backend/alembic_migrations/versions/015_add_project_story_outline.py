"""add project story_outline

Revision ID: 015
Revises: 014
Create Date: 2026-01-31 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("story_outline", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "story_outline")
