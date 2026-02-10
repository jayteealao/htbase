"""Response parsing for summary generation."""
from __future__ import annotations

import logging
import re
from typing import Optional

from pydantic import ValidationError

from .providers import SummaryLLMOutput

logger = logging.getLogger(__name__)


class ResponseParser:
    """Parses LLM responses into structured summary outputs.

    Handles JSON extraction, validation, and fallback heuristics for
    malformed responses.
    """

    def parse(self, raw: str, *, label: str = "Response") -> Optional[SummaryLLMOutput]:
        """Parse raw LLM response into structured output.

        Args:
            raw: Raw text from LLM
            label: Description for logging (e.g., "Chunk 1", "Reduced")

        Returns:
            Parsed output, or None if parsing failed completely
        """
        try:
            logger.debug("Model output received", extra={"label": label, "output": raw})
            return SummaryLLMOutput.model_validate_json(raw)
        except ValidationError:
            logger.warning(
                "Model output failed schema validation; attempting extraction",
                extra={"label": label},
            )
            parsed = self._extract_summary_from_text(raw)
            if parsed is not None:
                return parsed
            text = (raw or "").strip()
            if not text:
                return None
            lede_guess = self._first_sentence(text)
            return SummaryLLMOutput(lede=lede_guess, summary=text)

    def _extract_summary_from_text(self, text: str) -> Optional[SummaryLLMOutput]:
        """Extract JSON object from messy output.

        Heuristics:
        - If the whole text is JSON, parse it directly
        - Prefer scanning after closing tags to avoid braces in input
        - Scan for first balanced JSON object
        - Strip code fences like ```json ... ```

        Args:
            text: Raw text that may contain JSON

        Returns:
            Extracted summary, or None if no valid JSON found
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
                                    return SummaryLLMOutput.model_validate_json(
                                        candidate
                                    )
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

    def _first_sentence(self, text: str) -> str:
        """Extract first sentence, capped at ~30 words for lede fallback.

        Args:
            text: Input text

        Returns:
            First sentence (up to 30 words)
        """
        s = (text or "").strip()
        if not s:
            return s
        # Split on common sentence enders
        parts = re.split(r"(?<=[\.!?])\s+", s)
        first = parts[0] if parts else s
        words = first.split()
        if len(words) > 30:
            first = " ".join(words[:30])
        return first.strip()
