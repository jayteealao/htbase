from contextlib import asynccontextmanager
import logging
import queue
import subprocess
from typing import Optional

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from api import router as api_router
from api.firebase import router as firebase_router
from api.sync import router as sync_router
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
from task_manager.cleanup import CleanupTaskManager
from storage.local_file_storage import LocalFileStorage
from storage.gcs_file_storage import GCSFileStorage
from storage.postgres_storage import PostgresStorage
from storage.firestore_storage import FirestoreStorage
from storage.file_storage import FileStorageProvider
from storage.database_storage import DatabaseStorageProvider


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
    user_data_dir = settings.chromium.resolved_user_data_dir(settings.data_dir)
    user_data_dir.mkdir(parents=True, exist_ok=True)
    cleanup_chromium_singleton_locks(user_data_dir)

    # Log chromium and monolith versions (best-effort)
    try:
        out = subprocess.check_output([settings.chromium.binary, "--version"], text=True).strip()
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
    logger.info(f"Summarization enabled: {settings.summarization.enabled}")
    logger.info(f"CommandRunner debug mode: {command_runner.debug}")

    # Initialize storage providers (support multiple)
    file_storage_providers: list[FileStorageProvider] = []
    db_storage: Optional[DatabaseStorageProvider] = None

    # Initialize file storage providers from configuration
    for provider_name in settings.storage_providers:
        if provider_name == 'gcs':
            try:
                # Initialize GCS storage for production
                gcs_storage = GCSFileStorage(
                    bucket_name=settings.gcs.bucket,
                    project_id=settings.gcs.project_id
                )
                file_storage_providers.append(gcs_storage)
                logger.info(f"Initialized GCS storage: {settings.gcs.bucket}")
            except Exception as e:
                logger.error(f"Failed to initialize GCS storage: {e}")

        elif provider_name == 'local':
            # Use local backup directory if specified, otherwise DATA_DIR
            backup_dir = settings.local_backup_dir or settings.data_dir
            local_storage = LocalFileStorage(root_dir=backup_dir)
            file_storage_providers.append(local_storage)
            logger.info(f"Initialized local storage: {backup_dir}")

    if not file_storage_providers:
        # Fallback to local storage if none configured
        file_storage_providers.append(LocalFileStorage(root_dir=settings.data_dir))
        logger.warning("No storage providers configured, using default local storage")

    # Initialize database storage provider(s)
    # PostgreSQL is always the primary source of truth
    primary_db: DatabaseStorageProvider
    replica_db: Optional[DatabaseStorageProvider] = None

    # Always initialize PostgreSQL as primary
    primary_db = PostgresStorage()
    logger.info("Initialized PostgreSQL (primary database)")

    # Initialize Firestore as replica if dual persistence enabled
    if settings.enable_dual_persistence and settings.firestore.project_id:
        try:
            replica_db = FirestoreStorage(project_id=settings.firestore.project_id)
            logger.info(f"Initialized Firestore (replica database): {settings.firestore.project_id}")

            # Wrap in dual-write coordinator
            from storage.dual_database_storage import DualDatabaseStorage
            db_storage = DualDatabaseStorage(
                postgres=primary_db,
                firestore=replica_db,
                failure_mode=settings.dual_write_failure_mode
            )
            logger.info(
                f"Enabled dual PostgreSQL + Firestore persistence "
                f"(failure_mode={settings.dual_write_failure_mode})"
            )
        except Exception as e:
            logger.warning(f"Failed to initialize Firestore replica: {e}")
            db_storage = primary_db  # Fallback to PostgreSQL only
    else:
        db_storage = primary_db
        logger.info("Using PostgreSQL only (dual persistence disabled)")

    # Register archivers using factory with storage providers
    # Registration order matters when using the "all" pipeline
    # Run readability first so its DOM dump can be reused by monolith.
    factory = ArchiverFactory(settings, command_runner, file_storage_providers, db_storage)
    factory.register("readability", ReadabilityArchiver)
    factory.register("monolith", MonolithArchiver)
    factory.register("singlefile-cli", SingleFileCLIArchiver)
    # Run Chromium-derived captures last
    factory.register("screenshot", ScreenshotArchiver)
    factory.register("pdf", PDFArchiver)

    app.state.archivers = factory.create_all()
    app.state.archiver_factory = factory  # Store factory for potential dynamic registration

    # Store storage providers on app state for API access
    app.state.file_storage_providers = file_storage_providers
    app.state.db_storage = db_storage
    app.state.postgres_storage = primary_db  # Direct access for migrations
    app.state.firestore_storage = replica_db  # Direct access for mobile API (may be None)

    logger.info(
        f"Initialized {len(file_storage_providers)} storage provider(s)",
        extra={
            "providers": [p.provider_name for p in file_storage_providers],
            "db_storage": db_storage.provider_name,
            "archiver_count": len(app.state.archivers)
        }
    )
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
            sticky=settings.summarization.provider_sticky
        )
        logger.info(
            "Created provider chain",
            extra={
                "provider_count": len(providers),
                "provider_names": [p.name for p in providers],
                "sticky": settings.summarization.provider_sticky,
            }
        )
    except ValueError as e:
        logger.error(f"Failed to create provider chain: {e}")
        provider_chain = None

    # Create orchestration components
    chunker = ArticleChunker(chunk_size=settings.summarization.chunk_size)
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
    # Alias for Firebase integration compatibility
    app.state.archiver_task_manager = app.state.task_manager

    try:
        logger.info("Resuming any pending artifacts...")
        resumed_tasks = app.state.task_manager.resume_pending_artifacts()
        if resumed_tasks:
            logger.info(
                f"Recovered pending artifacts across {len(resumed_tasks)} task(s)."
            )
    except Exception as exc:
        logger.error(f"Failed to resume pending artifacts: {exc}")

    # Initialize and start cleanup task manager
    app.state.cleanup_manager = CleanupTaskManager(settings)
    app.state.cleanup_manager.start()
    logger.info("Cleanup task manager started")

    # Inject cleanup manager into all archivers
    for archiver in app.state.archivers.values():
        archiver._cleanup_manager = app.state.cleanup_manager

    # Schedule periodic failed output cleanup (once per day)
    import threading
    import time
    def periodic_failed_cleanup():
        while True:
            time.sleep(86400)  # 24 hours
            try:
                count = app.state.cleanup_manager.cleanup_failed_outputs(
                    retention_days=settings.failed_output_retention_days
                )
                logger.info(f"Periodic cleanup removed {count} failed outputs")
            except Exception as e:
                logger.error(f"Periodic cleanup failed: {e}")

    cleanup_thread = threading.Thread(target=periodic_failed_cleanup, daemon=True)
    cleanup_thread.start()
    logger.info("Started periodic failed output cleanup thread")
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
app.include_router(firebase_router)
app.include_router(sync_router)
app.include_router(web_router)

# Serve saved files directly for viewing in UI only when using local storage backend.
# During tests the DATA_DIR may not exist at import time, so skip existence check here;
# the lifespan startup ensures the directory is created before use.
if settings.storage_backend == 'local':
    app.mount(
        "/files",
        StaticFiles(directory=str(settings.data_dir), check_dir=False),
        name="files",
    )
else:
    # For cloud storage backends (GCS), file serving will be handled by API endpoints
    # that use storage providers instead of static file mounting
    logger.info(
        f"Static file mounting skipped for storage backend: {settings.storage_backend}",
        extra={"storage_backend": settings.storage_backend}
    )
