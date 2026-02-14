"""Article chunking for summary generation."""
from __future__ import annotations

import logging
from typing import List, Optional

from chonkie import TokenChunker

logger = logging.getLogger(__name__)


class ArticleChunker:
    """Chunks article text for processing by LLM.

    Wraps TokenChunker with logging and error handling.
    """

    def __init__(self, chunk_size: int = 1200):
        """Initialize chunker.

        Args:
            chunk_size: Target token count per chunk
        """
        self.chunk_size = chunk_size
        self._chunker: Optional[TokenChunker] = None  # type: ignore[type-arg]
        self._init_chunker()

    def _init_chunker(self) -> None:
        """Initialize underlying TokenChunker."""
        try:
            self._chunker = TokenChunker(chunk_size=self.chunk_size)  # type: ignore[call-arg]
        except Exception:
            logger.error(
                "Failed to initialize TokenChunker",
                exc_info=True,
            )
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
            List of text chunks (may be single item if chunking disabled)
        """
        if not self._chunker:
            logger.warning("Chunker not available; returning full text")
            return [text]

        try:
            chunks = self._chunker(text)
        except Exception:
            logger.warning(
                "TokenChunker failed; falling back to raw text", exc_info=True
            )
            return [text]

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
