from __future__ import annotations

import asyncio
from copy import deepcopy
import re
import traceback
from dataclasses import dataclass
from textwrap import dedent
from typing import Any, Dict, List, Optional, Sequence, Tuple

from chonkie import TokenChunker
from huggingface_hub import AsyncInferenceClient
from huggingface_hub.errors import GenerationError
from pydantic import BaseModel, Field, ValidationError

from core.config import AppSettings
from db.repository import (
    get_archived_url_by_id,
    get_metadata_for_archived_url,
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
        self._enabled = False
        self._chunker: Optional[TokenChunker] = None  # type: ignore[type-arg]
        self._hf_base_url: Optional[str] = None
        self._hf_token: Optional[str] = None
        self._hf_grammar: Optional[Dict[str, Any]] = None
        self._instructions: str = ""
        self._whitelist_entries: List[Tuple[str, re.Pattern[str]]] = (
            self._build_whitelist(settings.summary_tag_whitelist)
        )

        if not self.settings.enable_summarization:
            print("SummaryService disabled: feature flag disabled")
            return

        if not self._init_chunker():
            return

        if not self._configure_hf_clients():
            return

        self._instructions = self._build_instructions()
        self._enabled = True

    # ------------------------------------------------------------------
    # Setup helpers
    # ------------------------------------------------------------------
    def _build_whitelist(
        self, raw_tags: Sequence[str]
    ) -> List[Tuple[str, re.Pattern[str]]]:
        entries: List[Tuple[str, re.Pattern[str]]] = []
        for raw_tag in raw_tags:
            tag = raw_tag.strip()
            if not tag:
                continue
            pattern = re.compile(rf"(?<!\w){re.escape(tag)}(?!\w)", re.IGNORECASE)
            entries.append((tag, pattern))
        return entries

    def _init_chunker(self) -> bool:
        try:
            self._chunker = TokenChunker(  # type: ignore[call-arg]
                chunk_size=self.settings.summary_chunk_size
            )
        except Exception:
            print("Failed to initialise TokenChunker; disabling summarization")
            traceback.print_exc()
            return False
        return True

    def _configure_hf_clients(self) -> bool:
        try:
            base = (self.settings.summarization_api_base or "").strip()
            if base.endswith("/v1"):
                base = base[:-3]
            tgi_url = base or "http://text-generation"
            token = self.settings.summarization_api_key
            if not token or token == "-":
                token = None
            self._hf_base_url = tgi_url
            self._hf_token = token

            self._hf_grammar = self._build_summary_json_grammar()
            return True
        except Exception:
            print("Failed to initialise Hugging Face clients; disabling summarization")
            traceback.print_exc()
            return False

    def _build_instructions(self) -> str:
        return dedent(
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

    @property
    def is_enabled(self) -> bool:
        # Enabled if config + chunker are ready and we have at least one client path
        has_async = bool(self._hf_base_url)
        return bool(self._enabled and self._chunker and has_async)

    def generate_for_archived_url(self, archived_url_id: int) -> bool:
        if not self.is_enabled:
            return False

        print(f"Starting summarization run | archived_url_id={archived_url_id}")
        prepared = self._prepare_summary_context(archived_url_id)
        if not prepared:
            return False

        summary_inputs, base_text = prepared
        chunk_texts = self._segment_article(base_text) or [base_text]

        print(
            "Prepared article text | "
            f"archived_url_id={archived_url_id} "
            f"chunk_count={len(chunk_texts)} "
            f"chunk_size={self.settings.summary_chunk_size}"

        )

        generated = self._generate_outputs(
            archived_url_id=archived_url_id,
            chunk_texts=chunk_texts,
            summary_inputs=summary_inputs,
        )
        if not generated:
            return False

        chunk_outputs, final_output = generated

        return self._persist_outputs(
            archived_url_id=archived_url_id,
            final_output=final_output,
            chunk_outputs=chunk_outputs,
            source_text=base_text,
        )

    def _prepare_summary_context(
        self, archived_url_id: int
    ) -> Optional[Tuple[SummaryInputs, str]]:
        metadata = get_metadata_for_archived_url(
            self.settings.resolved_db_path, archived_url_id
        )
        if metadata is None or not (metadata.text and metadata.text.strip()):
            print(
                f"Skipping summarization: no metadata text | archived_url_id={archived_url_id}"
            )
            return None

        article = get_archived_url_by_id(
            self.settings.resolved_db_path, archived_url_id
        )
        summary_inputs = SummaryInputs(
            title=getattr(metadata, "title", None)
            or getattr(article, "name", None),
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
        if len(chunk_texts) == 1:
            result = self._run_single_chunk(chunk_texts[0], summary_inputs)
            if result is None:
                print(
                    "WARNING: Summarization aborted: LLM call failed | "
                    f"archived_url_id={archived_url_id}"
                )
                return None
            return [result], result

        done = self._run_multi_chunk(chunk_texts, summary_inputs)
        if not done:
            print(
                "WARNING: Summarization aborted: async chunk or reduce step failed | "
                f"archived_url_id={archived_url_id}"
            )
            return None
        return done

    def _run_single_chunk(
        self, chunk: str, summary_inputs: SummaryInputs
    ) -> Optional[SummaryLLMOutput]:
        prompt = self._build_single_prompt(chunk, summary_inputs)
        return self._run_async_prompt(prompt)

    def _run_multi_chunk(
        self, chunk_texts: Sequence[str], summary_inputs: SummaryInputs
    ) -> Optional[Tuple[List[SummaryLLMOutput], SummaryLLMOutput]]:
        if not self._hf_base_url:
            return None

        prompts = [
            self._build_chunk_prompt(txt, summary_inputs, idx + 1, len(chunk_texts))
            for idx, txt in enumerate(chunk_texts)
        ]

        try:
            return asyncio.run(
                self._run_async_chunks(prompts, summary_inputs)
            )
        except Exception:
            return None

    def _run_async_prompt(self, prompt: str) -> Optional[SummaryLLMOutput]:
        if not self._hf_base_url:
            return None

        async def _single_async() -> Optional[SummaryLLMOutput]:
            async with AsyncInferenceClient(self._hf_base_url, token=self._hf_token) as aclient:
                return await self._invoke_model_async(aclient, prompt)

        try:
            return asyncio.run(_single_async())
        except Exception:
            return None

    async def _run_async_chunks(
        self,
        prompts: Sequence[str],
        summary_inputs: SummaryInputs,
    ) -> Optional[Tuple[List[SummaryLLMOutput], SummaryLLMOutput]]:
        if not self._hf_base_url:
            return None

        async with AsyncInferenceClient(self._hf_base_url, token=self._hf_token) as aclient:
            limit = self._resolve_concurrency_limit(len(prompts))
            sem = asyncio.Semaphore(limit)

            async def run_one(prompt: str) -> Optional[SummaryLLMOutput]:
                async with sem:
                    return await self._invoke_model_async(aclient, prompt)

            results = await asyncio.gather(*[run_one(p) for p in prompts])
            if any(r is None for r in results):
                return None

            chunk_outputs = [r for r in results if r is not None]
            reduce_prompt = self._build_reduce_prompt(chunk_outputs, summary_inputs)
            reduced = await self._invoke_model_async(aclient, reduce_prompt)
            if reduced is None:
                return None
            return chunk_outputs, reduced

    def _resolve_concurrency_limit(self, total: int) -> int:
        raw_limit = getattr(self.settings, "summary_max_concurrency", 0) or 0
        if not raw_limit:
            return total
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            return total
        return max(1, min(limit, total))

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

    async def _invoke_model_async(
        self, aclient: AsyncInferenceClient, prompt: str
    ) -> Optional[SummaryLLMOutput]:
        try:
            full_prompt = self._apply_instructions(prompt)
            raw, last_err = await self._generate_async(aclient, full_prompt)
            if raw is None:
                if last_err:
                    print(f"Async generation failed after variants: {last_err}")
                return None
            return self._parse_llm_response(raw, label="Raw async")
        except Exception:
            print("Async summarization model call failed")
            traceback.print_exc()
            return None

    def _apply_instructions(self, prompt: str) -> str:
        instructions = self._instructions.strip()
        return f"{instructions}\n\n{prompt}" if instructions else prompt

    async def _generate_async(
        self, aclient: "AsyncInferenceClient", full_prompt: str
    ) -> Tuple[Any | None, Exception | None]:
        last_err: Exception | None = None
        for params in self._build_text_generation_variants():
            result, err = await self._try_single_variant_async(
                aclient, full_prompt, params
            )
            if result is not None:
                return result, None
            if err is not None:
                last_err = err
        return None, last_err

    async def _try_single_variant_async(
        self,
        aclient: "AsyncInferenceClient",
        full_prompt: str,
        params: Dict[str, Any],
    ) -> Tuple[Any | None, Exception | None]:
        current = dict(params)
        removed_return_full = False
        removed_grammar = False
        last_err: Exception | None = None

        while True:
            try:
                return await aclient.text_generation(full_prompt, **current), None
            except TypeError as exc:
                last_err = exc
                if not removed_return_full and "return_full_text" in current:
                    current = dict(current)
                    current.pop("return_full_text", None)
                    removed_return_full = True
                    continue
                if (
                    not removed_grammar
                    and "grammar" in current
                    and "grammar" in str(exc)
                ):
                    current = dict(current)
                    current.pop("grammar", None)
                    removed_grammar = True
                    continue
                await asyncio.sleep(0.25)
                return None, last_err
            except GenerationError as exc:
                last_err = exc
                await asyncio.sleep(0.25)
                return None, last_err
            except Exception as exc:
                last_err = exc
                await asyncio.sleep(0.25)
                return None, last_err

    def _parse_llm_response(
        self, raw: Any, *, label: str
    ) -> Optional[SummaryLLMOutput]:
        text = self._coerce_generated_text(raw)
        try:
            print(f"{label} model output: {text}")
            return SummaryLLMOutput.model_validate_json(text)
        except ValidationError:
            print("Model output failed schema validation; attempting extraction")
            parsed = self._extract_summary_from_text(text)
            if parsed is not None:
                return parsed
            text = (text or "").strip()
            if not text:
                return None
            lede_guess = self._first_sentence(text)
            return SummaryLLMOutput(lede=lede_guess, summary=text)

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

    def _build_summary_json_grammar(self) -> Optional[Dict[str, Any]]:
        try:
            schema = deepcopy(SummaryLLMOutput.model_json_schema())
        except Exception:
            return None

        # Ensure schema is explicit about required fields and shape
        required = list(dict.fromkeys([*(schema.get("required") or []), "lede", "summary"]))
        schema["required"] = required
        schema["additionalProperties"] = False

        properties = schema.setdefault("properties", {})
        if isinstance(properties, dict):
            for field in ("lede", "summary"):
                field_schema = properties.get(field) or {}
                if not isinstance(field_schema, dict):
                    field_schema = {}
                field_schema.setdefault("type", "string")
                field_schema.setdefault("minLength", 1)
                properties[field] = field_schema

        return {"type": "json_schema", "value": schema}

    def _build_text_generation_variants(self) -> List[Dict[str, Any]]:
        base_variants: List[Dict[str, Any]] = [
            {"temperature": 0.2, "top_p": 0.95, "do_sample": True, "max_new_tokens": 400, "return_full_text": False},
            {"temperature": 0.0, "top_p": 1.0, "do_sample": False, "max_new_tokens": 300, "return_full_text": False},
            {"temperature": 0.2, "top_p": 0.90, "do_sample": True, "max_new_tokens": 280, "return_full_text": False},
        ]

        grammar = getattr(self, "_hf_grammar", None)
        variants: List[Dict[str, Any]] = []
        for params in base_variants:
            variant = dict(params)
            if grammar:
                variant["grammar"] = grammar
            variants.append(variant)
        return variants

    def _coerce_generated_text(self, raw: Any) -> str:
        if raw is None:
            return ""
        if isinstance(raw, str):
            return raw
        text = getattr(raw, "generated_text", None)
        if isinstance(text, str):
            return text
        if isinstance(raw, dict):
            for key in ("generated_text", "text", "content"):
                value = raw.get(key)
                if isinstance(value, str):
                    return value
        return str(raw)

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


