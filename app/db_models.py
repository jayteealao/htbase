from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text, text
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
    success = Column(Boolean, nullable=False, default=False, server_default=text("0"))
    exit_code = Column(Integer, nullable=True)
    saved_path = Column(Text, nullable=True)
    created_at = Column(
        DateTime,
        nullable=False,
        server_default=text("datetime('now')"),
    )
    status = Column(String, nullable=True, server_default=text("'pending'"))
    task_id = Column(String, nullable=True)
    name = Column(String, nullable=True)


# Indices matching the raw-SQL schema intent
Index("idx_saves_item_id_created_at", Save.item_id, Save.created_at)
Index("idx_saves_user_id_created_at", Save.user_id, Save.created_at)

