from contextlib import asynccontextmanager
import queue
import subprocess

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from api import router as api_router
from web import router as web_router
from archivers.monolith import MonolithArchiver
from archivers.singlefile_cli import SingleFileCLIArchiver
from archivers.screenshot import ScreenshotArchiver
from archivers.pdf import PDFArchiver
from archivers.readability import ReadabilityArchiver
from core.config import get_settings
from db.repository import init_db
from core.ht_runner import HTRunner
from services.summarizer import SummaryService
from task_manager import (
    ArchiverTaskManager,
    SummarizeTask,
    SummarizationCoordinator,
    SummarizationTaskManager,
)


settings = get_settings()
ht_runner = HTRunner(settings.ht_bin, settings.ht_listen, log_path=settings.ht_log_file)


@asynccontextmanager
async def lifespan_context(app: FastAPI):
    # Startup
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    init_db(settings.resolved_db_path)
    # Log chromium and monolith versions (best-effort)
    try:
        out = subprocess.check_output([settings.chromium_bin, "--version"], text=True).strip()
        print(f"Chromium: {out}")
    except Exception:
        print("Chromium: not available")
    try:
        out = subprocess.check_output([settings.monolith_bin, "--version"], text=True).strip()
        print(f"Monolith: {out}")
    except Exception:
        print("Monolith: not available")
    try:
        out = subprocess.check_output([settings.singlefile_bin, "--version"], text=True).strip()
        print(f"SingleFile CLI: {out}")
    except Exception:
        print("SingleFile CLI: not available")
    try:
        out = subprocess.check_output([settings.ht_bin, "--version"], text=True).strip()
        print(f"ht: {out}")
    except Exception:
        print("ht: not available")
    
    print(f"Summarization enabled: {settings.enable_summarization}")
    if settings.start_ht:
        ht_runner.start()
    # Register archivers on app state
    app.state.archivers = {
        # Registration order matters when using the "all" pipeline
        # Run readability first so its DOM dump can be reused by monolith.
        "readability": ReadabilityArchiver(ht_runner=ht_runner, settings=settings),
        "monolith": MonolithArchiver(ht_runner=ht_runner, settings=settings),
        "singlefile-cli": SingleFileCLIArchiver(ht_runner=ht_runner, settings=settings),
        # Run Chromium-derived captures last
        "screenshot": ScreenshotArchiver(ht_runner=ht_runner, settings=settings),
        "pdf": PDFArchiver(ht_runner=ht_runner, settings=settings),
    }
    # Expose ht runner on app state for APIs
    app.state.ht_runner = ht_runner
    app.state.summarizer = SummaryService(settings)
    summarization_queue: "queue.Queue[SummarizeTask]" = queue.Queue()
    app.state.summarization_manager = SummarizationTaskManager(
        settings,
        summarizer=app.state.summarizer,
        task_queue=summarization_queue,
    )
    app.state.summarization_manager.start()
    app.state.summarizer_manager = app.state.summarization_manager
    app.state.summarization_queue = summarization_queue
    app.state.summarization = SummarizationCoordinator(
        settings,
        summarizer=app.state.summarizer,
        task_queue=summarization_queue,
    )
    app.state.summarization_coordinator = app.state.summarization
    # Inject archivers into task manager now that they exist
    app.state.task_manager = ArchiverTaskManager(
        settings,
        app.state.archivers,
        summarization=app.state.summarization,
    )
    try:
        yield
    finally:
        # Shutdown
        if settings.start_ht:
            try:
                ht_runner.stop()
            except Exception:
                pass


app = FastAPI(title="archiver service", version="0.3.0", lifespan=lifespan_context)

# Mount API routes
app.include_router(api_router)
app.include_router(web_router)

# Serve saved files directly for viewing in UI. During tests the DATA_DIR may
# not exist at import time, so skip existence check here; the lifespan startup
# ensures the directory is created before use.
app.mount(
    "/files",
    StaticFiles(directory=str(settings.data_dir), check_dir=False),
    name="files",
)
