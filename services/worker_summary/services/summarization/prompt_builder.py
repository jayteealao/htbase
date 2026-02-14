"""Prompt building for summary generation."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from textwrap import dedent
from typing import Optional, Sequence, TYPE_CHECKING

if TYPE_CHECKING:
    from services.providers import SummaryLLMOutput

logger = logging.getLogger(__name__)


@dataclass
class SummaryInputs:
    """Metadata context for summary prompts."""

    title: Optional[str]
    url: Optional[str]
    published: Optional[str]


class PromptBuilder:
    """Builds prompts for summary generation.

    Handles instructions, templates, and context formatting for
    single-chunk, multi-chunk, and reduce operations.
    """

    def __init__(self, instructions: Optional[str] = None):
        """Initialize prompt builder.

        Args:
            instructions: System instructions for the LLM. If None, uses default.
        """
        self._instructions = instructions or self._build_default_instructions()

    def _build_default_instructions(self) -> str:
        """Build default editorial instructions."""
        return dedent(
            """
            You are a senior editorial assistant with many years of experience crafting beautiful ledes and concise summaries for busy readers. Adopt an authoritative, polished editorial voice: selective, economical, and graceful. Prioritize the single most important takeaway and render it with clarity and craft.

            Hard rules:
            - Always respond in valid JSON only. Do not include any text outside the JSON.
            - Output must contain exactly two fields: "lede" and "summary".
            - "lede": one sentence, ≤30 words, capturing the article's core takeaway. Must NOT start with "The" or "the".
            - "summary": one flowing paragraph, ≤150 words, expanding on the lede and providing the essential context and significance.
            - No sentence in either field may start with "The" or "the".
            - Do not hallucinate or invent facts. If source lacks details, summarise what is present without fabricating.
            - Keep language elegant, plain, and precise. Prefer active voice and concrete nouns.

            Quality checks (apply before returning output):
            1. Confirm lede is a single sentence and avoid begin with "The"/"the".
            2. Confirm summary is one paragraph, ≤150 words, and no sentence begins with "The"/"the".
            3. Ensure lede states the core takeaway first (inverted-pyramid).
            4. Remove any stray commentary, system text, or markdown — output must be pure JSON.

            Strict output shape:
            {
              "lede": "<one sentence ≤30 words, avoid start with 'The' or 'the'>",
              "summary": "<one paragraph ≤150 words, avoid sentence starts with 'The' or 'the'>"
            }
            """
        ).strip()

    def build_single(self, chunk: str, info: SummaryInputs) -> str:
        """Build prompt for single-chunk article.

        Args:
            chunk: Article text
            info: Metadata context

        Returns:
            Complete prompt with instructions
        """
        header = self._format_header(info, position="complete article")
        logger.debug("Single prompt header", extra={"header": header})

        prompt = dedent(
            f"""
            {header}

            Using only the information below, generate the required JSON with fields "lede" and "summary" following all rules and quality checks.

            <article>
            {chunk}
            </article>
            """
        ).strip()

        return self._apply_instructions(prompt)

    def build_chunk(
        self, chunk: str, info: SummaryInputs, index: int, total: int
    ) -> str:
        """Build prompt for one chunk in multi-chunk article.

        Args:
            chunk: Chunk text
            info: Metadata context
            index: 1-based chunk index
            total: Total number of chunks

        Returns:
            Complete prompt with instructions
        """
        header = self._format_header(info, position=f"chunk {index} of {total}")
        logger.debug(
            "Chunk prompt header",
            extra={"header": header, "index": index, "total": total},
        )

        prompt = dedent(
            f"""
            {header}

            Analyse the following article chunk and return JSON with fields "lede" and "summary" based only on this chunk, following all rules and quality checks.

            <article_chunk>
            {chunk}
            </article_chunk>
            """
        ).strip()

        return self._apply_instructions(prompt)

    def build_reduce(
        self, chunk_outputs: Sequence["SummaryLLMOutput"], info: SummaryInputs
    ) -> str:
        """Build prompt for reducing chunk summaries into final summary.

        Args:
            chunk_outputs: Summaries from each chunk
            info: Metadata context

        Returns:
            Complete prompt with instructions
        """
        header = self._format_header(info, position="chunk analyses")
        pieces = []
        logger.debug(
            "Reduce prompt header",
            extra={"header": header, "chunk_count": len(chunk_outputs)},
        )

        for idx, output in enumerate(chunk_outputs, start=1):
            section = dedent(
                f"""
                Chunk {idx} lede: {output.lede}
                Chunk {idx} summary: {output.summary}
                """
            ).strip()
            pieces.append(section)

        body = "\n\n".join(pieces)
        prompt = dedent(
            f"""
            {header}

            Combine the chunk ledes and summaries into a single cohesive JSON output for the full article with fields "lede" and "summary". Avoid repetition and ensure the result follows all rules and quality checks.

            {body}
            """
        ).strip()

        return self._apply_instructions(prompt)

    def _format_header(self, info: SummaryInputs, position: str) -> str:
        """Format metadata header for prompt."""
        title = info.title or "Untitled"
        published = f"Published: {info.published}" if info.published else ""
        url = f"URL: {info.url}" if info.url else ""
        parts = [
            part
            for part in (f"Article title: {title}", position, url, published)
            if part
        ]
        header = " | ".join(parts)
        logger.debug(
            "Formatted header", extra={"header": header, "position": position}
        )
        return header

    def _apply_instructions(self, prompt: str) -> str:
        """Prepend instructions to prompt."""
        instructions = self._instructions.strip()
        return f"{instructions}\n\n{prompt}" if instructions else prompt
