from pathlib import Path


def test_save_endpoint_creates_record_and_file(test_client):
    client = test_client
    payload = {"id": "user123", "url": "https://example.com/article", "name": "example.html"}
    r = client.post("/save", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["exit_code"] == 0
    assert data["saved_path"].endswith("user123/monolith/example.html")
    assert data["db_rowid"] is not None

    # File exists on disk
    p = Path(data["saved_path"])
    assert p.exists()
    assert p.read_text(encoding="utf-8").startswith("<html>")


def test_archive_dummy_route_works(test_client):
    client = test_client
    payload = {"id": "abc", "url": "https://example.com/x", "name": "x.html"}
    r = client.post("/archive/monolith", json=payload)
    assert r.status_code == 200
    assert r.json()["ok"] is True

