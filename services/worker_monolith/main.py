import logging
from common.celery_config import (
    celery_app,
    TASK_ARCHIVE_MONOLITH,
)
from common.core.config import get_settings
from common.core.command_runner import CommandRunner
from common.storage.local_file_storage import LocalFileStorage
from common.storage.gcs_file_storage import GCSFileStorage
from common.storage.postgres_storage import PostgresStorage
from common.storage.firestore_storage import FirestoreStorage
from common.storage.dual_database_storage import DualDatabaseStorage
from common.db.repository import insert_save_result

from services.worker_monolith.archivers.monolith import MonolithArchiver

logger = logging.getLogger(__name__)
settings = get_settings()

command_runner = CommandRunner(debug=settings.log_level == "DEBUG")

file_storage_providers = []
for provider_name in settings.storage_providers:
    if provider_name == 'gcs':
        try:
            gcs_storage = GCSFileStorage(
                bucket_name=settings.gcs.bucket,
                project_id=settings.gcs.project_id
            )
            file_storage_providers.append(gcs_storage)
        except Exception as e:
            logger.error(f"Failed to initialize GCS storage: {e}")
    elif provider_name == 'local':
        backup_dir = settings.local_backup_dir or settings.data_dir
        local_storage = LocalFileStorage(root_dir=backup_dir)
        file_storage_providers.append(local_storage)

if not file_storage_providers:
    file_storage_providers.append(LocalFileStorage(root_dir=settings.data_dir))

primary_db = PostgresStorage()
db_storage = primary_db
if settings.enable_dual_persistence and settings.firestore.project_id:
    try:
        replica_db = FirestoreStorage(project_id=settings.firestore.project_id)
        db_storage = DualDatabaseStorage(
            postgres=primary_db,
            firestore=replica_db,
            failure_mode=settings.dual_write_failure_mode
        )
    except Exception as e:
        logger.warning(f"Failed to initialize Firestore replica: {e}")

monolith_archiver = MonolithArchiver(command_runner, settings, file_storage_providers, db_storage)

@celery_app.task(name=TASK_ARCHIVE_MONOLITH)
def archive_monolith(url: str, item_id: str):
    logger.info(f"Starting monolith for {url} ({item_id})")

    if hasattr(monolith_archiver, 'archive_with_storage') and file_storage_providers:
        result = monolith_archiver.archive_with_storage(url=url, item_id=item_id)
    else:
        result = monolith_archiver.archive(url=url, item_id=item_id)

    db_rowid = None
    try:
        db_rowid = insert_save_result(
            db_path=settings.database.resolved_path(settings.data_dir),
            item_id=item_id,
            url=url,
            success=result.success,
            exit_code=result.exit_code,
            saved_path=result.saved_path,
            archiver_name="monolith",
        )
    except Exception as e:
        logger.error(f"Failed to update DB for monolith: {e}")

    return {
        "success": result.success,
        "exit_code": result.exit_code,
        "saved_path": str(result.saved_path) if result.saved_path else None,
        "db_rowid": db_rowid,
    }
