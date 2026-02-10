"""Article chunking for summary generation."""
from __future__ import annotations

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


class ArticleChunker:
    """Chunks article text for processing by LLM.

    Uses TokenChunker for intelligent token-based chunking,
    with fallback to character-based chunking if unavailable.
    """

    def __init__(self, chunk_size: int = 1200, overlap: int = 100):
        """Initialize chunker.

        Args:
            chunk_size: Target token count per chunk
            overlap: Token overlap between chunks
        """
        self.chunk_size = chunk_size
        self.overlap = overlap
        self._chunker: Optional[object] = None
        self._init_chunker()

    def _init_chunker(self) -> None:
        """Initialize underlying TokenChunker if available."""
        try:
            from chonkie import TokenChunker
            self._chunker = TokenChunker(chunk_size=self.chunk_size)
        except ImportError:
            logger.warning("chonkie not available; using character-based chunking")
            self._chunker = None
        except Exception:
            logger.error("Failed to initialize TokenChunker", exc_info=True)
            self._chunker = None

    @property
    def is_enabled(self) -> bool:
        """Check if chunker is available."""
        return self._chunker is not None

    def chunk(self, text: str) -> List[str]:
        """Chunk article text into segments.

        Args:
            text: Article text to chunk

        Returns:
            List of text chunks (may be single item if text is short)
        """
        if not text or not text.strip():
            return []

        text = text.strip()

        # Use token chunker if available
        if self._chunker:
            return self._chunk_with_tokens(text)

        # Fallback to character-based chunking
        return self._chunk_by_chars(text)

    def _chunk_with_tokens(self, text: str) -> List[str]:
        """Chunk using TokenChunker."""
        try:
            chunks = self._chunker(text)
        except Exception:
            logger.warning("TokenChunker failed; falling back to char chunking", exc_info=True)
            return self._chunk_by_chars(text)

        out: List[str] = []
        for chunk in chunks:
            chunk_text = getattr(chunk, "text", None)
            if chunk_text and chunk_text.strip():
                out.append(chunk_text.strip())

        if not out:
            logger.warning("Chunking produced no output; returning full text")
            return [text]

        logger.debug("Segmented article", extra={"chunk_count": len(out)})
        return out

    def _chunk_by_chars(self, text: str, chars_per_chunk: int = 4000) -> List[str]:
        """Fallback character-based chunking.

        Args:
            text: Text to chunk
            chars_per_chunk: Approximate characters per chunk

        Returns:
            List of text chunks
        """
        if len(text) <= chars_per_chunk:
            return [text]

        chunks = []
        sentences = text.replace('\n', ' ').split('. ')

        current_chunk = []
        current_length = 0

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # Add period back if not ending with punctuation
            if not sentence.endswith(('.', '!', '?')):
                sentence += '.'

            sentence_length = len(sentence)

            if current_length + sentence_length > chars_per_chunk and current_chunk:
                chunks.append(' '.join(current_chunk))
                current_chunk = [sentence]
                current_length = sentence_length
            else:
                current_chunk.append(sentence)
                current_length += sentence_length

        if current_chunk:
            chunks.append(' '.join(current_chunk))

        return chunks if chunks else [text]

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text.

        Uses rough approximation of 4 characters per token.

        Args:
            text: Text to estimate

        Returns:
            Estimated token count
        """
        return len(text) // 4
