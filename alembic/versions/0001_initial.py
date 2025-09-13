"""initial schema

Revision ID: 0001_initial
Revises: 
Create Date: 2025-09-13

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "saves",
        sa.Column("rowid", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("item_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("saved_path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("datetime('now')")),
        sa.Column("status", sa.String(), nullable=True, server_default=sa.text("'pending'")),
        sa.Column("task_id", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=True),
    )
    op.create_index("idx_saves_item_id_created_at", "saves", ["item_id", "created_at"], unique=False)
    op.create_index("idx_saves_user_id_created_at", "saves", ["user_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_saves_user_id_created_at", table_name="saves")
    op.drop_index("idx_saves_item_id_created_at", table_name="saves")
    op.drop_table("saves")

