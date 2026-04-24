"""(noop) generation_jobs user_id + stage

Revision ID: 014
Revises: 013
Create Date: 2026-01-15 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NOTE: migration 013 already introduced user_id, stage and prompt nullability.
    # This revision is kept as a compatibility marker for DBs that already
    # migrated to 014 in earlier iterations.
    pass


def downgrade() -> None:
    # Nothing to do. Columns are removed in downgrade() of revision 013.
    pass
