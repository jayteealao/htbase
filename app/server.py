from contextlib import asynccontextmanager

from fastapi import FastAPI

from api import router as api_router
from archivers.monolith import MonolithArchiver
from config import get_settings
from db import init_db
from ht_runner import HTRunner


settings = get_settings()
ht_runner = HTRunner(settings.ht_bin, settings.ht_listen)


@asynccontextmanager
async def lifespan_context(app: FastAPI):
    # Startup
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    init_db(settings.resolved_db_path)
    if settings.start_ht:
        ht_runner.start()
    # Register archivers on app state
    app.state.archivers = {
        "monolith": MonolithArchiver(ht_runner=ht_runner, settings=settings),
    }
    try:
        yield
    finally:
        # Shutdown
        if settings.start_ht:
            try:
                ht_runner.stop()
            except Exception:
                pass


app = FastAPI(title="archiver service", version="0.2.0", lifespan=lifespan_context)

# Mount API routes
app.include_router(api_router)
