"""add multi-provider upload tracking

Revision ID: 0005_add_multi_provider_tracking
Revises: 0004_command_logging
Create Date: 2025-12-06
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '0005_add_multi_provider_tracking'
down_revision = '0004_command_logging'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add upload tracking columns for multi-provider support
    op.add_column(
        'archive_artifact',
        sa.Column('uploaded_to_storage', sa.Boolean(), server_default=sa.text('false'), nullable=False)
    )
    op.add_column(
        'archive_artifact',
        sa.Column('storage_uploads', sa.JSON(), nullable=True,
                  comment='List of upload results per storage provider')
    )
    op.add_column(
        'archive_artifact',
        sa.Column('all_uploads_succeeded', sa.Boolean(), server_default=sa.text('false'), nullable=False)
    )
    op.add_column(
        'archive_artifact',
        sa.Column('local_file_deleted', sa.Boolean(), server_default=sa.text('false'), nullable=False)
    )
    op.add_column(
        'archive_artifact',
        sa.Column('local_file_deleted_at', sa.DateTime(), nullable=True)
    )

    # Create index for cleanup queries (finding files eligible for cleanup)
    op.create_index(
        'idx_artifact_cleanup',
        'archive_artifact',
        ['success', 'all_uploads_succeeded', 'local_file_deleted'],
        unique=False
    )


def downgrade() -> None:
    op.drop_index('idx_artifact_cleanup', table_name='archive_artifact')
    op.drop_column('archive_artifact', 'local_file_deleted_at')
    op.drop_column('archive_artifact', 'local_file_deleted')
    op.drop_column('archive_artifact', 'all_uploads_succeeded')
    op.drop_column('archive_artifact', 'storage_uploads')
    op.drop_column('archive_artifact', 'uploaded_to_storage')
