"""
Readability Archiver.

Extracts article content using Readability and saves as JSON.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

from shared.models import ArchiveResult

from app.archivers.base import BaseArchiver

logger = logging.getLogger(__name__)


class ReadabilityArchiver(BaseArchiver):
    """Extract article content using Readability."""

    name = "readability"
    output_extension = "json"

    def archive(self, *, url: str, item_id: str) -> ArchiveResult:
        """Extract article content using Readability."""
        out_dir, out_path = self.get_output_path(item_id)

        logger.info(
            f"Extracting {item_id} {url}",
            extra={"item_id": item_id, "archiver": "readability"},
        )

        try:
            # Use readability-lxml or similar Python library
            content = self._extract_content(url)

            if content:
                # Save as JSON
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(content, f, ensure_ascii=False, indent=2)

                return ArchiveResult(
                    success=True,
                    exit_code=0,
                    saved_path=str(out_path),
                    metadata=content,
                )
            else:
                return ArchiveResult(success=False, exit_code=1, saved_path=None)

        except Exception as e:
            logger.error(f"Readability extraction failed: {e}", exc_info=True)
            return ArchiveResult(success=False, exit_code=1, saved_path=None)

    def _extract_content(self, url: str) -> Optional[dict]:
        """Extract article content from URL."""
        import httpx

        try:
            # Fetch page content
            with httpx.Client(follow_redirects=True, timeout=30) as client:
                response = client.get(url)
                response.raise_for_status()
                html = response.text

            # Try to use readability-lxml if available
            try:
                from readability import Document

                doc = Document(html)

                return {
                    "title": doc.title(),
                    "content": doc.summary(),
                    "text": self._html_to_text(doc.summary()),
                    "url": url,
                }
            except ImportError:
                # Fall back to basic extraction
                return self._basic_extract(html, url)

        except Exception as e:
            logger.error(f"Failed to fetch URL: {e}")
            return None

    def _basic_extract(self, html: str, url: str) -> dict:
        """Basic HTML extraction without readability."""
        from html.parser import HTMLParser

        class TitleExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self.in_title = False
                self.title = ""

            def handle_starttag(self, tag, attrs):
                if tag == "title":
                    self.in_title = True

            def handle_endtag(self, tag):
                if tag == "title":
                    self.in_title = False

            def handle_data(self, data):
                if self.in_title:
                    self.title += data

        extractor = TitleExtractor()
        extractor.feed(html)

        return {
            "title": extractor.title.strip(),
            "content": html,
            "text": self._html_to_text(html),
            "url": url,
        }

    def _html_to_text(self, html: str) -> str:
        """Convert HTML to plain text."""
        import re

        # Remove script and style elements
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)

        # Remove HTML tags
        text = re.sub(r"<[^>]+>", " ", text)

        # Clean up whitespace
        text = re.sub(r"\s+", " ", text)

        return text.strip()
