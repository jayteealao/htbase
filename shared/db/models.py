"""
SQLAlchemy ORM models for HTBase.

These models define the database schema for storing archived URLs,
artifacts, metadata, summaries, and related data.
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    text as sa_text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class ArchivedUrl(Base):
    """Archived URL record - the primary entity for saved URLs."""

    __tablename__ = "archived_urls"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # Original identifier provided by client (kept for compatibility/labeling)
    item_id = Column(String, nullable=True)
    # The canonical URL for this entry; enforce single row per URL
    url = Column(Text, nullable=False, unique=True)
    name = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=sa_text("now()"))
    # Total size of all artifacts for this URL
    total_size_bytes = Column(BigInteger, nullable=True)

    # Relationships
    artifacts = relationship("ArchiveArtifact", back_populates="archived_url")
    metadata = relationship("UrlMetadata", back_populates="archived_url", uselist=False)
    summaries = relationship("ArticleSummary", back_populates="archived_url")
    entities = relationship("ArticleEntity", back_populates="archived_url")
    tags = relationship("ArticleTag", back_populates="archived_url")

    __table_args__ = (
        Index("idx_archived_urls_item_id", "item_id"),
    )


class UrlMetadata(Base):
    """Metadata extracted from URL content (via readability)."""

    __tablename__ = "url_metadata"

    id = Column(Integer, primary_key=True, autoincrement=True)
    archived_url_id = Column(
        Integer, ForeignKey("archived_urls.id"), nullable=False, unique=True
    )
    # Core metadata
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

    # Relationships
    archived_url = relationship("ArchivedUrl", back_populates="metadata")

    __table_args__ = (
        Index("idx_url_metadata_archived_url_id", "archived_url_id"),
    )


class ArchiveArtifact(Base):
    """Archive artifact - output from a specific archiver for a URL."""

    __tablename__ = "archive_artifact"

    id = Column(Integer, primary_key=True, autoincrement=True)
    archived_url_id = Column(
        Integer, ForeignKey("archived_urls.id"), nullable=False
    )
    archiver = Column(String, nullable=False)
    # Execution/result fields
    success = Column(Boolean, nullable=False, server_default=sa_text("false"))
    exit_code = Column(Integer, nullable=True)
    saved_path = Column(Text, nullable=True)
    status = Column(String, nullable=True, server_default=sa_text("'pending'"))
    task_id = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=sa_text("now()"))
    updated_at = Column(DateTime, nullable=True)
    # Size of individual archiver output in bytes
    size_bytes = Column(BigInteger, nullable=True)

    # Multi-provider upload tracking
    uploaded_to_storage = Column(
        Boolean, nullable=False, server_default=sa_text("false")
    )
    storage_uploads = Column(JSON, nullable=True)  # List of upload results per provider
    all_uploads_succeeded = Column(
        Boolean, nullable=False, server_default=sa_text("false")
    )
    local_file_deleted = Column(
        Boolean, nullable=False, server_default=sa_text("false")
    )
    local_file_deleted_at = Column(DateTime, nullable=True)

    # Storage paths
    gcs_path = Column(Text, nullable=True)
    gcs_bucket = Column(String, nullable=True)

    # Relationships
    archived_url = relationship("ArchivedUrl", back_populates="artifacts")

    __table_args__ = (
        UniqueConstraint("archived_url_id", "archiver", name="uq_artifact_url_archiver"),
        Index("idx_artifact_task_id", "task_id"),
        Index("idx_artifact_archiver", "archiver"),
        Index(
            "idx_artifact_cleanup",
            "success",
            "all_uploads_succeeded",
            "local_file_deleted",
        ),
        Index("idx_artifact_status", "status"),
    )


class ArticleSummary(Base):
    """AI-generated article summary."""

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

    # Relationships
    archived_url = relationship("ArchivedUrl", back_populates="summaries")

    __table_args__ = (
        UniqueConstraint(
            "archived_url_id", "summary_type", name="uq_article_summary_type"
        ),
        Index("idx_article_summaries_archived_url", "archived_url_id"),
    )


class ArticleEntity(Base):
    """Named entity extracted from article."""

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

    # Relationships
    archived_url = relationship("ArchivedUrl", back_populates="entities")

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
    """Article tag/category."""

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

    # Relationships
    archived_url = relationship("ArchivedUrl", back_populates="tags")

    __table_args__ = (
        UniqueConstraint(
            "archived_url_id", "tag", "source", name="uq_article_tag_identity"
        ),
        Index("idx_article_tags_archived_url", "archived_url_id"),
        Index("idx_article_tags_tag", "tag"),
    )


class CommandExecution(Base):
    """Records of command executions with full observability."""

    __tablename__ = "command_executions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    command = Column(Text, nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    exit_code = Column(Integer, nullable=True)
    timeout = Column(Float, nullable=False)
    timed_out = Column(Boolean, nullable=False, server_default=sa_text("false"))
    # Optional context linking
    archived_url_id = Column(Integer, ForeignKey("archived_urls.id"), nullable=True)
    archiver = Column(String, nullable=True)

    __table_args__ = (
        Index("idx_command_executions_archived_url", "archived_url_id"),
        Index("idx_command_executions_archiver", "archiver"),
        Index("idx_command_executions_start_time", "start_time"),
    )


class CommandOutputLine(Base):
    """Individual lines of stdin/stdout/stderr from command executions."""

    __tablename__ = "command_output_lines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    execution_id = Column(
        Integer,
        ForeignKey("command_executions.id", ondelete="CASCADE"),
        nullable=False,
    )
    timestamp = Column(DateTime, nullable=False)
    stream = Column(String(length=10), nullable=False)  # 'stdin', 'stdout', 'stderr'
    line = Column(Text, nullable=False)
    line_number = Column(Integer, nullable=True)

    __table_args__ = (
        Index("idx_command_output_execution", "execution_id"),
        Index("idx_command_output_stream", "stream"),
    )
