"""add studio assets and material sets

Revision ID: 011_add_studio_assets_and_material_sets
Revises: 010_add_scene_node_character_in_frame
Create Date: 2025-01-12 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("character_presets") as batch:
        batch.add_column(sa.Column("project_id", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("source_preset_id", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("source_version", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
        batch.create_index("ix_character_presets_project_id", ["project_id"])
        batch.create_index("ix_character_presets_source_preset_id", ["source_preset_id"])
        batch.create_foreign_key("fk_character_presets_project", "projects", ["project_id"], ["id"])
        batch.create_foreign_key(
            "fk_character_presets_source", "character_presets", ["source_preset_id"], ["id"]
        )

    with op.batch_alter_table("locations") as batch:
        batch.alter_column("project_id", existing_type=sa.String(length=32), nullable=True)
        batch.add_column(sa.Column("owner_id", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("is_public", sa.Boolean(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("source_location_id", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("source_version", sa.Integer(), nullable=True))
        batch.create_index("ix_locations_owner_id", ["owner_id"])
        batch.create_index("ix_locations_source_location_id", ["source_location_id"])
        batch.create_foreign_key("fk_locations_owner", "users", ["owner_id"], ["id"])
        batch.create_foreign_key("fk_locations_source", "locations", ["source_location_id"], ["id"])

    with op.batch_alter_table("artifacts") as batch:
        batch.alter_column("project_id", existing_type=sa.String(length=32), nullable=True)
        batch.add_column(sa.Column("owner_id", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("is_public", sa.Boolean(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("source_artifact_id", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("source_version", sa.Integer(), nullable=True))
        batch.create_index("ix_artifacts_owner_id", ["owner_id"])
        batch.create_index("ix_artifacts_source_artifact_id", ["source_artifact_id"])
        batch.create_foreign_key("fk_artifacts_owner", "users", ["owner_id"], ["id"])
        batch.create_foreign_key("fk_artifacts_source", "artifacts", ["source_artifact_id"], ["id"])

    with op.batch_alter_table("document_templates") as batch:
        batch.alter_column("project_id", existing_type=sa.String(length=32), nullable=True)
        batch.add_column(sa.Column("owner_id", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("is_public", sa.Boolean(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("source_template_id", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("source_version", sa.Integer(), nullable=True))
        batch.create_index("ix_document_templates_owner_id", ["owner_id"])
        batch.create_index("ix_document_templates_source_template_id", ["source_template_id"])
        batch.create_foreign_key("fk_document_templates_owner", "users", ["owner_id"], ["id"])
        batch.create_foreign_key(
            "fk_document_templates_source", "document_templates", ["source_template_id"], ["id"]
        )

    op.create_table(
        "material_sets",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("project_id", sa.String(length=32), sa.ForeignKey("projects.id"), nullable=False, index=True),
        sa.Column("asset_type", sa.String(length=32), nullable=False, index=True),
        sa.Column("asset_id", sa.String(length=32), nullable=False, index=True),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("reference_images", sa.JSON(), nullable=True),
        sa.Column("material_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    with op.batch_alter_table("scene_node_characters") as batch:
        batch.add_column(sa.Column("material_set_id", sa.String(length=32), nullable=True))
        batch.create_index("ix_scene_node_characters_material_set_id", ["material_set_id"])
        batch.create_foreign_key("fk_scene_node_characters_material_set", "material_sets", ["material_set_id"], ["id"])

    with op.batch_alter_table("scene_nodes") as batch:
        batch.add_column(sa.Column("location_material_set_id", sa.String(length=32), nullable=True))
        batch.create_index("ix_scene_nodes_location_material_set_id", ["location_material_set_id"])
        batch.create_foreign_key("fk_scene_nodes_location_material_set", "material_sets", ["location_material_set_id"], ["id"])


def downgrade():
    op.drop_table("material_sets")

    with op.batch_alter_table("scene_nodes") as batch:
        batch.drop_constraint("fk_scene_nodes_location_material_set", type_="foreignkey")
        batch.drop_index("ix_scene_nodes_location_material_set_id")
        batch.drop_column("location_material_set_id")

    with op.batch_alter_table("scene_node_characters") as batch:
        batch.drop_constraint("fk_scene_node_characters_material_set", type_="foreignkey")
        batch.drop_index("ix_scene_node_characters_material_set_id")
        batch.drop_column("material_set_id")

    with op.batch_alter_table("document_templates") as batch:
        batch.drop_constraint("fk_document_templates_source", type_="foreignkey")
        batch.drop_constraint("fk_document_templates_owner", type_="foreignkey")
        batch.drop_index("ix_document_templates_owner_id")
        batch.drop_index("ix_document_templates_source_template_id")
        batch.drop_column("source_version")
        batch.drop_column("source_template_id")
        batch.drop_column("version")
        batch.drop_column("is_public")
        batch.drop_column("owner_id")
        batch.alter_column("project_id", existing_type=sa.String(length=32), nullable=False)

    with op.batch_alter_table("artifacts") as batch:
        batch.drop_constraint("fk_artifacts_source", type_="foreignkey")
        batch.drop_constraint("fk_artifacts_owner", type_="foreignkey")
        batch.drop_index("ix_artifacts_owner_id")
        batch.drop_index("ix_artifacts_source_artifact_id")
        batch.drop_column("source_version")
        batch.drop_column("source_artifact_id")
        batch.drop_column("version")
        batch.drop_column("is_public")
        batch.drop_column("owner_id")
        batch.alter_column("project_id", existing_type=sa.String(length=32), nullable=False)

    with op.batch_alter_table("locations") as batch:
        batch.drop_constraint("fk_locations_source", type_="foreignkey")
        batch.drop_constraint("fk_locations_owner", type_="foreignkey")
        batch.drop_index("ix_locations_owner_id")
        batch.drop_index("ix_locations_source_location_id")
        batch.drop_column("source_version")
        batch.drop_column("source_location_id")
        batch.drop_column("version")
        batch.drop_column("is_public")
        batch.drop_column("owner_id")
        batch.alter_column("project_id", existing_type=sa.String(length=32), nullable=False)

    with op.batch_alter_table("character_presets") as batch:
        batch.drop_constraint("fk_character_presets_source", type_="foreignkey")
        batch.drop_constraint("fk_character_presets_project", type_="foreignkey")
        batch.drop_index("ix_character_presets_project_id")
        batch.drop_index("ix_character_presets_source_preset_id")
        batch.drop_column("version")
        batch.drop_column("source_version")
        batch.drop_column("source_preset_id")
        batch.drop_column("project_id")
