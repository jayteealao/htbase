from __future__ import annotations

import sys
from pathlib import Path
from typing import Generator

import pytest

# Ensure the application package is importable as a flat module set
_ROOT = Path(__file__).resolve().parents[1]
_APP = str(_ROOT / "app")
if _APP not in sys.path:
    sys.path.insert(0, _APP)


@pytest.fixture()
def temp_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Configure app to use a temp data dir and disable ht runner
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "data" / "app.db"))
    monkeypatch.setenv("START_HT", "false")


@pytest.fixture()
def test_client(temp_env) -> Generator:
    # Import here so env vars apply before settings load
    from fastapi.testclient import TestClient
    import server

    client = TestClient(server.app)
    # Install dummy archiver to avoid external binaries
    from archivers.base import BaseArchiver
    from core.config import get_settings
    from models import ArchiveResult
    from core.utils import sanitize_filename

    class DummyArchiver(BaseArchiver):
        name = "monolith"

        def archive(self, *, url: str, item_id: str, out_name: str | None) -> ArchiveResult:
            settings = get_settings()
            safe_item = sanitize_filename(item_id)
            out_dir = Path(settings.data_dir) / safe_item / self.name
            out_dir.mkdir(parents=True, exist_ok=True)
            fname = out_name or "page.html"
            if not fname.endswith(".html"):
                fname += ".html"
            out_path = out_dir / fname
            out_path.write_text(f"<html><body>Dummy saved: {url}</body></html>", encoding="utf-8")
            return ArchiveResult(success=True, exit_code=0, saved_path=str(out_path))

    server.app.state.archivers = {"monolith": DummyArchiver(get_settings())}

    try:
        yield client
    finally:
        client.close()
