from pathlib import Path


def test_end_to_end_save_flow(test_client):
    # Treat this as E2E: HTTP -> routing -> archiver -> file -> DB
    client = test_client
    payload = {"id": "e2e-1", "url": "https://example.org/foo", "name": "foo.html"}
    resp = client.post("/save", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    saved = Path(body["saved_path"])
    assert saved.exists()

    # Second call with a different name writes a second file and gets a new row
    payload2 = {"id": "e2e-1", "url": "https://example.org/foo", "name": "foo2.html"}
    resp2 = client.post("/save", json=payload2)
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2["db_rowid"] != body["db_rowid"]
    assert Path(body2["saved_path"]).exists()

