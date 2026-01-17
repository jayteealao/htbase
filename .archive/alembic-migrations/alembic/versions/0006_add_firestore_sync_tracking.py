"""add firestore sync tracking

Revision ID: 0006_add_firestore_sync_tracking
Revises: 0005_add_multi_provider_tracking
Create Date: 2026-01-09
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0006_add_firestore_sync_tracking'
down_revision = '0005_add_multi_provider_tracking'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add sync tracking columns to archived_urls
    op.add_column(
        'archived_urls',
        sa.Column('last_synced_to_firestore', sa.DateTime(), nullable=True,
                  comment='Timestamp of last successful sync to Firestore')
    )

    # Add sync tracking columns to archive_artifact
    op.add_column(
        'archive_artifact',
        sa.Column('last_synced_to_firestore', sa.DateTime(), nullable=True,
                  comment='Timestamp of last successful sync to Firestore')
    )

    # Create indexes for reconciliation queries (finding unsynced records)
    op.create_index(
        'idx_archived_urls_sync_status',
        'archived_urls',
        ['last_synced_to_firestore'],
        unique=False
    )

    op.create_index(
        'idx_artifact_sync_status',
        'archive_artifact',
        ['last_synced_to_firestore'],
        unique=False
    )


def downgrade() -> None:
    op.drop_index('idx_artifact_sync_status', table_name='archive_artifact')
    op.drop_index('idx_archived_urls_sync_status', table_name='archived_urls')
    op.drop_column('archive_artifact', 'last_synced_to_firestore')
    op.drop_column('archived_urls', 'last_synced_to_firestore')
