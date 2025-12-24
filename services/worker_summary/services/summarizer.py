from __future__ import annotations

import asyncio
import logging
import re
from typing import List, Optional, Sequence, Tuple

from common.core.config import AppSettings
from common.db import ArchivedUrlRepository, ArticleSummaryRepository, UrlMetadataRepository
from services.providers import ProviderChain, SummaryLLMOutput, SummaryProvider
from services.summarization import ArticleChunker, PromptBuilder, ResponseParser, SummaryInputs

logger = logging.getLogger(__name__)


class SummaryService:
    """Pure orchestrator for summary generation.

    Coordinates metadata fetching, chunking, prompt building, generation,
    parsing, and persistence. All specialized logic is delegated to injected
    dependencies.
    """

    def __init__(
        self,
        provider: SummaryProvider | ProviderChain,
        prompt_builder: PromptBuilder,
        response_parser: ResponseParser,
        chunker: ArticleChunker,
        settings: AppSettings,
    ):
        """Initialize summary service.

        Args:
            provider: Provider or provider chain for LLM calls
            prompt_builder: Builds prompts for generation
            response_parser: Parses LLM responses
            chunker: Chunks article text
            settings: App settings (for DB paths, model name, etc.)
        """
        self.provider = provider
        self.prompt_builder = prompt_builder
        self.response_parser = response_parser
        self.chunker = chunker
        self.settings = settings

        # Build whitelist for tag extraction (legacy feature)
        self._whitelist_entries: List[Tuple[str, re.Pattern[str]]] = (
            self._build_whitelist(settings.summarization.tag_whitelist)
        )

    def _build_whitelist(
        self, raw_tags: Sequence[str]
    ) -> List[Tuple[str, re.Pattern[str]]]:
        """Build regex patterns for tag whitelist."""
        entries: List[Tuple[str, re.Pattern[str]]] = []
        for raw_tag in raw_tags:
            tag = raw_tag.strip()
            if not tag:
                continue
            pattern = re.compile(rf"(?<!\w){re.escape(tag)}(?!\w)", re.IGNORECASE)
            entries.append((tag, pattern))
        return entries

    @property
    def is_enabled(self) -> bool:
        """Check if service is properly configured."""
        return bool(self.provider and self.prompt_builder and self.response_parser and self.chunker)

    def generate_for_archived_url(self, archived_url_id: int) -> bool:
        """Generate summary for an archived URL.

        Main entry point called by summarization task manager.

        Args:
            archived_url_id: ID of archived URL to summarize

        Returns:
            True if summary generated and persisted successfully
        """
        if not self.is_enabled:
            logger.warning("SummaryService not properly configured")
            return False

        # Reset provider chain session for this article
        if isinstance(self.provider, ProviderChain):
            self.provider.reset_session()

        logger.info(
            "Starting summarization run", extra={"archived_url_id": archived_url_id}
        )

        # Check provider health
        if isinstance(self.provider, ProviderChain):
            health_results = asyncio.run(self.provider.check_all_health())
            healthy_count = sum(1 for _, health in health_results if health.healthy)
            if healthy_count == 0:
                logger.error(
                    "All providers unhealthy; aborting summarization",
                    extra={"archived_url_id": archived_url_id},
                )
                return False
            logger.info(
                "Provider health check complete",
                extra={
                    "archived_url_id": archived_url_id,
                    "healthy_count": healthy_count,
                    "total_count": len(health_results),
                },
            )

        # Prepare context
        prepared = self._prepare_summary_context(archived_url_id)
        if not prepared:
            return False

        summary_inputs, base_text = prepared
        chunk_texts = self.chunker.chunk(base_text)

        logger.info(
            "Prepared article text",
            extra={
                "archived_url_id": archived_url_id,
                "chunk_count": len(chunk_texts),
                "chunk_size": self.chunker.chunk_size,
            },
        )

        # Generate summaries
        generated = self._generate_outputs(
            archived_url_id=archived_url_id,
            chunk_texts=chunk_texts,
            summary_inputs=summary_inputs,
        )
        if not generated:
            return False

        chunk_outputs, final_output = generated

        # Persist results
        return self._persist_outputs(
            archived_url_id=archived_url_id,
            final_output=final_output,
            chunk_outputs=chunk_outputs,
            source_text=base_text,
        )

    def _prepare_summary_context(
        self, archived_url_id: int
    ) -> Optional[Tuple[SummaryInputs, str]]:
        """Fetch metadata and prepare context for summarization."""
        metadata_repo = UrlMetadataRepository(self.settings.database.resolved_path(settings.data_dir))
        url_repo = ArchivedUrlRepository(self.settings.database.resolved_path(settings.data_dir))

        metadata = metadata_repo.get_by_archived_url(archived_url_id)
        if metadata is None or not (metadata.text and metadata.text.strip()):
            logger.warning(
                "Skipping summarization: no metadata text",
                extra={"archived_url_id": archived_url_id},
            )
            return None

        article = url_repo.get_by_id(archived_url_id)
        summary_inputs = SummaryInputs(
            title=getattr(metadata, "title", None) or getattr(article, "name", None),
            url=getattr(article, "url", None),
            published=getattr(metadata, "published", None),
        )
        base_text = metadata.text.strip()
        return summary_inputs, base_text

    def _generate_outputs(
        self,
        *,
        archived_url_id: int,
        chunk_texts: Sequence[str],
        summary_inputs: SummaryInputs,
    ) -> Optional[Tuple[List[SummaryLLMOutput], SummaryLLMOutput]]:
        """Orchestrate generation using provider."""
        if len(chunk_texts) == 1:
            result = self._run_single_chunk(chunk_texts[0], summary_inputs)
            if result is None:
                logger.warning(
                    "Summarization aborted: LLM call failed",
                    extra={"archived_url_id": archived_url_id},
                )
                return None
            return [result], result

        done = self._run_multi_chunk(chunk_texts, summary_inputs)
        if not done:
            logger.warning(
                "Summarization aborted: chunk or reduce step failed",
                extra={"archived_url_id": archived_url_id},
            )
            return None
        return done

    def _run_single_chunk(
        self, chunk: str, summary_inputs: SummaryInputs
    ) -> Optional[SummaryLLMOutput]:
        """Handle single-chunk article."""
        prompt = self.prompt_builder.build_single(chunk, summary_inputs)

        raw = asyncio.run(self._generate(prompt))
        if raw is None:
            return None

        return self.response_parser.parse(raw, label="Single chunk")

    def _run_multi_chunk(
        self, chunk_texts: Sequence[str], summary_inputs: SummaryInputs
    ) -> Optional[Tuple[List[SummaryLLMOutput], SummaryLLMOutput]]:
        """Handle multi-chunk article with map-reduce pattern."""
        # Map: generate summary for each chunk
        prompts = [
            self.prompt_builder.build_chunk(txt, summary_inputs, idx + 1, len(chunk_texts))
            for idx, txt in enumerate(chunk_texts)
        ]

        try:
            raw_results = asyncio.run(self._generate_batch(prompts))
        except Exception:
            logger.error("Batch generation failed", exc_info=True)
            return None

        if any(r is None for r in raw_results):
            logger.warning("Some chunks failed to generate")
            return None

        chunk_outputs = []
        for idx, raw in enumerate(raw_results):
            if raw is None:
                return None
            parsed = self.response_parser.parse(raw, label=f"Chunk {idx + 1}")
            if parsed is None:
                return None
            chunk_outputs.append(parsed)

        # Reduce: combine chunk summaries into final summary
        reduce_prompt = self.prompt_builder.build_reduce(chunk_outputs, summary_inputs)

        raw_reduced = asyncio.run(self._generate(reduce_prompt))
        if raw_reduced is None:
            logger.warning("Reduce step failed")
            return None

        reduced = self.response_parser.parse(raw_reduced, label="Reduced")
        if reduced is None:
            return None

        return chunk_outputs, reduced

    async def _generate(self, prompt: str) -> Optional[str]:
        """Generate single response via provider."""
        if isinstance(self.provider, ProviderChain):
            return await self.provider.generate(prompt)
        else:
            return await self.provider.generate(prompt)

    async def _generate_batch(self, prompts: List[str]) -> List[Optional[str]]:
        """Generate batch of responses via provider."""
        if isinstance(self.provider, ProviderChain):
            return await self.provider.generate_batch(prompts)
        else:
            return await self.provider.generate_batch(prompts)

    def _persist_outputs(
        self,
        *,
        archived_url_id: int,
        final_output: SummaryLLMOutput,
        chunk_outputs: Sequence[SummaryLLMOutput],
        source_text: str,
    ) -> bool:
        """Persist summary to database."""
        summary_text = final_output.summary.strip()
        if not summary_text:
            summary_text = " ".join(
                output.summary.strip()
                for output in chunk_outputs
                if output.summary.strip()
            )
        summary_text = summary_text.strip()
        if not summary_text:
            logger.warning(
                "No summary generated; aborting", extra={"archived_url_id": archived_url_id}
            )
            return False

        # Store the lede in the bullet_points column as a single-item list
        lede_text = (final_output.lede or "").strip()
        bullets = [lede_text] if lede_text else None

        summary_repo = ArticleSummaryRepository(self.settings.database.resolved_path(settings.data_dir))
        summary_repo.upsert(
            archived_url_id=archived_url_id,
            summary_type="default",
            summary_text=summary_text,
            bullet_points=bullets,
            model_name=self.settings.summarization.model,
        )
        logger.info(
            "Completed summarization run",
            extra={
                "archived_url_id": archived_url_id,
                "summary_length": len(summary_text),
            },
        )
        return True
