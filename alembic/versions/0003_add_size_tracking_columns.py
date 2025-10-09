"""add size tracking columns to archive_artifact and archived_urls

Revision ID: 0003_add_size_tracking_columns
Revises: 0002_add_article_semantic_tables
Create Date: 2025-10-08
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0003_add_size_tracking_columns'
down_revision = '0002_add_article_semantic_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add size_bytes column to archive_artifact (size of individual archiver output)
    op.add_column(
        'archive_artifact',
        sa.Column('size_bytes', sa.BigInteger(), nullable=True)
    )

    # Add total_size_bytes column to archived_urls (total size of all artifacts for a URL)
    op.add_column(
        'archived_urls',
        sa.Column('total_size_bytes', sa.BigInteger(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('archived_urls', 'total_size_bytes')
    op.drop_column('archive_artifact', 'size_bytes')
