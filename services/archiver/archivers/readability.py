from __future__ import annotations

from datetime import datetime
import logging
from pathlib import Path
from typing import Optional
import subprocess

from .base import BaseArchiver
from core.chromium_utils import ChromiumArchiverMixin, ChromiumCommandBuilder
from core.config import AppSettings
from core.utils import sanitize_filename
from models import ArchiveResult
from storage.file_storage import FileStorageProvider
from storage.database_storage import DatabaseStorageProvider

logger = logging.getLogger(__name__)


class ReadabilityArchiver(BaseArchiver, ChromiumArchiverMixin):
    name = "readability"

    def __init__(
        self,
        command_runner,
        settings: AppSettings,
        file_storage_providers: Optional[list[FileStorageProvider]] = None,
        db_storage: Optional[DatabaseStorageProvider] = None
    ):
        super().__init__(settings, file_storage_providers, db_storage)
        # command_runner not used by readability; kept for constructor compatibility
        self.command_runner = command_runner
        self.chromium_builder = ChromiumCommandBuilder(settings)

    def _get_source_html(self, url: str) -> Optional[str]:
        """Return page HTML either via headless Chromium (--dump-dom) or HTTP GET.

        This avoids any need for a long-lived shell/`ht` session and does not
        write an intermediate DOM file to disk.
        """
        # Try Chromium first if enabled
        try:
            if getattr(self.settings, "use_chromium", True):
                # Setup Chromium (create user data dir and clean locks)
                self.setup_chromium()

                # Build Chromium command for DOM dumping
                args = self.chromium_builder.build_dump_dom_args(url)

                proc = subprocess.run(
                    args,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    # Clean up after Chromium completes
                    self.cleanup_chromium()
                    return proc.stdout
        except Exception:
            # Fall through to requests
            pass

        # HTTP fallback
        try:
            import requests  # type: ignore

            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            }
            r = requests.get(url, headers=headers, timeout=30)
            r.raise_for_status()
            return r.text
        except Exception:
            return None

    def archive(self, *, url: str, item_id: str) -> ArchiveResult:
        out_dir, out_path = self.get_output_path(item_id)

        logger.info(f"Archiving {url}", extra={"item_id": item_id, "archiver": "readability"})

        # Obtain page HTML (Chromium dump preferred; HTTP fallback)
        html = self._get_source_html(url)
        if not html:
            return ArchiveResult(success=False, exit_code=1, saved_path=None)

        try:
            from readability import Document  # type: ignore
        except Exception:
            return ArchiveResult(success=False, exit_code=127, saved_path=None)

        try:
            doc = Document(html)
            title = doc.short_title() or doc.title() or ""
            # summary() returns article HTML
            article_html = doc.summary(html_partial=False)

            # Extract metadata from DOM using lxml
            meta: dict = {}
            try:
                import lxml.html as LH  # provided by readability-lxml dependency

                tree = LH.fromstring(html)

                def mget(names: list[tuple[str, str]]):
                    for attr, key in names:
                        val = tree.xpath(f"//meta[@{attr}='{key}']/@content")
                        if val:
                            return val[0]
                    return None

                def lget(rels: list[str]):
                    for rel in rels:
                        val = tree.xpath(f"//link[translate(@rel,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='{rel}']/@href")
                        if val:
                            return val[0]
                    return None

                lang = (tree.xpath("string(//html/@lang)") or "").strip().lower() or None
                byline = mget([( "name", "author"), ("property", "article:author"), ("name", "byl")])
                site_name = mget([( "property", "og:site_name")])
                description = mget([("name", "description"), ("property", "og:description")])
                published = mget([("property", "article:published_time"), ("name", "pubdate"), ("name", "date")])
                canonical = lget(["canonical"]) or None
                top_image = mget([("property", "og:image")]) or lget(["image_src"]) or None
                favicon = lget(["icon"]) or lget(["shortcut icon"]) or None
                keywords_raw = mget([("name", "keywords")])
                keywords = [s.strip() for s in keywords_raw.split(",") if s.strip()] if keywords_raw else []

                # Derive text, word counts
                try:
                    article_tree = LH.fromstring(article_html)
                    text = article_tree.text_content().strip()
                except Exception:
                    text = ""
                word_count = len(text.split()) if text else 0
                reading_time_minutes = round(word_count / 200.0, 2) if word_count else 0.0

                meta = {
                    "source_url": url,
                    "title": title,
                    "byline": byline,
                    "site_name": site_name,
                    "description": description,
                    "published": published,
                    "language": lang,
                    "canonical_url": canonical,
                    "top_image": top_image,
                    "favicon": favicon,
                    "keywords": keywords,
                    "word_count": word_count,
                    "reading_time_minutes": reading_time_minutes,
                    "text": text,
                }
            except Exception:
                meta = {"source_url": url, "title": title}

            # Persist metadata JSON alongside the HTML for inspection/debugging
            try:
                import json
                meta_path = out_dir / "output.json"
                meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass

            # Wrap into a minimal HTML page to be viewable alone
            page = (
                "<!DOCTYPE html>\n"
                "<html><head><meta charset=\"utf-8\">"
                f"<title>{title}</title>"
                "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"></head>"
                f"<body>{article_html}</body></html>"
            )
            out_path.write_text(page, encoding="utf-8")
        except Exception:
            return ArchiveResult(success=False, exit_code=1, saved_path=None)

        # Use base class validation, passing exit_code=0 for successful parsing
        return self.create_result(
            path=out_path,
            exit_code=0 if out_path.exists() and out_path.stat().st_size > 0 else 1,
            metadata=meta,
        )
