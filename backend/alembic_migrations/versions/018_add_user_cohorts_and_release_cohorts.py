"""add user cohorts and release cohort access

Revision ID: 018
Revises: 017
Create Date: 2026-03-12 01:15:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return name in insp.get_table_names()


def _index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return any(index.get("name") == index_name for index in insp.get_indexes(table_name))


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return any(column.get("name") == column_name for column in insp.get_columns(table_name))


def upgrade() -> None:
    if not _column_exists("users", "cohort_code"):
        op.add_column("users", sa.Column("cohort_code", sa.String(length=64), nullable=True))
    if not _index_exists("users", "ix_users_cohort_code"):
        op.create_index("ix_users_cohort_code", "users", ["cohort_code"])

    if not _table_exists("project_release_cohort_access"):
        op.create_table(
            "project_release_cohort_access",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("release_id", sa.String(length=32), nullable=False),
            sa.Column("cohort_code", sa.String(length=64), nullable=False),
            sa.Column("granted_by_user_id", sa.String(length=32), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint(
                "release_id",
                "cohort_code",
                name="uq_project_release_cohort_access_release_cohort",
            ),
        )

    for index_name, columns in (
        ("ix_project_release_cohort_access_release_id", ["release_id"]),
        ("ix_project_release_cohort_access_cohort_code", ["cohort_code"]),
        ("ix_project_release_cohort_access_granted_by_user_id", ["granted_by_user_id"]),
    ):
        if not _index_exists("project_release_cohort_access", index_name):
            op.create_index(index_name, "project_release_cohort_access", columns)


def downgrade() -> None:
    if _table_exists("project_release_cohort_access"):
        for index_name in (
            "ix_project_release_cohort_access_granted_by_user_id",
            "ix_project_release_cohort_access_cohort_code",
            "ix_project_release_cohort_access_release_id",
        ):
            if _index_exists("project_release_cohort_access", index_name):
                op.drop_index(index_name, table_name="project_release_cohort_access")
        op.drop_table("project_release_cohort_access")

    if _index_exists("users", "ix_users_cohort_code"):
        op.drop_index("ix_users_cohort_code", table_name="users")
    if _column_exists("users", "cohort_code"):
        if op.get_bind().dialect.name == "postgresql":
            op.execute("ALTER TABLE users DROP COLUMN IF EXISTS cohort_code")
        else:
            # SQLite test env relies on metadata create_all, so downgrade keeps best-effort semantics.
            pass
