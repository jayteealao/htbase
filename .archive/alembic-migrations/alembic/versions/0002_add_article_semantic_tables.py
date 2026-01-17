"""create tables for article summaries, tags, and entities

Revision ID: 0002_add_article_semantic_tables
Revises: 0001_init_postgres
Create Date: 2025-09-16
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '0002_add_article_semantic_tables'
down_revision = '0001_init_postgres'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'article_summaries',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('archived_url_id', sa.Integer(), sa.ForeignKey('archived_urls.id', ondelete='CASCADE'), nullable=False),
        sa.Column('summary_type', sa.String(length=50), nullable=False, server_default='default'),
        sa.Column('summary_text', sa.Text(), nullable=False),
        sa.Column('bullet_points', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('model_name', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=True, server_default=sa.text('now()'), server_onupdate=sa.text('now()')),
        sa.UniqueConstraint('archived_url_id', 'summary_type', name='uq_article_summary_type'),
    )
    op.create_index(
        'idx_article_summaries_archived_url',
        'article_summaries',
        ['archived_url_id'],
    )

    op.create_table(
        'article_entities',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('archived_url_id', sa.Integer(), sa.ForeignKey('archived_urls.id', ondelete='CASCADE'), nullable=False),
        sa.Column('entity', sa.Text(), nullable=False),
        sa.Column('entity_type', sa.String(length=64), nullable=True),
        sa.Column('alias', sa.String(), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('validated', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=True, server_default=sa.text('now()'), server_onupdate=sa.text('now()')),
        sa.UniqueConstraint('archived_url_id', 'entity', 'entity_type', name='uq_article_entity_identity'),
    )
    op.create_index(
        'idx_article_entities_archived_url',
        'article_entities',
        ['archived_url_id'],
    )
    op.create_index(
        'idx_article_entities_entity_type',
        'article_entities',
        ['entity_type'],
    )

    op.create_table(
        'article_tags',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('archived_url_id', sa.Integer(), sa.ForeignKey('archived_urls.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tag', sa.String(length=128), nullable=False),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=True, server_default=sa.text('now()'), server_onupdate=sa.text('now()')),
        sa.UniqueConstraint('archived_url_id', 'tag', 'source', name='uq_article_tag_identity'),
    )
    op.create_index(
        'idx_article_tags_archived_url',
        'article_tags',
        ['archived_url_id'],
    )
    op.create_index(
        'idx_article_tags_tag',
        'article_tags',
        ['tag'],
    )


def downgrade() -> None:
    op.drop_index('idx_article_tags_tag', table_name='article_tags')
    op.drop_index('idx_article_tags_archived_url', table_name='article_tags')
    op.drop_table('article_tags')

    op.drop_index('idx_article_entities_entity_type', table_name='article_entities')
    op.drop_index('idx_article_entities_archived_url', table_name='article_entities')
    op.drop_table('article_entities')

    op.drop_index('idx_article_summaries_archived_url', table_name='article_summaries')
    op.drop_table('article_summaries')
