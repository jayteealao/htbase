"""add task tracking columns for zombie detection

Revision ID: 0008_add_task_tracking_columns
Revises: 0007_add_migration_progress_table
Create Date: 2026-01-09
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0008_add_task_tracking_columns'
down_revision = '0007_add_migration_progress_table'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add task tracking columns for zombie detection
    op.add_column(
        'archive_artifact',
        sa.Column('task_started_at', sa.DateTime(), nullable=True,
                  comment='When the archive task started executing')
    )
    op.add_column(
        'archive_artifact',
        sa.Column('last_heartbeat', sa.DateTime(), nullable=True,
                  comment='Last heartbeat timestamp from worker during long operations')
    )

    # Create partial index for efficient zombie task detection
    # Only index rows that are in_progress to optimize zombie cleanup queries
    op.execute("""
        CREATE INDEX idx_zombie_tasks
        ON archive_artifact(status, updated_at)
        WHERE status = 'in_progress'
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_zombie_tasks")
    op.drop_column('archive_artifact', 'last_heartbeat')
    op.drop_column('archive_artifact', 'task_started_at')
