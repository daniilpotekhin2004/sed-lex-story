"""add character presets

Revision ID: 002
Revises: 001
Create Date: 2025-12-04 07:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON


# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create character_presets table
    op.create_table(
        'character_presets',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('character_type', sa.String(length=50), nullable=False),
        sa.Column('appearance_prompt', sa.Text(), nullable=False),
        sa.Column('negative_prompt', sa.Text(), nullable=True),
        sa.Column('lora_models', JSON, nullable=True),
        sa.Column('embeddings', JSON, nullable=True),
        sa.Column('style_tags', JSON, nullable=True),
        sa.Column('default_pose', sa.String(length=255), nullable=True),
        sa.Column('is_public', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('author_id', sa.String(length=32), nullable=False),
        sa.Column('usage_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['author_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index(op.f('ix_character_presets_name'), 'character_presets', ['name'], unique=False)
    op.create_index(op.f('ix_character_presets_author_id'), 'character_presets', ['author_id'], unique=False)

    # Create scene_characters table
    op.create_table(
        'scene_characters',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('scene_id', sa.String(length=32), nullable=False),
        sa.Column('character_preset_id', sa.String(length=32), nullable=False),
        sa.Column('scene_context', sa.Text(), nullable=True),
        sa.Column('position', sa.String(length=50), nullable=True),
        sa.Column('importance', sa.Float(), nullable=False, server_default='1.0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['scene_id'], ['scenes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['character_preset_id'], ['character_presets.id'], ondelete='CASCADE'),
    )
    op.create_index(op.f('ix_scene_characters_scene_id'), 'scene_characters', ['scene_id'], unique=False)
    op.create_index(op.f('ix_scene_characters_character_preset_id'), 'scene_characters', ['character_preset_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_scene_characters_character_preset_id'), table_name='scene_characters')
    op.drop_index(op.f('ix_scene_characters_scene_id'), table_name='scene_characters')
    op.drop_table('scene_characters')
    
    op.drop_index(op.f('ix_character_presets_author_id'), table_name='character_presets')
    op.drop_index(op.f('ix_character_presets_name'), table_name='character_presets')
    op.drop_table('character_presets')
