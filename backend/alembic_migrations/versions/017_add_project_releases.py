"""add project release tables

Revision ID: 017
Revises: 016
Create Date: 2026-03-12 00:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "017"
down_revision = "016"
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


def upgrade() -> None:
    if not _table_exists("project_releases"):
        op.create_table(
            "project_releases",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("project_id", sa.String(length=32), nullable=False),
            sa.Column("graph_id", sa.String(length=32), nullable=False),
            sa.Column("created_by_user_id", sa.String(length=32), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="published"),
            sa.Column("package_version", sa.String(length=64), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("published_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("archived_at", sa.DateTime(), nullable=True),
            sa.Column("manifest_payload", sa.JSON(), nullable=False),
            sa.Column("export_payload", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint("project_id", "version", name="uq_project_releases_project_version"),
        )

    for index_name, columns in (
        ("ix_project_releases_project_id", ["project_id"]),
        ("ix_project_releases_graph_id", ["graph_id"]),
        ("ix_project_releases_created_by_user_id", ["created_by_user_id"]),
        ("ix_project_releases_status", ["status"]),
        ("ix_project_releases_package_version", ["package_version"]),
        ("ix_project_releases_published_at", ["published_at"]),
        ("ix_project_releases_archived_at", ["archived_at"]),
    ):
        if not _index_exists("project_releases", index_name):
            op.create_index(index_name, "project_releases", columns)

    if not _table_exists("project_release_access"):
        op.create_table(
            "project_release_access",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("release_id", sa.String(length=32), nullable=False),
            sa.Column("user_id", sa.String(length=32), nullable=False),
            sa.Column("granted_by_user_id", sa.String(length=32), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint("release_id", "user_id", name="uq_project_release_access_release_user"),
        )

    for index_name, columns in (
        ("ix_project_release_access_release_id", ["release_id"]),
        ("ix_project_release_access_user_id", ["user_id"]),
        ("ix_project_release_access_granted_by_user_id", ["granted_by_user_id"]),
    ):
        if not _index_exists("project_release_access", index_name):
            op.create_index(index_name, "project_release_access", columns)


def downgrade() -> None:
    if _table_exists("project_release_access"):
        for index_name in (
            "ix_project_release_access_granted_by_user_id",
            "ix_project_release_access_user_id",
            "ix_project_release_access_release_id",
        ):
            if _index_exists("project_release_access", index_name):
                op.drop_index(index_name, table_name="project_release_access")
        op.drop_table("project_release_access")

    if _table_exists("project_releases"):
        for index_name in (
            "ix_project_releases_archived_at",
            "ix_project_releases_published_at",
            "ix_project_releases_package_version",
            "ix_project_releases_status",
            "ix_project_releases_created_by_user_id",
            "ix_project_releases_graph_id",
            "ix_project_releases_project_id",
        ):
            if _index_exists("project_releases", index_name):
                op.drop_index(index_name, table_name="project_releases")
        op.drop_table("project_releases")
