"""
Summarization Worker Celery Tasks.

Defines Celery tasks for article summarization.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List

# Add shared module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from celery import Task
from shared.celery_config import celery_app, configure_for_worker
from shared.config import get_settings, configure_logging
from shared.db import get_session, ArchiveArtifact, ArticleSummary, UrlMetadata

# Configure for summarization worker
configure_for_worker("summarization")

logger = logging.getLogger(__name__)


class SummarizationTask(Task):
    """Base class for summarization tasks."""

    autoretry_for = (Exception,)
    retry_backoff = True
    retry_backoff_max = 300
    retry_jitter = True
    max_retries = 3

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle task failure."""
        logger.error(
            f"Summarization task failed: {exc}",
            exc_info=True,
            extra={"task_id": task_id, "kwargs": kwargs},
        )


@celery_app.task(base=SummarizationTask, bind=True, name="services.summarization_worker.tasks.summarize_article")
def summarize_article(
    self,
    item_id: str,
    archived_url_id: int,
    force: bool = False,
) -> dict:
    """
    Summarize an article.

    Args:
        item_id: Item identifier
        archived_url_id: Database ID of archived URL
        force: Force re-summarization even if summary exists

    Returns:
        Summarization result dictionary
    """
    logger.info(
        "Starting summarization",
        extra={
            "task_id": self.request.id,
            "item_id": item_id,
            "archived_url_id": archived_url_id,
        },
    )

    settings = get_settings()

    # Check if summarization is enabled
    if not settings.summarization.enabled:
        logger.info("Summarization disabled")
        return {"success": False, "reason": "summarization_disabled"}

    # Check for existing summary
    if not force:
        with get_session() as session:
            existing = (
                session.query(ArticleSummary)
                .filter(ArticleSummary.archived_url_id == archived_url_id)
                .first()
            )
            if existing:
                logger.info("Summary already exists")
                return {
                    "success": True,
                    "reason": "existing",
                    "summary_id": existing.id,
                }

    # Get content from readability artifact
    content = _get_article_content(archived_url_id, settings)
    if not content:
        logger.warning("No content found for summarization")
        return {"success": False, "reason": "no_content"}

    # Generate summary
    try:
        summary_result = _generate_summary(content, settings)

        if summary_result:
            # Store summary
            with get_session() as session:
                summary = ArticleSummary(
                    archived_url_id=archived_url_id,
                    summary_type="default",
                    summary_text=summary_result["summary"],
                    bullet_points=summary_result.get("bullet_points"),
                    model_name=summary_result.get("model_name"),
                )
                session.add(summary)
                session.flush()
                summary_id = summary.id

            logger.info(
                "Summary created",
                extra={"summary_id": summary_id, "item_id": item_id},
            )

            return {
                "success": True,
                "summary_id": summary_id,
                "summary_text": summary_result["summary"],
                "bullet_points": summary_result.get("bullet_points"),
            }
        else:
            return {"success": False, "reason": "generation_failed"}

    except Exception as e:
        logger.error(f"Summarization failed: {e}", exc_info=True)
        raise


@celery_app.task(base=SummarizationTask, bind=True, name="services.summarization_worker.tasks.extract_entities")
def extract_entities(
    self,
    item_id: str,
    archived_url_id: int,
) -> dict:
    """
    Extract named entities from article.

    Args:
        item_id: Item identifier
        archived_url_id: Database ID of archived URL

    Returns:
        Entity extraction result
    """
    logger.info(
        "Starting entity extraction",
        extra={"task_id": self.request.id, "item_id": item_id},
    )

    settings = get_settings()

    # Get content
    content = _get_article_content(archived_url_id, settings)
    if not content:
        return {"success": False, "reason": "no_content"}

    try:
        entities = _extract_entities(content, settings)

        if entities:
            # Store entities
            from shared.db import ArticleEntity

            with get_session() as session:
                for entity in entities:
                    db_entity = ArticleEntity(
                        archived_url_id=archived_url_id,
                        entity=entity["entity"],
                        entity_type=entity.get("type"),
                        confidence=entity.get("confidence"),
                    )
                    session.add(db_entity)

            return {
                "success": True,
                "entity_count": len(entities),
                "entities": entities,
            }
        else:
            return {"success": False, "reason": "no_entities_found"}

    except Exception as e:
        logger.error(f"Entity extraction failed: {e}", exc_info=True)
        raise


@celery_app.task(base=SummarizationTask, bind=True, name="services.summarization_worker.tasks.generate_tags")
def generate_tags(
    self,
    item_id: str,
    archived_url_id: int,
) -> dict:
    """
    Generate tags for article.

    Args:
        item_id: Item identifier
        archived_url_id: Database ID of archived URL

    Returns:
        Tag generation result
    """
    logger.info(
        "Starting tag generation",
        extra={"task_id": self.request.id, "item_id": item_id},
    )

    settings = get_settings()

    # Get content
    content = _get_article_content(archived_url_id, settings)
    if not content:
        return {"success": False, "reason": "no_content"}

    try:
        tags = _generate_tags(content, settings)

        if tags:
            # Store tags
            from shared.db import ArticleTag

            with get_session() as session:
                for tag in tags:
                    db_tag = ArticleTag(
                        archived_url_id=archived_url_id,
                        tag=tag["tag"],
                        source="llm",
                        confidence=tag.get("confidence"),
                    )
                    session.add(db_tag)

            return {
                "success": True,
                "tag_count": len(tags),
                "tags": [t["tag"] for t in tags],
            }
        else:
            return {"success": False, "reason": "no_tags_generated"}

    except Exception as e:
        logger.error(f"Tag generation failed: {e}", exc_info=True)
        raise


def _get_article_content(archived_url_id: int, settings) -> Optional[str]:
    """Get article content for summarization."""
    # First try to get from metadata
    with get_session() as session:
        metadata = (
            session.query(UrlMetadata)
            .filter(UrlMetadata.archived_url_id == archived_url_id)
            .first()
        )
        if metadata and metadata.text:
            return metadata.text

    # Fall back to readability artifact
    with get_session() as session:
        artifact = (
            session.query(ArchiveArtifact)
            .filter(
                ArchiveArtifact.archived_url_id == archived_url_id,
                ArchiveArtifact.archiver == "readability",
                ArchiveArtifact.success == True,
            )
            .first()
        )

        if artifact and artifact.saved_path:
            import json

            path = Path(artifact.saved_path)
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("text") or data.get("content")

    return None


def _generate_summary(content: str, settings) -> Optional[dict]:
    """Generate summary using configured provider."""
    # Truncate content if too long
    max_chars = settings.summarization.chunk_size * 10
    if len(content) > max_chars:
        content = content[:max_chars]

    provider = settings.summarization.providers[0] if settings.summarization.providers else "huggingface"

    if provider == "openai" and settings.summarization.api_key:
        return _summarize_with_openai(content, settings)
    elif provider == "huggingface" and settings.summarization.api_base:
        return _summarize_with_huggingface(content, settings)
    else:
        # Simple extractive summary as fallback
        return _extractive_summary(content)


def _summarize_with_openai(content: str, settings) -> Optional[dict]:
    """Summarize using OpenAI API."""
    try:
        import httpx

        response = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.summarization.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.summarization.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that summarizes articles. Provide a concise summary in 2-3 sentences, followed by 3-5 bullet points with key takeaways.",
                    },
                    {
                        "role": "user",
                        "content": f"Summarize this article:\n\n{content}",
                    },
                ],
                "temperature": 0.3,
                "max_tokens": 500,
            },
            timeout=60,
        )
        response.raise_for_status()

        result = response.json()
        text = result["choices"][0]["message"]["content"]

        # Parse bullet points from response
        lines = text.split("\n")
        summary = []
        bullets = []

        for line in lines:
            line = line.strip()
            if line.startswith("•") or line.startswith("-") or line.startswith("*"):
                bullets.append(line.lstrip("•-* "))
            elif line:
                summary.append(line)

        return {
            "summary": " ".join(summary),
            "bullet_points": bullets,
            "model_name": settings.summarization.model,
        }

    except Exception as e:
        logger.error(f"OpenAI summarization failed: {e}")
        return None


def _summarize_with_huggingface(content: str, settings) -> Optional[dict]:
    """Summarize using HuggingFace TGI."""
    try:
        import httpx

        headers = {"Content-Type": "application/json"}
        if settings.summarization.api_key:
            headers["Authorization"] = f"Bearer {settings.summarization.api_key}"

        response = httpx.post(
            f"{settings.summarization.api_base}/generate",
            headers=headers,
            json={
                "inputs": f"Summarize: {content}",
                "parameters": {
                    "max_new_tokens": 300,
                    "temperature": 0.3,
                },
            },
            timeout=60,
        )
        response.raise_for_status()

        result = response.json()
        text = result.get("generated_text", "")

        return {
            "summary": text,
            "bullet_points": [],
            "model_name": "huggingface-tgi",
        }

    except Exception as e:
        logger.error(f"HuggingFace summarization failed: {e}")
        return None


def _extractive_summary(content: str) -> dict:
    """Simple extractive summary as fallback."""
    sentences = content.split(".")
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]

    # Take first few sentences as summary
    summary_sentences = sentences[:3]
    summary = ". ".join(summary_sentences) + "." if summary_sentences else content[:500]

    return {
        "summary": summary,
        "bullet_points": [],
        "model_name": "extractive",
    }


def _extract_entities(content: str, settings) -> List[dict]:
    """Extract named entities from content."""
    # Simple regex-based extraction as fallback
    import re

    entities = []

    # Find capitalized phrases (potential names/organizations)
    pattern = r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b"
    matches = re.findall(pattern, content)

    seen = set()
    for match in matches:
        if match not in seen and len(match) > 3:
            entities.append({
                "entity": match,
                "type": "UNKNOWN",
                "confidence": 0.5,
            })
            seen.add(match)

    return entities[:20]  # Limit to 20 entities


def _generate_tags(content: str, settings) -> List[dict]:
    """Generate tags for content."""
    # Simple keyword extraction as fallback
    import re
    from collections import Counter

    # Tokenize and count words
    words = re.findall(r"\b[a-z]{4,}\b", content.lower())
    word_counts = Counter(words)

    # Filter common words
    common_words = {
        "that", "this", "with", "from", "have", "been", "were",
        "they", "their", "which", "about", "would", "could",
        "should", "there", "when", "what", "where", "will",
    }

    tags = []
    for word, count in word_counts.most_common(20):
        if word not in common_words and count >= 2:
            tags.append({
                "tag": word,
                "confidence": min(count / 10, 1.0),
            })

    return tags[:10]  # Limit to 10 tags
