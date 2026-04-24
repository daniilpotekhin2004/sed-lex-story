"""add user generation presets

Revision ID: 004
Revises: 003
Create Date: 2025-12-04

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'user_generation_presets',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('user_id', sa.String(length=32), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('negative_prompt', sa.Text(), nullable=True),
        sa.Column('cfg_scale', sa.Float(), nullable=False),
        sa.Column('steps', sa.Integer(), nullable=False),
        sa.Column('width', sa.Integer(), nullable=False),
        sa.Column('height', sa.Integer(), nullable=False),
        sa.Column('style', sa.String(length=100), nullable=True),
        sa.Column('sampler', sa.String(length=100), nullable=True),
        sa.Column('lora_models', sa.JSON(), nullable=True),
        sa.Column('is_favorite', sa.Boolean(), nullable=False),
        sa.Column('usage_count', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_generation_presets_user_id'), 'user_generation_presets', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_user_generation_presets_user_id'), table_name='user_generation_presets')
    op.drop_table('user_generation_presets')
