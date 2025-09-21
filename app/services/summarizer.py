from __future__ import annotations

import re
import traceback
from dataclasses import dataclass
from textwrap import dedent
from typing import List, Optional, Sequence, Tuple

from pydantic import BaseModel, Field, ValidationError

try:
    from chonkie import TokenChunker
except Exception as exc:
    print(f'Failed to import chonkie: {exc}')
    traceback.print_exc()
    TokenChunker = None  # type: ignore[assignment]

try:
    from huggingface_hub import InferenceClient
except Exception as exc:
    print(f'Failed to import huggingface_hub InferenceClient: {exc}')
    traceback.print_exc()
    InferenceClient = None  # type: ignore[assignment]

try:
    import outlines
except Exception as exc:
    print(f'Failed to import outlines: {exc}')
    traceback.print_exc()
    outlines = None  # type: ignore[assignment]

from core.config import AppSettings
from db.repository import (
    get_archived_url_by_id,
    get_metadata_for_archived_url,
    get_save_by_rowid,
    replace_article_entities,
    replace_article_tags,
    upsert_article_summary,
)

class SummaryLLMOutput(BaseModel):
    lede: str = Field(..., min_length=1)
    summary: str = Field(..., min_length=1)

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
        if not (settings.openrouter_api_key or settings.summarization_api_base):
            missing.append("No summarization provider configured (set OPENROUTER_API_KEY or SUMMARIZATION_API_BASE)")
        if TokenChunker is None:
            missing.append("chonkie not installed")
        if InferenceClient is None or outlines is None:
            missing.append("huggingface_hub or outlines unavailable")

        self._enabled = not missing
        self._chunker: Optional[TokenChunker] = None  # type: ignore[type-arg]
        self._hf_client: Optional[InferenceClient] = None  # type: ignore[type-arg]
        self._outlines_model = None
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
            # Build TokenChunker
            if self._chunker is None:
                pass  # already built above

            # Configure TGI URL from settings; strip trailing '/v1' if provided
            base = (self.settings.summarization_api_base or '').strip()
            if base.endswith('/v1'):
                base = base[:-3]
            tgi_url = base or 'http://text-generation'
            token = None if not self.settings.summarization_api_key or self.settings.summarization_api_key == '-' else self.settings.summarization_api_key
            self._hf_client = InferenceClient(tgi_url, token=token)

            # Outlines model backed by TGI
            self._outlines_model = outlines.from_tgi(self._hf_client)

            self._instructions = dedent(
                """
                You are a senior editorial assistant with many years of experience crafting beautiful ledes and concise summaries for busy readers. Adopt an authoritative, polished editorial voice: selective, economical, and graceful. Prioritize the single most important takeaway and render it with clarity and craft.

                Hard rules:
                - Always respond in valid JSON only. Do not include any text outside the JSON.
                - Output must contain exactly two fields: "lede" and "summary".
                - "lede": one sentence, ≤30 words, capturing the article’s core takeaway. Must NOT start with "The" or "the".
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
        except Exception:
            print("Failed to initialise TGI/Outlines; disabling summarization")
            traceback.print_exc()
            self._enabled = False

    @property
    def is_enabled(self) -> bool:
        return bool(self._enabled and self._outlines_model and self._hf_client and self._chunker)

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
            result = self._invoke_model(prompt)
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
                result = self._invoke_model(prompt)
                if result is None:
                    print(
                        f"WARNING: Summarization aborted: LLM chunk call failed | archived_url_id={archived_url_id} chunk_index={idx}"

                    )
                    return False
                chunk_outputs.append(result)

            reduce_prompt = self._build_reduce_prompt(chunk_outputs, summary_inputs)
            final_output = self._invoke_model(reduce_prompt)
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
        print(f"Single prompt header: {header}")
        return dedent(
            f"""
            {header}

            Using only the information below, generate the required JSON with fields "lede" and "summary" following all rules and quality checks.

            <article>
            {chunk}
            </article>
            """
        ).strip()

    def _build_chunk_prompt(
        self, chunk: str, info: SummaryInputs, index: int, total: int
    ) -> str:
        header = self._format_header(info, position=f"chunk {index} of {total}")
        print(f"Chunk prompt header: {header}")
        return dedent(
            f"""
            {header}

            Analyse the following article chunk and return JSON with fields "lede" and "summary" based only on this chunk, following all rules and quality checks.

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
        print(f"Reduce prompt header: {header}")
        for idx, output in enumerate(chunk_outputs, start=1):
            section = dedent(
                f"""
                Chunk {idx} lede: {output.lede}
                Chunk {idx} summary: {output.summary}
                """
            ).strip()
            pieces.append(section)
        body = "\n\n".join(pieces)
        return dedent(
            f"""
            {header}

            Combine the chunk ledes and summaries into a single cohesive JSON output for the full article with fields "lede" and "summary". Avoid repetition and ensure the result follows all rules and quality checks.

            {body}
            """
        ).strip()

    def _format_header(self, info: SummaryInputs, position: str) -> str:
        title = info.title or "Untitled"
        published = f"Published: {info.published}" if info.published else ""
        url = f"URL: {info.url}" if info.url else ""
        parts = [part for part in (f"Article title: {title}", position, url, published) if part]
        print(f"Formatted header: {' | '.join(parts)}")
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
        print(f"Segmented article into {len(out)} chunks")
        return out

    def _invoke_model(self, prompt: str) -> Optional[SummaryLLMOutput]:
        if not self._outlines_model:
            return None
        try:
            instructions = getattr(self, "_instructions", "") or ""
            full_prompt = f"{instructions}\n\n{prompt}" if instructions else prompt
            try:
                raw = self._outlines_model(
                    full_prompt,
                    output_type=SummaryLLMOutput,
                    max_new_tokens=400,
                    temperature=0.2,
                    top_p=0.95,
                    return_full_text=False,
                )
            except TypeError:
                # Some Outlines/TGI versions may not accept return_full_text; retry without it
                raw = self._outlines_model(
                    full_prompt,
                    output_type=SummaryLLMOutput,
                    max_new_tokens=400,
                    temperature=0.2,
                    top_p=0.95,
                )
            try:
                print(f"Raw model output: {raw}")
                return SummaryLLMOutput.model_validate_json(raw)
            except ValidationError:
                print("Model output failed schema validation; attempting extraction")
                text = str(raw)
                parsed = self._extract_summary_from_text(text)
                if parsed is not None:
                    return parsed
                # Final fallback: synthesize lede from first sentence, use text as summary
                text = (text or "").strip()
                if not text:
                    return None
                lede_guess = self._first_sentence(text)
                return SummaryLLMOutput(lede=lede_guess, summary=text)
        except Exception:
            print("Summarization model call failed")
            traceback.print_exc()
            return None

    def _extract_summary_from_text(self, text: str) -> Optional[SummaryLLMOutput]:
        """Extract a JSON object containing a 'summary' field from messy output.

        Heuristics:
        - If the whole text is JSON for SummaryLLMOutput, parse it directly.
        - Prefer scanning after known closing tags (</article_chunk>, </article>) to
          avoid braces inside the input body.
        - Scan for the first balanced JSON object and validate against Pydantic.
        - Strip code fences like ```json ... ``` if present.
        """
        if not text:
            return None

        # Quick path: try full text as JSON
        try:
            return SummaryLLMOutput.model_validate_json(text.strip())
        except Exception:
            pass

        # Remove common code fences around JSON
        fenced = text
        if "```" in fenced:
            parts = fenced.split("```")
            for i in range(1, len(parts), 2):  # odd indices are inside fences
                candidate_block = parts[i]
                if "{" in candidate_block and "}" in candidate_block:
                    block = candidate_block
                    if "\n" in block:
                        lang, rest = block.split("\n", 1)
                        block = rest if "{" in rest else candidate_block
                    try:
                        return SummaryLLMOutput.model_validate_json(block.strip())
                    except Exception:
                        continue

        # Choose a safer starting point after our closing tags
        start = 0
        for tag in ("</article_chunk>", "</article>"):
            idx = text.rfind(tag)
            if idx != -1:
                start = max(start, idx + len(tag))

        # Scan for balanced JSON objects starting from 'start'
        src = text[start:]
        n = len(src)
        i = 0
        while i < n:
            if src[i] == "{":
                depth = 0
                in_str = False
                esc = False
                j = i
                while j < n:
                    ch = src[j]
                    if in_str:
                        if esc:
                            esc = False
                        elif ch == "\\":
                            esc = True
                        elif ch == '"':
                            in_str = False
                    else:
                        if ch == '"':
                            in_str = True
                        elif ch == "{":
                            depth += 1
                        elif ch == "}":
                            depth -= 1
                            if depth == 0:
                                candidate = src[i : j + 1]
                                try:
                                    return SummaryLLMOutput.model_validate_json(candidate)
                                except Exception:
                                    break
                    j += 1
                i = j + 1
                continue
            i += 1

        # As a last heuristic, split on an exact marker if present
        marker = "</article_chunk>{"
        m_idx = text.find(marker)
        if m_idx != -1:
            tail = "{" + text[m_idx + len(marker) :]
            rbrace = tail.rfind("}")
            if rbrace != -1:
                tail = tail[: rbrace + 1]
            try:
                return SummaryLLMOutput.model_validate_json(tail.strip())
            except Exception:
                pass

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

        # Store the lede in the bullet_points column as a single-item list
        lede_text = (final_output.lede or "").strip()
        bullets = [lede_text] if lede_text else None

        upsert_article_summary(
            self.settings.resolved_db_path,
            archived_url_id=archived_url_id,
            summary_type="default",
            summary_text=summary_text,
            bullet_points=bullets,
            model_name=self.settings.summarization_model,
        )
        print(
            "Completed summarization run | "
            f"archived_url_id={archived_url_id} "
            f"summary_length={len(summary_text)}"

        )
        return True

    def _first_sentence(self, text: str) -> str:
        """Naive first-sentence extractor, capped at ~30 words for a lede fallback."""
        s = (text or "").strip()
        if not s:
            return s
        # Split on common sentence enders.
        import re as _re
        parts = _re.split(r"(?<=[\.!?])\s+", s)
        first = parts[0] if parts else s
        words = first.split()
        if len(words) > 30:
            first = " ".join(words[:30])
        return first.strip()


