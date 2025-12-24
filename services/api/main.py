from contextlib import asynccontextmanager
import logging
import queue
import subprocess
from typing import Optional

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from services.api.routes import router as api_router
from services.api.routes.firebase import router as firebase_router
from services.api.routes.sync import router as sync_router
from services.api.web import router as web_router
from common.core.config import get_settings
from common.core.logging import setup_logging
from common.storage.local_file_storage import LocalFileStorage
from common.storage.gcs_file_storage import GCSFileStorage
from common.storage.postgres_storage import PostgresStorage
from common.storage.firestore_storage import FirestoreStorage
from common.storage.file_storage import FileStorageProvider
from common.storage.database_storage import DatabaseStorageProvider
from common.celery_config import celery_app
from common.core.ht_runner import HTRunner

settings = get_settings()
setup_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan_context(app: FastAPI):
    # Startup
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    # Initialize HTRunner if binary is configured and available
    if settings.ht_bin:
        import shutil
        ht_path = shutil.which(settings.ht_bin)
        if ht_path:
            logger.info(f"Initializing HTRunner with binary: {ht_path}")
            ht_runner = HTRunner(
                ht_bin=ht_path,
                listen_addr=settings.ht_listen or "127.0.0.1:9999",
                log_path=settings.data_dir / "ht_runner.log"
            )
            try:
                ht_runner.start()
                app.state.ht_runner = ht_runner
                logger.info("HTRunner started")
            except Exception as e:
                logger.error(f"Failed to start HTRunner: {e}")
        else:
            logger.warning(f"HT binary '{settings.ht_bin}' not found in PATH. /ht endpoints will be unavailable.")
    else:
        logger.info("HT binary not configured. /ht endpoints will be unavailable.")

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
            from common.storage.dual_database_storage import DualDatabaseStorage
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
        }
    )

    # Store celery app in state if needed, though mostly global
    app.state.celery = celery_app

    try:
        yield
    finally:
        # Shutdown HTRunner if initialized
        if hasattr(app.state, "ht_runner") and app.state.ht_runner:
            logger.info("Stopping HTRunner...")
            app.state.ht_runner.stop()


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
