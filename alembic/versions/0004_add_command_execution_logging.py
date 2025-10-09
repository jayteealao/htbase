"""add command execution logging tables

Revision ID: 0004_command_logging
Revises: 0003_add_size_tracking_columns
Create Date: 2025-10-09
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0004_command_logging'
down_revision = '0003_add_size_tracking_columns'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create command_executions table
    op.create_table(
        'command_executions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('command', sa.Text(), nullable=False),
        sa.Column('start_time', sa.DateTime(), nullable=False),
        sa.Column('end_time', sa.DateTime(), nullable=True),
        sa.Column('exit_code', sa.Integer(), nullable=True),
        sa.Column('timeout', sa.Float(), nullable=False),
        sa.Column('timed_out', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('archived_url_id', sa.Integer(), nullable=True),
        sa.Column('archiver', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['archived_url_id'], ['archived_urls.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indices for command_executions
    op.create_index('idx_command_executions_archived_url', 'command_executions', ['archived_url_id'])
    op.create_index('idx_command_executions_archiver', 'command_executions', ['archiver'])
    op.create_index('idx_command_executions_start_time', 'command_executions', ['start_time'])

    # Create command_output_lines table
    op.create_table(
        'command_output_lines',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('execution_id', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('stream', sa.String(length=10), nullable=False),
        sa.Column('line', sa.Text(), nullable=False),
        sa.Column('line_number', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['execution_id'], ['command_executions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indices for command_output_lines
    op.create_index('idx_command_output_execution', 'command_output_lines', ['execution_id'])
    op.create_index('idx_command_output_stream', 'command_output_lines', ['stream'])


def downgrade() -> None:
    # Drop indices first
    op.drop_index('idx_command_output_stream', table_name='command_output_lines')
    op.drop_index('idx_command_output_execution', table_name='command_output_lines')
    op.drop_index('idx_command_executions_start_time', table_name='command_executions')
    op.drop_index('idx_command_executions_archiver', table_name='command_executions')
    op.drop_index('idx_command_executions_archived_url', table_name='command_executions')

    # Drop tables
    op.drop_table('command_output_lines')
    op.drop_table('command_executions')
