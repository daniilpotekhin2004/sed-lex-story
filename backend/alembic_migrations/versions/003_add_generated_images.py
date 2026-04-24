"""add generated images table

Revision ID: 003
Revises: 002
Create Date: 2025-12-04 08:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON


# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create generated_images table
    op.create_table(
        'generated_images',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('scene_id', sa.String(length=32), nullable=False),
        sa.Column('author_id', sa.String(length=32), nullable=False),
        sa.Column('task_id', sa.String(length=255), nullable=True),
        sa.Column('prompt', sa.Text(), nullable=False),
        sa.Column('negative_prompt', sa.Text(), nullable=True),
        sa.Column('generation_params', JSON, nullable=True),
        sa.Column('image_path', sa.String(length=512), nullable=True),
        sa.Column('thumbnail_path', sa.String(length=512), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='pending'),
        sa.Column('moderation_notes', sa.Text(), nullable=True),
        sa.Column('moderated_by_id', sa.String(length=32), nullable=True),
        sa.Column('moderated_at', sa.String(length=50), nullable=True),
        sa.Column('variant_number', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('is_selected', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('generation_time_seconds', sa.Integer(), nullable=True),
        sa.Column('file_size_bytes', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['scene_id'], ['scenes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['author_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['moderated_by_id'], ['users.id'], ondelete='SET NULL'),
    )
    
    # Create indexes
    op.create_index(op.f('ix_generated_images_scene_id'), 'generated_images', ['scene_id'], unique=False)
    op.create_index(op.f('ix_generated_images_author_id'), 'generated_images', ['author_id'], unique=False)
    op.create_index(op.f('ix_generated_images_task_id'), 'generated_images', ['task_id'], unique=False)
    op.create_index(op.f('ix_generated_images_status'), 'generated_images', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_generated_images_status'), table_name='generated_images')
    op.drop_index(op.f('ix_generated_images_task_id'), table_name='generated_images')
    op.drop_index(op.f('ix_generated_images_author_id'), table_name='generated_images')
    op.drop_index(op.f('ix_generated_images_scene_id'), table_name='generated_images')
    op.drop_table('generated_images')
