from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text, ForeignKey, Float, text as sa_text
from sqlalchemy.orm import declarative_base


Base = declarative_base()


class Save(Base):
    __tablename__ = "saves"

    # Keep the primary key column named 'rowid' for compatibility with existing code
    rowid = Column(Integer, primary_key=True, autoincrement=True)

    item_id = Column(String, nullable=False)
    # Optional legacy column for backward compatibility
    user_id = Column(String, nullable=True)

    url = Column(Text, nullable=False)
    success = Column(Boolean, nullable=False, default=False, server_default=sa_text("0"))
    exit_code = Column(Integer, nullable=True)
    saved_path = Column(Text, nullable=True)
    created_at = Column(
        DateTime,
        nullable=False,
        server_default=sa_text("datetime('now')"),
    )
    status = Column(String, nullable=True, server_default=sa_text("'pending'"))
    task_id = Column(String, nullable=True)
    name = Column(String, nullable=True)
    # Name of the archiver that produced this row (e.g., monolith, screenshot)
    archiver = Column(String, nullable=True)


# Indices matching the raw-SQL schema intent
Index("idx_saves_item_id_created_at", Save.item_id, Save.created_at)
Index("idx_saves_user_id_created_at", Save.user_id, Save.created_at)
# Useful for per-archiver lookups and skipping existing saves
Index("idx_saves_item_archiver_created_at", Save.item_id, Save.archiver, Save.created_at)


class SaveMetadata(Base):
    __tablename__ = "save_metadata"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # FK to saves.rowid (one metadata row per save)
    save_rowid = Column(Integer, ForeignKey("saves.rowid"), nullable=False)
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

    created_at = Column(DateTime, nullable=False, server_default=sa_text("datetime('now')"))

Index("idx_save_metadata_save_rowid", SaveMetadata.save_rowid)
