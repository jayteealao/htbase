from __future__ import annotations

import re
import traceback
from dataclasses import dataclass
from textwrap import dedent
from typing import Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, Field

try:
    from chonkie import TokenChunker
except Exception as exc:
    print(f'Failed to import chonkie: {exc}')
    traceback.print_exc()
    TokenChunker = None  # type: ignore[assignment]

try:
    from pydantic_ai import Agent
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openrouter import OpenRouterProvider
except Exception as exc:
    print(f'Failed to import pydantic-ai or components: {exc}')
    traceback.print_exc()
    Agent = None  # type: ignore[assignment]
    OpenAIChatModel = None  # type: ignore[assignment]
    OpenRouterProvider = None  # type: ignore[assignment]

from core.config import AppSettings
from db.repository import (
    get_archived_url_by_id,
    get_metadata_for_archived_url,
    get_save_by_rowid,
    replace_article_entities,
    replace_article_tags,
    upsert_article_summary,
)

class TagSuggestion(BaseModel):
    tag: str = Field(..., min_length=1)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    reason: Optional[str] = None

class EntitySuggestion(BaseModel):
    entity: str = Field(..., min_length=1)
    entity_type: Optional[str] = None
    alias: Optional[str] = None
    reason: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0, le=1)

class SummaryLLMOutput(BaseModel):
    summary: str = Field(..., min_length=1)
    bullet_points: List[str] = Field(default_factory=list, max_length=12)
    recommended_tags: List[TagSuggestion] = Field(default_factory=list)
    entities: List[EntitySuggestion] = Field(default_factory=list)

@dataclass
class SummaryInputs:
    title: Optional[str]
    url: Optional[str]
    published: Optional[str]

class SummaryService:
    """Generate summaries, tags, and entities for archived articles."""

    def __init__(self, settings: AppSettings):
        self.settings = settings
        missing: list[str] = []
        if not settings.enable_summarization:
            missing.append("feature flag disabled")
        if not settings.openrouter_api_key:
            missing.append("OPENROUTER_API_KEY missing")
        if TokenChunker is None:
            missing.append("chonkie not installed")
        if Agent is None or OpenAIChatModel is None or OpenRouterProvider is None:
            missing.append("pydantic-ai or providers unavailable")

        self._enabled = not missing
        self._chunker: Optional[TokenChunker] = None  # type: ignore[type-arg]
        self._agent: Optional[Agent[SummaryLLMOutput]] = None  # type: ignore[misc]
        self._whitelist_entries: List[Tuple[str, re.Pattern[str]]] = []

        for raw_tag in self.settings.summary_tag_whitelist:
            tag = raw_tag.strip()
            if not tag:
                continue
            pattern = re.compile(rf"(?<!\w){re.escape(tag)}(?!\w)", re.IGNORECASE)
            self._whitelist_entries.append((tag, pattern))

        if not self._enabled:
            print(
                "SummaryService disabled: "
                + (", ".join(missing) if missing else "unknown reason")

            )
            return

        try:
            self._chunker = TokenChunker(  # type: ignore[call-arg]
                chunk_size=self.settings.summary_chunk_size
            )
        except Exception:

            print("Failed to initialise TokenChunker; disabling summarization")
            traceback.print_exc()

            self._enabled = False

            return

        try:
            provider = OpenRouterProvider(api_key=self.settings.openrouter_api_key)
            model = OpenAIChatModel(self.settings.summarization_model, provider=provider)
            instructions = dedent(
                f"""
                You are an editorial assistant. Produce concise outputs following the
                SummaryLLMOutput schema. Keep sentences factual, avoid speculation, and
                limit bullet_points to at most {self.settings.summary_max_bullets} items,
                each no longer than 20 words. Only emit entities that appear verbatim in
                the provided material.
                """
            ).strip()
            self._agent = Agent(
                model=model,
                output_type=SummaryLLMOutput,
                instructions=instructions,
            )
        except Exception:

            print("Failed to initialise summarization agent; disabling")
            traceback.print_exc()

            self._enabled = False

    @property
    def is_enabled(self) -> bool:
        return bool(self._enabled and self._agent and self._chunker)

    def generate_for_archived_url(self, archived_url_id: int) -> bool:
        if not self.is_enabled:
            return False

        print(f"Starting summarization run | archived_url_id={archived_url_id}")
        metadata = get_metadata_for_archived_url(
            self.settings.resolved_db_path, archived_url_id
        )
        if metadata is None or not (metadata.text and metadata.text.strip()):
            print(
                f"Skipping summarization: no metadata text | archived_url_id={archived_url_id}"

            )
            return False

        article = get_archived_url_by_id(
            self.settings.resolved_db_path, archived_url_id
        )
        summary_inputs = SummaryInputs(
            title=getattr(metadata, "title", None) or getattr(article, "name", None),
            url=getattr(article, "url", None),
            published=getattr(metadata, "published", None),
        )

        base_text = metadata.text.strip()
        chunk_texts = self._segment_article(base_text)
        if not chunk_texts:
            chunk_texts = [base_text]

        print(
            "Prepared article text | "
            f"archived_url_id={archived_url_id} "
            f"chunk_count={len(chunk_texts)} "
            f"chunk_size={self.settings.summary_chunk_size}"

        )

        chunk_outputs: List[SummaryLLMOutput] = []
        if len(chunk_texts) == 1:
            prompt = self._build_single_prompt(chunk_texts[0], summary_inputs)
            result = self._invoke_agent(prompt)
            if result is None:
                print(
                    f"WARNING: Summarization aborted: LLM call failed | archived_url_id={archived_url_id}"

                )
                return False
            chunk_outputs.append(result)
            final_output = result
        else:
            for idx, chunk_text in enumerate(chunk_texts, start=1):
                prompt = self._build_chunk_prompt(
                    chunk_text, summary_inputs, idx, len(chunk_texts)
                )
                result = self._invoke_agent(prompt)
                if result is None:
                    print(
                        f"WARNING: Summarization aborted: LLM chunk call failed | archived_url_id={archived_url_id} chunk_index={idx}"

                    )
                    return False
                chunk_outputs.append(result)

            reduce_prompt = self._build_reduce_prompt(chunk_outputs, summary_inputs)
            final_output = self._invoke_agent(reduce_prompt)
            if final_output is None:
                print(
                    f"WARNING: Summarization aborted: reduce step failed | archived_url_id={archived_url_id}"

                )
                return False

        return self._persist_outputs(
            archived_url_id=archived_url_id,
            final_output=final_output,
            chunk_outputs=chunk_outputs,
            source_text=base_text,
        )

    # ------------------------------------------------------------------
    # Prompt helpers
    # ------------------------------------------------------------------
    def _build_single_prompt(self, chunk: str, info: SummaryInputs) -> str:
        header = self._format_header(info, position="complete article")
        return dedent(
            f"""
            {header}

            Provide an article-level summary, bullet points, recommended topical tags,
            and named entities. Use only information from the article text.

            <article>
            {chunk}
            </article>
            """
        ).strip()

    def _build_chunk_prompt(
        self, chunk: str, info: SummaryInputs, index: int, total: int
    ) -> str:
        header = self._format_header(info, position=f"chunk {index} of {total}")
        return dedent(
            f"""
            {header}

            Analyse the following article chunk. Summarise only the information in
            this chunk, note key bullet points, suggest topical tags, and list named
            entities present in the text.

            <article_chunk>
            {chunk}
            </article_chunk>
            """
        ).strip()

    def _build_reduce_prompt(
        self, chunk_outputs: Sequence[SummaryLLMOutput], info: SummaryInputs
    ) -> str:
        header = self._format_header(info, position="chunk analyses")
        pieces = []
        for idx, output in enumerate(chunk_outputs, start=1):
            bullets = "\n".join(f"- {pt}" for pt in output.bullet_points)
            tags = ", ".join(tag.tag for tag in output.recommended_tags)
            entities = ", ".join(ent.entity for ent in output.entities)
            section = dedent(
                f"""
                Chunk {idx} summary: {output.summary}
                Bullet points:
                {bullets or '- (none)'}
                Tags: {tags or 'n/a'}
                Entities: {entities or 'n/a'}
                """
            ).strip()
            pieces.append(section)
        body = "\n\n".join(pieces)
        return dedent(
            f"""
            {header}

            Combine the chunk analyses below into a single cohesive summary for the
            full article. Avoid repetition, consolidate bullet points, and merge tags
            and entities. Output the final result in the expected schema.

            {body}
            """
        ).strip()

    def _format_header(self, info: SummaryInputs, position: str) -> str:
        title = info.title or "Untitled"
        published = f"Published: {info.published}" if info.published else ""
        url = f"URL: {info.url}" if info.url else ""
        parts = [part for part in (f"Article title: {title}", position, url, published) if part]
        return " | ".join(parts)

    # ------------------------------------------------------------------
    # Core utilities
    # ------------------------------------------------------------------
    def _segment_article(self, text: str) -> List[str]:
        if not self._chunker:
            return [text]
        try:
            chunks = self._chunker(text)
        except Exception:
            print("TokenChunker failed; falling back to raw text")
            traceback.print_exc()
            return [text]
        out: List[str] = []
        for chunk in chunks:
            chunk_text = getattr(chunk, "text", None)
            if chunk_text and chunk_text.strip():
                out.append(chunk_text.strip())
        return out

    def _invoke_agent(self, prompt: str) -> Optional[SummaryLLMOutput]:
        if not self._agent:
            return None
        try:
            result = self._agent.run_sync(prompt)
            return result.output
        except Exception:
            print("Summarization agent call failed")
            traceback.print_exc()
            return None

    def _persist_outputs(
        self,
        *,
        archived_url_id: int,
        final_output: SummaryLLMOutput,
        chunk_outputs: Sequence[SummaryLLMOutput],
        source_text: str,
    ) -> bool:
        summary_text = final_output.summary.strip()
        if not summary_text:
            summary_text = " ".join(
                output.summary.strip() for output in chunk_outputs if output.summary.strip()
            )
        summary_text = summary_text.strip()
        if not summary_text:
            print(f"DEBUG: No summary generated for archived_url_id={archived_url_id}; aborting")
            return False

        bullet_points = [pt.strip() for pt in final_output.bullet_points if pt.strip()]
        bullet_points = bullet_points[: self.settings.summary_max_bullets]

        whitelist_tags = self._extract_whitelist_tags(source_text)
        llm_tags = self._normalise_llm_tags(final_output.recommended_tags)
        tags_payload = self._merge_tags(whitelist_tags, llm_tags)

        entities_payload = self._validate_entities(
            source_text,
            final_output.entities,
        )

        upsert_article_summary(
            self.settings.resolved_db_path,
            archived_url_id=archived_url_id,
            summary_type="default",
            summary_text=summary_text,
            bullet_points=bullet_points or None,
            model_name=self.settings.summarization_model,
        )
        replace_article_tags(
            self.settings.resolved_db_path,
            archived_url_id=archived_url_id,
            tags=tags_payload,
        )
        replace_article_entities(
            self.settings.resolved_db_path,
            archived_url_id=archived_url_id,
            entities=entities_payload,
        )
        print(
            "Completed summarization run | "
            f"archived_url_id={archived_url_id} "
            f"tags={len(tags_payload)} "
            f"entities={len(entities_payload)} "
            f"bullet_points={len(bullet_points)}"

        )
        return True

    def _extract_whitelist_tags(self, text: str) -> List[Dict[str, object]]:
        if not text:
            return []
        matches: List[Dict[str, object]] = []
        for tag, pattern in self._whitelist_entries:
            if pattern.search(text):
                matches.append(
                    {
                        "tag": tag,
                        "source": "whitelist",
                        "confidence": 1.0,
                        "reason": "Matched whitelist term in article",
                    }
                )
        return matches

    def _normalise_llm_tags(
        self, suggestions: Sequence[TagSuggestion]
    ) -> List[Dict[str, object]]:
        out: List[Dict[str, object]] = []
        for suggestion in suggestions:
            tag = suggestion.tag.strip()
            if not tag:
                continue
            out.append(
                {
                    "tag": tag,
                    "source": "llm",
                    "confidence": suggestion.confidence,
                    "reason": suggestion.reason,
                }
            )
        return out

    def _merge_tags(
        self,
        whitelist_tags: Sequence[Dict[str, object]],
        llm_tags: Sequence[Dict[str, object]],
    ) -> List[Dict[str, object]]:
        seen: set[Tuple[str, str]] = set()
        merged: List[Dict[str, object]] = []
        for candidate in list(whitelist_tags) + list(llm_tags):
            tag = str(candidate.get("tag", "")).strip()
            source = str(candidate.get("source", "")).strip() or "llm"
            if not tag:
                continue
            key = (tag.lower(), source.lower())
            if key in seen:
                continue
            seen.add(key)
            merged.append({**candidate, "tag": tag, "source": source})
        return merged

    def _validate_entities(
        self,
        source_text: str,
        suggestions: Sequence[EntitySuggestion],
    ) -> List[Dict[str, object]]:
        haystack = source_text.lower()
        results: List[Dict[str, object]] = []
        seen: set[Tuple[str, Optional[str]]] = set()
        for suggestion in suggestions:
            entity = suggestion.entity.strip()
            if not entity:
                continue
            entity_key = entity.lower()
            entity_type = suggestion.entity_type.strip() if suggestion.entity_type else None

            alias = suggestion.alias.strip() if suggestion.alias else None
            if not self._entity_in_text(entity_key, haystack):
                if not alias or not self._entity_in_text(alias.lower(), haystack):
                    continue

            key = (entity_key, entity_type.lower() if entity_type else None)
            if key in seen:
                continue
            seen.add(key)
            results.append(
                {
                    "entity": entity,
                    "entity_type": entity_type,
                    "alias": alias,
                    "reason": suggestion.reason,
                    "confidence": suggestion.confidence,
                    "validated": True,
                }
            )
        return results

    def _entity_in_text(self, needle: str, haystack: str) -> bool:
        if not needle:
            return False
        pattern = re.compile(rf"(?<!\w){re.escape(needle)}(?!\w)")
        return bool(pattern.search(haystack))

def trigger_summarization_if_ready(
    summarizer: "SummaryService" | None,
    *,
    settings: AppSettings,
    rowid: Optional[int] = None,
    archived_url_id: Optional[int] = None,
    reason: str | None = None,
) -> bool:
    """Run summarization if metadata exists and the service is ready."""

    print(f"trigger_summarization_if_ready called | rowid={rowid} archived_url_id={archived_url_id} reason={reason}")
    print(f"summarizer: {summarizer}, enabled: {summarizer.is_enabled if summarizer else 'n/a'}")
    if summarizer is None or not summarizer.is_enabled:
        return False

    reason = reason or "unspecified"

    try:
        target_id = archived_url_id
        if target_id is None and rowid is not None:
            artifact = get_save_by_rowid(settings.resolved_db_path, rowid)
            if artifact is None:
                print(
                    f"Skipping summarization: artifact missing | rowid={rowid} reason={reason}"

                )
                return False
            target_id = artifact.archived_url_id

        if target_id is None:
            print(
                f"Skipping summarization: archived_url unresolved | rowid={rowid} reason={reason}"

            )
            return False

        metadata = get_metadata_for_archived_url(
            settings.resolved_db_path, target_id
        )
        if metadata is None or not getattr(metadata, "text", None):
            print(
                f"Skipping summarization: metadata unavailable | archived_url_id={target_id} rowid={rowid} reason={reason}"

            )
            return False

        print(
            f"Triggering summarization | archived_url_id={target_id} rowid={rowid} reason={reason}"

        )
        summarizer.generate_for_archived_url(target_id)
        return True
    except Exception:
        print(
            f"Failed to execute summarization | archived_url_id={archived_url_id} rowid={rowid} reason={reason}"

        )
        traceback.print_exc()
        return False

