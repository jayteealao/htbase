from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    ForeignKey,
    Float,
    UniqueConstraint,
    text as sa_text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base


Base = declarative_base()


class ArchivedUrl(Base):
    __tablename__ = "archived_urls"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # Original identifier provided by client (kept for compatibility/labeling)
    item_id = Column(String, nullable=True)
    # The canonical URL for this entry; enforce single row per URL
    url = Column(Text, nullable=False, unique=True)
    name = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=sa_text("now()"))

    # Convenience indices
    __table_args__ = (
        Index("idx_archived_urls_item_id", "item_id"),
    )


class UrlMetadata(Base):
    __tablename__ = "url_metadata"

    id = Column(Integer, primary_key=True, autoincrement=True)
    archived_url_id = Column(Integer, ForeignKey("archived_urls.id"), nullable=False, unique=True)
    # Core
    source_url = Column(Text, nullable=True)
    title = Column(Text, nullable=True)
    byline = Column(Text, nullable=True)
    site_name = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    published = Column(String, nullable=True)
    language = Column(String, nullable=True)
    canonical_url = Column(Text, nullable=True)
    # Media
    top_image = Column(Text, nullable=True)
    favicon = Column(Text, nullable=True)
    # SEO
    keywords = Column(Text, nullable=True)  # JSON array encoded as text
    # Content
    text = Column(Text, nullable=True)
    word_count = Column(Integer, nullable=True)
    reading_time_minutes = Column(Float, nullable=True)

    created_at = Column(DateTime, nullable=False, server_default=sa_text("now()"))

    __table_args__ = (
        Index("idx_url_metadata_archived_url_id", "archived_url_id"),
    )


class ArchiveArtifact(Base):
    __tablename__ = "archive_artifact"

    id = Column(Integer, primary_key=True, autoincrement=True)
    archived_url_id = Column(Integer, ForeignKey("archived_urls.id"), nullable=False)
    archiver = Column(String, nullable=False)
    # Execution/result fields
    success = Column(Boolean, nullable=False, server_default=sa_text("false"))
    exit_code = Column(Integer, nullable=True)
    saved_path = Column(Text, nullable=True)
    status = Column(String, nullable=True, server_default=sa_text("'pending'"))
    task_id = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=sa_text("now()"))
    updated_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("archived_url_id", "archiver", name="uq_artifact_url_archiver"),
        Index("idx_artifact_task_id", "task_id"),
        Index("idx_artifact_archiver", "archiver"),
    )


class ArticleSummary(Base):
    __tablename__ = "article_summaries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    archived_url_id = Column(
        Integer,
        ForeignKey("archived_urls.id", ondelete="CASCADE"),
        nullable=False,
    )
    summary_type = Column(String(length=50), nullable=False, server_default="default")
    summary_text = Column(Text, nullable=False)
    bullet_points = Column(JSONB, nullable=True)
    model_name = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=sa_text("now()"))
    updated_at = Column(
        DateTime,
        nullable=True,
        server_default=sa_text("now()"),
        server_onupdate=sa_text("now()"),
    )

    __table_args__ = (
        UniqueConstraint(
            "archived_url_id", "summary_type", name="uq_article_summary_type"
        ),
        Index("idx_article_summaries_archived_url", "archived_url_id"),
    )


class ArticleEntity(Base):
    __tablename__ = "article_entities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    archived_url_id = Column(
        Integer,
        ForeignKey("archived_urls.id", ondelete="CASCADE"),
        nullable=False,
    )
    entity = Column(Text, nullable=False)
    entity_type = Column(String(length=64), nullable=True)
    alias = Column(String, nullable=True)
    reason = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)
    validated = Column(Boolean, nullable=False, server_default=sa_text("false"))
    created_at = Column(DateTime, nullable=False, server_default=sa_text("now()"))
    updated_at = Column(
        DateTime,
        nullable=True,
        server_default=sa_text("now()"),
        server_onupdate=sa_text("now()"),
    )

    __table_args__ = (
        UniqueConstraint(
            "archived_url_id",
            "entity",
            "entity_type",
            name="uq_article_entity_identity",
        ),
        Index("idx_article_entities_archived_url", "archived_url_id"),
        Index("idx_article_entities_entity_type", "entity_type"),
    )


class ArticleTag(Base):
    __tablename__ = "article_tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    archived_url_id = Column(
        Integer,
        ForeignKey("archived_urls.id", ondelete="CASCADE"),
        nullable=False,
    )
    tag = Column(String(length=128), nullable=False)
    source = Column(String(length=32), nullable=False)
    confidence = Column(Float, nullable=True)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=sa_text("now()"))
    updated_at = Column(
        DateTime,
        nullable=True,
        server_default=sa_text("now()"),
        server_onupdate=sa_text("now()"),
    )

    __table_args__ = (
        UniqueConstraint(
            "archived_url_id", "tag", "source", name="uq_article_tag_identity"
        ),
        Index("idx_article_tags_archived_url", "archived_url_id"),
        Index("idx_article_tags_tag", "tag"),
    )
