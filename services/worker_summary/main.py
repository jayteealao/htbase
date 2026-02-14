import logging
from common.celery_config import (
    celery_app,
    TASK_GENERATE_SUMMARY,
)
from common.core.config import get_settings
from common.storage.postgres_storage import PostgresStorage

from services.summarizer import SummaryService
from services.providers import ProviderFactory, ProviderChain
from services.summarization import ArticleChunker, PromptBuilder, ResponseParser

logger = logging.getLogger(__name__)
settings = get_settings()

# Initialize summarization components
chunker = ArticleChunker(chunk_size=settings.summarization.chunk_size)
prompt_builder = PromptBuilder()
response_parser = ResponseParser()

provider_chain = None
try:
    provider_factory = ProviderFactory(settings.summarization)
    providers = provider_factory.create_all_configured()
    provider_chain = ProviderChain(
        providers=providers,
        sticky=settings.summarization.provider_sticky
    )
except Exception as e:
    logger.error(f"Failed to initialize provider chain: {e}")

summarizer = None
if provider_chain and chunker.is_enabled:
    summarizer = SummaryService(
        provider=provider_chain,
        prompt_builder=prompt_builder,
        response_parser=response_parser,
        chunker=chunker,
        settings=settings,
    )

db = PostgresStorage()

@celery_app.task(name=TASK_GENERATE_SUMMARY)
def generate_summary(article_id: str | int):
    logger.info(f"Starting summary generation for {article_id}")
    if not summarizer:
        logger.error("Summarizer not initialized")
        return {"success": False, "error": "Summarizer not initialized"}

    # Resolve article_id to archived_url_id (int) if it's a string
    archived_url_id = None
    if isinstance(article_id, int):
        archived_url_id = article_id
    else:
        # Try to find by item_id using ArchiveArtifactRepository which has list_by_item_id
        from common.db import ArchiveArtifactRepository
        repo = ArchiveArtifactRepository(settings.database.resolved_path(settings.data_dir))

        # This returns List[ArchiveArtifact] joined with Url implicitly in query but return type says ArchiveArtifact
        rows = repo.list_by_item_id(article_id)
        if rows:
            # Use the first artifact to identify the archived_url_id
            first_artifact = rows[0]
            if hasattr(first_artifact, 'archived_url_id'):
                archived_url_id = int(first_artifact.archived_url_id)

    if archived_url_id is None:
        # Fallback: try to see if the string IS the integer ID (as string)
        if isinstance(article_id, str) and article_id.isdigit():
            archived_url_id = int(article_id)

    if archived_url_id is None:
        logger.error(f"Could not resolve {article_id} to an archived_url_id")
        return {"success": False, "error": "Could not resolve ID"}

    success = summarizer.generate_for_archived_url(archived_url_id)

    if success:
        return {"success": True, "archived_url_id": archived_url_id}
    else:
        return {"success": False, "error": "Summarization failed"}
