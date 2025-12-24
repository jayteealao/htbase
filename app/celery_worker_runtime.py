from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Optional

from archivers.factory import ArchiverFactory
from archivers.monolith import MonolithArchiver
from archivers.pdf import PDFArchiver
from archivers.readability import ReadabilityArchiver
from archivers.screenshot import ScreenshotArchiver
from archivers.singlefile_cli import SingleFileCLIArchiver
from core.command_runner import CommandRunner
from core.config import AppSettings, get_settings
from core.logging import setup_logging
from services.summarizer import SummaryService
from services.providers import ProviderFactory, ProviderChain
from services.summarization import ArticleChunker, PromptBuilder, ResponseParser
from storage.database_storage import DatabaseStorageProvider
from storage.file_storage import FileStorageProvider
from storage.firestore_storage import FirestoreStorage
from storage.gcs_file_storage import GCSFileStorage
from storage.local_file_storage import LocalFileStorage
from storage.postgres_storage import PostgresStorage
from task_manager import SummarizationTaskManager, SummarizationCoordinator
from task_manager.archiver import ArchiverTaskManager

logger = logging.getLogger(__name__)


@dataclass
class WorkerRuntime:
    settings: AppSettings
    archivers: Dict[str, object]
    file_storage_providers: list[FileStorageProvider]
    db_storage: DatabaseStorageProvider
    summarization_manager: Optional[SummarizationTaskManager]
    summarization: Optional[SummarizationCoordinator]
    archiver_task_manager: ArchiverTaskManager


_worker_runtime: Optional[WorkerRuntime] = None


def _build_storage(settings: AppSettings) -> tuple[list[FileStorageProvider], DatabaseStorageProvider]:
    file_storage_providers: list[FileStorageProvider] = []

    for provider_name in settings.storage_providers:
        if provider_name == "gcs":
            try:
                gcs_storage = GCSFileStorage(
                    bucket_name=settings.gcs.bucket,
                    project_id=settings.gcs.project_id,
                )
                file_storage_providers.append(gcs_storage)
                logger.info("Initialized GCS storage for worker", extra={"bucket": settings.gcs.bucket})
            except Exception as exc:
                logger.warning("GCS storage unavailable for worker", extra={"error": str(exc)})
        elif provider_name == "local":
            backup_dir = settings.local_backup_dir or settings.data_dir
            local_storage = LocalFileStorage(root_dir=backup_dir)
            file_storage_providers.append(local_storage)
            logger.info("Initialized local storage for worker", extra={"path": backup_dir})

    if not file_storage_providers:
        file_storage_providers.append(LocalFileStorage(root_dir=settings.data_dir))
        logger.warning("No storage providers configured for worker; defaulting to local")

    primary_db: DatabaseStorageProvider = PostgresStorage()
    replica_db: Optional[DatabaseStorageProvider] = None

    if settings.enable_dual_persistence and settings.firestore.project_id:
        try:
            replica_db = FirestoreStorage(project_id=settings.firestore.project_id)
            logger.info("Initialized Firestore replica for worker", extra={"project_id": settings.firestore.project_id})
        except Exception as exc:
            logger.warning("Firestore unavailable for worker", extra={"error": str(exc)})

    if replica_db:
        from storage.dual_database_storage import DualDatabaseStorage

        db_storage: DatabaseStorageProvider = DualDatabaseStorage(
            postgres=primary_db,
            firestore=replica_db,
            failure_mode=settings.dual_write_failure_mode,
        )
    else:
        db_storage = primary_db

    return file_storage_providers, db_storage


def _build_summarization(settings: AppSettings) -> tuple[Optional[SummaryService], Optional[SummarizationTaskManager], Optional[SummarizationCoordinator]]:
    if settings.service_role.strip().lower() == "archiver-worker":
        logger.info("Archiver-only worker role: skipping summarization bootstrap")
        return None, None, None

    provider_factory = ProviderFactory(settings.summarization)
    try:
        providers = provider_factory.create_all_configured()
    except ValueError as exc:
        logger.warning("Summarization providers misconfigured", extra={"error": str(exc)})
        providers = []

    chain = ProviderChain(providers=providers, sticky=settings.summarization.provider_sticky) if providers else None

    chunker = ArticleChunker(chunk_size=settings.summarization.chunk_size)
    prompt_builder = PromptBuilder()
    response_parser = ResponseParser()

    summarizer = None
    if chain and chunker.is_enabled:
        summarizer = SummaryService(
            provider=chain,
            prompt_builder=prompt_builder,
            response_parser=response_parser,
            chunker=chunker,
            settings=settings,
        )

    queue_manager = SummarizationTaskManager(settings, summarizer=summarizer)
    coordinator = SummarizationCoordinator(settings, summarizer=summarizer, task_queue=queue_manager.queue)
    queue_manager.start()
    return summarizer, queue_manager, coordinator


def get_worker_runtime() -> WorkerRuntime:
    global _worker_runtime
    if _worker_runtime is not None:
        return _worker_runtime

    settings = get_settings()
    setup_logging(settings.log_level)

    file_storage_providers, db_storage = _build_storage(settings)

    command_runner = CommandRunner(debug=settings.log_level == "DEBUG")
    factory = ArchiverFactory(settings, command_runner, file_storage_providers, db_storage)
    archiver_classes = {
        "readability": ReadabilityArchiver,
        "monolith": MonolithArchiver,
        "singlefile-cli": SingleFileCLIArchiver,
        "screenshot": ScreenshotArchiver,
        "pdf": PDFArchiver,
    }
    for archiver_name in settings.archivers:
        archiver_cls = archiver_classes.get(archiver_name)
        if archiver_cls is None:
            logger.warning("Worker skipping unknown archiver", extra={"archiver": archiver_name})
            continue
        factory.register(archiver_name, archiver_cls)
    archivers = factory.create_all()

    summarizer, summary_manager, summarization_coordinator = _build_summarization(settings)

    task_manager = ArchiverTaskManager(
        settings,
        archivers,
        summarization=summarization_coordinator,
    )

    _worker_runtime = WorkerRuntime(
        settings=settings,
        archivers=archivers,
        file_storage_providers=file_storage_providers,
        db_storage=db_storage,
        summarization_manager=summary_manager,
        summarization=summarization_coordinator,
        archiver_task_manager=task_manager,
    )
    return _worker_runtime
