"""add migration_progress table

Revision ID: 0007_add_migration_progress_table
Revises: 0006_add_firestore_sync_tracking
Create Date: 2026-01-09
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0007_add_migration_progress_table'
down_revision = '0006_add_firestore_sync_tracking'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create migration_progress table for tracking Firestore to PostgreSQL migration."""

    op.create_table(
        'migration_progress',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('collection', sa.String(length=100), nullable=False,
                  comment='Firestore collection being migrated'),
        sa.Column('last_document_id', sa.String(length=255), nullable=True,
                  comment='Last successfully migrated Firestore document ID (for resumability)'),
        sa.Column('documents_migrated', sa.Integer(), nullable=False, server_default='0',
                  comment='Total count of documents migrated so far'),
        sa.Column('started_at', sa.DateTime(), nullable=False,
                  comment='When migration started'),
        sa.Column('updated_at', sa.DateTime(), nullable=True,
                  comment='Last update timestamp'),
        sa.Column('completed_at', sa.DateTime(), nullable=True,
                  comment='When migration completed'),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='running',
                  comment='Migration status: running, paused, completed, failed, rolled_back'),
    )

    # Create indexes for common queries
    op.create_index(
        'idx_migration_progress_collection',
        'migration_progress',
        ['collection'],
        unique=False
    )

    op.create_index(
        'idx_migration_progress_status',
        'migration_progress',
        ['status'],
        unique=False
    )

    op.create_index(
        'idx_migration_progress_started_at',
        'migration_progress',
        ['started_at'],
        unique=False
    )


def downgrade() -> None:
    """Drop migration_progress table."""

    op.drop_index('idx_migration_progress_started_at', table_name='migration_progress')
    op.drop_index('idx_migration_progress_status', table_name='migration_progress')
    op.drop_index('idx_migration_progress_collection', table_name='migration_progress')
    op.drop_table('migration_progress')
