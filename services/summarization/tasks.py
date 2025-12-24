import os
import logging
import httpx
from celery import shared_task
from .logic.summarizer import SummaryService
from .logic.providers import ProviderFactory, ProviderChain
from .logic.summarization import ArticleChunker, PromptBuilder, ResponseParser
from core.config import get_settings

# --- Service URLs ---
DATA_SERVICE_URL = os.environ.get("DATA_SERVICE_URL", "http://data:8000")
STORAGE_SERVICE_URL = os.environ.get("STORAGE_SERVICE_URL", "http://storage:8000")

# --- Configure logging ---
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

@shared_task(name='summarization.tasks.start_summary')
def start_summary(archived_url_id: int, artifact_path: str):
    """
    Celery task to generate a summary for a given archived URL.
    """
    logger.info(f"Received summary task for ArchivedUrl ID: {archived_url_id}, artifact: {artifact_path}")

    # 1. Fetch the content from the Storage Service
    with httpx.Client() as client:
        try:
            response = client.get(f"{STORAGE_SERVICE_URL}/files/{artifact_path}")
            response.raise_for_status()
            content = response.text
            logger.info(f"Successfully fetched content for {artifact_path}")
        except Exception as e:
            logger.error(f"Failed to fetch content from {artifact_path}: {e}")
            return {"status": "error", "message": "Failed to fetch content"}

    # 2. Set up the Summarization Service
    # This is a simplified setup. In a real application, you'd manage settings
    # more cleanly, perhaps via environment variables passed to the service.
    settings = get_settings()
    provider_factory = ProviderFactory(settings.summarization)
    providers = provider_factory.create_all_configured()
    provider_chain = ProviderChain(providers=providers)
    chunker = ArticleChunker(chunk_size=settings.summarization.chunk_size)
    prompt_builder = PromptBuilder()
    response_parser = ResponseParser()

    summarizer = SummaryService(
        provider=provider_chain,
        prompt_builder=prompt_builder,
        response_parser=response_parser,
        chunker=chunker,
        settings=settings,
    )

    # 3. Generate the summary
    try:
        summary_text = summarizer.summarize_content(content)
        if not summary_text:
            raise Exception("Summary generation returned empty content")
        logger.info(f"Successfully generated summary for ArchivedUrl ID: {archived_url_id}")
    except Exception as e:
        logger.error(f"Failed to generate summary for {archived_url_id}: {e}")
        return {"status": "error", "message": "Failed to generate summary"}

    # 4. Save the summary to the Data Service
    with httpx.Client() as client:
        try:
            payload = {
                "archived_url_id": archived_url_id,
                "summary_text": summary_text,
                "summary_type": "default", # Or determine this dynamically
            }
            # This endpoint needs to be created in the Data Service
            response = client.post(f"{DATA_SERVICE_URL}/summaries", json=payload)
            response.raise_for_status()
            summary_record = response.json()
            logger.info(f"Successfully saved summary record with ID: {summary_record.get('id')}")
        except Exception as e:
            logger.error(f"Failed to save summary for {archived_url_id}: {e}")
            return {"status": "error", "message": "Failed to save summary"}

    return {"status": "success", "summary_id": summary_record.get('id')}
