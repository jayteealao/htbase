from contextlib import asynccontextmanager
import logging
import queue
import subprocess

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from api import router as api_router
from web import router as web_router
from archivers.factory import ArchiverFactory
from archivers.monolith import MonolithArchiver
from archivers.singlefile_cli import SingleFileCLIArchiver
from archivers.screenshot import ScreenshotArchiver
from archivers.pdf import PDFArchiver
from archivers.readability import ReadabilityArchiver
from core.config import get_settings
from core.logging import setup_logging
from core.utils import cleanup_chromium_singleton_locks
# init_db is deprecated - engine initialization happens automatically
from core.command_runner import CommandRunner
from services.summarizer import SummaryService
from services.providers import ProviderFactory, ProviderChain
from services.summarization import ArticleChunker, PromptBuilder, ResponseParser
from task_manager import (
    ArchiverTaskManager,
    SummarizeTask,
    SummarizationCoordinator,
    SummarizationTaskManager,
)


settings = get_settings()
setup_logging(settings.log_level)
logger = logging.getLogger(__name__)

command_runner = CommandRunner(debug=settings.log_level == "DEBUG")


@asynccontextmanager
async def lifespan_context(app: FastAPI):
    # Startup
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    # Database initialization happens automatically in get_session()

    # Clean up Chromium singleton locks at startup to prevent exit code 21
    user_data_dir = settings.resolved_chromium_user_data_dir
    user_data_dir.mkdir(parents=True, exist_ok=True)
    cleanup_chromium_singleton_locks(user_data_dir)

    # Log chromium and monolith versions (best-effort)
    try:
        out = subprocess.check_output([settings.chromium_bin, "--version"], text=True).strip()
        logger.info(f"Chromium: {out}")
    except Exception:
        logger.warning("Chromium: not available")
    try:
        out = subprocess.check_output([settings.monolith_bin, "--version"], text=True).strip()
        logger.info(f"Monolith: {out}")
    except Exception:
        logger.warning("Monolith: not available")
    try:
        out = subprocess.check_output([settings.singlefile_bin, "--version"], text=True).strip()
        logger.info(f"SingleFile CLI: {out}")
    except Exception:
        logger.warning("SingleFile CLI: not available")
    logger.info(f"Summarization enabled: {settings.enable_summarization}")
    logger.info(f"CommandRunner debug mode: {command_runner.debug}")

    # Register archivers using factory
    # Registration order matters when using the "all" pipeline
    # Run readability first so its DOM dump can be reused by monolith.
    factory = ArchiverFactory(settings, command_runner)
    factory.register("readability", ReadabilityArchiver)
    factory.register("monolith", MonolithArchiver)
    factory.register("singlefile-cli", SingleFileCLIArchiver)
    # Run Chromium-derived captures last
    factory.register("screenshot", ScreenshotArchiver)
    factory.register("pdf", PDFArchiver)

    app.state.archivers = factory.create_all()
    app.state.archiver_factory = factory  # Store factory for potential dynamic registration
    summarization_queue: "queue.Queue[SummarizeTask]" = queue.Queue()

    # Expose command runner on app state for APIs
    app.state.command_runner = command_runner

    # Build summarization components using dependency injection
    logger.info("Initializing summarization service components")

    # Create provider chain
    provider_factory = ProviderFactory(settings.summarization)
    try:
        providers = provider_factory.create_all_configured()
        provider_chain = ProviderChain(
            providers=providers,
            sticky=settings.summary_provider_sticky
        )
        logger.info(
            "Created provider chain",
            extra={
                "provider_count": len(providers),
                "provider_names": [p.name for p in providers],
                "sticky": settings.summary_provider_sticky,
            }
        )
    except ValueError as e:
        logger.error(f"Failed to create provider chain: {e}")
        provider_chain = None

    # Create orchestration components
    chunker = ArticleChunker(chunk_size=settings.summary_chunk_size)
    prompt_builder = PromptBuilder()
    response_parser = ResponseParser()

    # Assemble SummaryService with all dependencies
    if provider_chain and chunker.is_enabled:
        app.state.summarizer = SummaryService(
            provider=provider_chain,
            prompt_builder=prompt_builder,
            response_parser=response_parser,
            chunker=chunker,
            settings=settings,
        )
        logger.info("SummaryService initialized successfully")
    else:
        app.state.summarizer = None
        logger.warning("SummaryService disabled: provider chain or chunker unavailable")

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
        logger.info("Resuming any pending artifacts...")
        resumed_tasks = app.state.task_manager.resume_pending_artifacts()
        if resumed_tasks:
            logger.info(
                f"Recovered pending artifacts across {len(resumed_tasks)} task(s)."
            )
    except Exception as exc:
        logger.error(f"Failed to resume pending artifacts: {exc}")
    try:
        yield
    finally:
        # Shutdown
        # Clean up Chromium singleton locks at shutdown to ensure clean state for next startup
        try:
            cleanup_chromium_singleton_locks(user_data_dir)
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
