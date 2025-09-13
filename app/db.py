import sqlite3
from pathlib import Path
from typing import Optional


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS saves (
                rowid INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id TEXT NOT NULL,
                url TEXT NOT NULL,
                success INTEGER NOT NULL,
                exit_code INTEGER,
                saved_path TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
        # Create both potential indices for forward/backward compatibility
        try:
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_saves_item_id_created_at ON saves(item_id, created_at);"
            )
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_saves_user_id_created_at ON saves(user_id, created_at);"
            )
        except sqlite3.OperationalError:
            pass


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.execute(f"PRAGMA table_info({table});")
    return any(row[1] == column for row in cur.fetchall())


def insert_save_result(
    db_path: Path,
    item_id: str,
    url: str,
    success: bool,
    exit_code: Optional[int],
    saved_path: Optional[str],
) -> int:
    with sqlite3.connect(db_path) as conn:
        # Decide which column to use depending on existing schema
        col = "item_id" if _has_column(conn, "saves", "item_id") else "user_id"
        cur = conn.execute(
            f"INSERT INTO saves({col}, url, success, exit_code, saved_path) VALUES (?, ?, ?, ?, ?)",
            (item_id, url, 1 if success else 0, exit_code, saved_path),
        )
        return int(cur.lastrowid)
