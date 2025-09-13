import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any


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
        # Add new columns for async batch workflow if missing
        try:
            if not _has_column(conn, "saves", "status"):
                conn.execute("ALTER TABLE saves ADD COLUMN status TEXT DEFAULT 'pending';")
        except sqlite3.OperationalError:
            pass
        try:
            if not _has_column(conn, "saves", "task_id"):
                conn.execute("ALTER TABLE saves ADD COLUMN task_id TEXT;")
        except sqlite3.OperationalError:
            pass
        try:
            if not _has_column(conn, "saves", "name"):
                conn.execute("ALTER TABLE saves ADD COLUMN name TEXT;")
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
    # Ensure schema exists (idempotent)
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        # Decide which column to use depending on existing schema
        col = "item_id" if _has_column(conn, "saves", "item_id") else "user_id"
        if _has_column(conn, "saves", "status"):
            cur = conn.execute(
                f"INSERT INTO saves({col}, url, success, exit_code, saved_path, status) VALUES (?, ?, ?, ?, ?, ?)",
                (item_id, url, 1 if success else 0, exit_code, saved_path, "success" if success else "failed"),
            )
        else:
            cur = conn.execute(
                f"INSERT INTO saves({col}, url, success, exit_code, saved_path) VALUES (?, ?, ?, ?, ?)",
                (item_id, url, 1 if success else 0, exit_code, saved_path),
            )
        return int(cur.lastrowid)


def insert_pending_save(
    db_path: Path,
    item_id: str,
    url: str,
    task_id: str,
    name: Optional[str] = None,
) -> int:
    """Insert a pending save row for async processing and return rowid."""
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        col = "item_id" if _has_column(conn, "saves", "item_id") else "user_id"
        cols = [col, "url", "success"]
        vals = [item_id, url, 0]  # success=0 initially (pending)
        if _has_column(conn, "saves", "status"):
            cols.append("status")
            vals.append("pending")
        if _has_column(conn, "saves", "task_id"):
            cols.append("task_id")
            vals.append(task_id)
        if name is not None and _has_column(conn, "saves", "name"):
            cols.append("name")
            vals.append(name)
        placeholders = ", ".join(["?"] * len(vals))
        sql = f"INSERT INTO saves({', '.join(cols)}) VALUES ({placeholders})"
        cur = conn.execute(sql, tuple(vals))
        return int(cur.lastrowid)


def finalize_save_result(
    db_path: Path,
    rowid: int,
    success: bool,
    exit_code: Optional[int],
    saved_path: Optional[str],
) -> None:
    """Update an existing row with final result and status."""
    init_db(db_path)
    status = "success" if success else "failed"
    with sqlite3.connect(db_path) as conn:
        if _has_column(conn, "saves", "status"):
            conn.execute(
                "UPDATE saves SET success=?, exit_code=?, saved_path=?, status=? WHERE rowid=?",
                (1 if success else 0, exit_code, saved_path, status, rowid),
            )
        else:
            conn.execute(
                "UPDATE saves SET success=?, exit_code=?, saved_path=? WHERE rowid=?",
                (1 if success else 0, exit_code, saved_path, rowid),
            )


def get_task_rows(db_path: Path, task_id: str) -> List[Dict[str, Any]]:
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT rowid, * FROM saves WHERE task_id = ? ORDER BY rowid ASC",
            (task_id,),
        )
        return [dict(row) for row in cur.fetchall()]
