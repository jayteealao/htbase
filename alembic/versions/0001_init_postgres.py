"""initial postgres schema

Revision ID: 0001_init_postgres
Revises: 
Create Date: 2025-09-16
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0001_init_postgres'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'archived_urls',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('item_id', sa.String(), nullable=True),
        sa.Column('url', sa.Text(), nullable=False, unique=True),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('idx_archived_urls_item_id', 'archived_urls', ['item_id'])

    op.create_table(
        'url_metadata',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('archived_url_id', sa.Integer(), sa.ForeignKey('archived_urls.id'), nullable=False, unique=True),
        sa.Column('source_url', sa.Text(), nullable=True),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('byline', sa.Text(), nullable=True),
        sa.Column('site_name', sa.Text(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('published', sa.String(), nullable=True),
        sa.Column('language', sa.String(), nullable=True),
        sa.Column('canonical_url', sa.Text(), nullable=True),
        sa.Column('top_image', sa.Text(), nullable=True),
        sa.Column('favicon', sa.Text(), nullable=True),
        sa.Column('keywords', sa.Text(), nullable=True),
        sa.Column('text', sa.Text(), nullable=True),
        sa.Column('word_count', sa.Integer(), nullable=True),
        sa.Column('reading_time_minutes', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    )
    # op.create_index('idx_url_metadata_archived_url_id', 'url_metadata', ['archived_url_id'])

    op.create_table(
        'archive_artifact',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('archived_url_id', sa.Integer(), sa.ForeignKey('archived_urls.id'), nullable=False),
        sa.Column('archiver', sa.String(), nullable=False),
        sa.Column('success', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('exit_code', sa.Integer(), nullable=True),
        sa.Column('saved_path', sa.Text(), nullable=True),
        sa.Column('status', sa.String(), nullable=True, server_default=sa.text("'pending'")),
        sa.Column('task_id', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_unique_constraint('uq_artifact_url_archiver', 'archive_artifact', ['archived_url_id', 'archiver'])
    op.create_index('idx_artifact_task_id', 'archive_artifact', ['task_id'])
    op.create_index('idx_artifact_archiver', 'archive_artifact', ['archiver'])


def downgrade() -> None:
    op.drop_table('archive_artifact')
    op.drop_table('url_metadata')
    op.drop_table('archived_urls')
