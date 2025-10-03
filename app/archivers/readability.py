from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional
import subprocess

from archivers.base import BaseArchiver
from core.config import AppSettings
from core.utils import sanitize_filename
from models import ArchiveResult


class ReadabilityArchiver(BaseArchiver):
    name = "readability"

    def __init__(self, ht_runner, settings: AppSettings):
        super().__init__(settings)
        # ht_runner no longer required; kept for constructor compatibility
        self.ht_runner = ht_runner

    def _get_source_html(self, url: str) -> Optional[str]:
        """Return page HTML either via headless Chromium (--dump-dom) or HTTP GET.

        This avoids any need for a long-lived shell/`ht` session and does not
        write an intermediate DOM file to disk.
        """
        # Try Chromium first if enabled
        try:
            if getattr(self.settings, "use_chromium", True):
                args = [
                    self.settings.chromium_bin,
                    "--headless=new",
                    "--dump-dom",
                    "--run-all-compositor-stages-before-draw",
                    "--virtual-time-budget=9000",
                    "--hide-scrollbars",
                    "--no-sandbox",
                    "--disable-gpu",
                    "--disable-software-rasterizer",
                    "--disable-dev-shm-usage",
                    "--disable-setuid-sandbox",
                    "--disable-features=NetworkService,NetworkServiceInProcess",
                    url,
                ]
                proc = subprocess.run(
                    args,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if proc.returncode == 0 and proc.stdout.strip():
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
        safe_item = sanitize_filename(item_id)
        out_dir = Path(self.settings.data_dir) / safe_item / self.name
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "output.html"

        print(f"ReadabilityArchiver: archiving {url} as {item_id}")

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

        success = out_path.exists() and out_path.stat().st_size > 0
        return ArchiveResult(
            success=success,
            exit_code=0 if success else 1,
            saved_path=str(out_path) if success else None,
            metadata=meta if success else None,
        )
