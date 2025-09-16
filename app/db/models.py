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
