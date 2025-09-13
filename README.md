# monolith + ht wrapper (Docker)

This setup runs [monolith](https://github.com/Y2Z/monolith) inside an interactive shell wrapped by [ht](https://github.com/andyk/ht). It exposes:

- a REST endpoint `POST /save` to request page archiving via monolith
- ht's live terminal preview on port `7681` so you can watch commands run

Saved pages go into a local `./data` directory (mounted to `/data` in the container). Each request must include an `id` to namespace the save, and files are stored under `./data/<id>/monolith/`.

## Quick start

1) Build and start

```
docker compose up --build -d
```

2) Save a page

```
curl -X POST http://localhost:8000/save \
  -H 'Content-Type: application/json' \
  -d '{"id":"user123","url":"https://example.com","name":"example.html"}'
```

Response example:

```
{
  "ok": true,
  "exit_code": 0,
  "saved_path": "/data/user123/monolith/example.html",
  "ht_preview_url": "http://0.0.0.0:7681",
  "id": "user123",
  "db_rowid": 1
}
```

3) Live terminal preview

Open `http://localhost:7681` to watch the terminal session managed by `ht`.

## Files

- `Dockerfile` – builds an image with monolith, ht, and the API server
- `docker-compose.yml` – runs the service and mounts `./data` for output
- `app/server.py` – FastAPI server that bridges HTTP → ht → monolith
- `app/db.py` – SQLite schema and helpers; DB stored at `/data/app.db` by default

## Notes

- The API serializes requests: commands run one at a time in a single shell.
- If you prefer, change the `MONOLITH_BIN` flags/args by editing `server.py`.
- Architecture is auto-detected for binary downloads (x86_64/aarch64 Linux).
