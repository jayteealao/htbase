"""
Shared utility functions for HTBase microservices.

Provides common helper functions used across services for URL processing,
file operations, and data validation.
"""

from __future__ import annotations

import glob
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


# Domains that should be rewritten to freedium for paywall bypass
PAYWALL_BYPASS_SUFFIXES: tuple[str, ...] = (
    "medium.com",
    "proandroiddev.com",
)


def rewrite_paywalled_url(url: str) -> str:
    """Rewrite Medium-like URLs to their freedium mirror when applicable.

    Args:
        url: Original URL

    Returns:
        Rewritten URL if paywall bypass applies, otherwise original URL
    """
    raw_url = (url or "").strip()
    if not raw_url:
        return raw_url

    try:
        parsed = urlparse(raw_url)
    except ValueError:
        return raw_url

    host = (parsed.hostname or "").lower()
    if not host:
        return raw_url

    if host == "freedium.cfd":
        return raw_url

    for suffix in PAYWALL_BYPASS_SUFFIXES:
        if host == suffix or host.endswith(f".{suffix}"):
            return f"https://freedium.cfd/{raw_url}"

    return raw_url


def extract_original_url(url: str) -> str | None:
    """Extract the original URL from a freedium.cfd rewritten URL.

    Returns the original URL if this is a freedium URL, otherwise returns None.

    Examples:
        "https://freedium.cfd/https://medium.com/article" -> "https://medium.com/article"
        "https://medium.com/article" -> None
    """
    raw_url = (url or "").strip()
    if not raw_url:
        return None

    try:
        parsed = urlparse(raw_url)
    except ValueError:
        return None

    host = (parsed.hostname or "").lower()
    if host != "freedium.cfd":
        return None

    # Extract the original URL from the path
    # Format: https://freedium.cfd/{original_url}
    path = parsed.path.lstrip("/")
    if not path:
        return None

    # The path should be the full original URL
    if path.startswith("http://") or path.startswith("https://"):
        return path

    return None


def sanitize_filename(name: str) -> str:
    """Return a safe filename by keeping [A-Za-z0-9._-] and trimming length.

    Also prevents hidden filenames by stripping leading dots and ensures
    a non-empty fallback value.

    NOTE: Preserves leading underscores and dashes to maintain itemId integrity
    for Trails app <-> Firestore <-> htbase relationship.

    Args:
        name: Original filename or identifier

    Returns:
        Sanitized filename safe for filesystem use
    """
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    # remove leading dots to prevent hidden files
    safe = safe.lstrip(".")
    # DO NOT strip leading underscores or dashes - they are valid in itemIds
    # and required for maintaining relationships with Trails app and Firestore
    if not safe:
        safe = "file"
    return safe[:200]


def cleanup_chromium_singleton_locks(user_data_dir: Path) -> None:
    """Remove stale Chromium Singleton lock files to prevent exit code 21.

    Exit code 21 occurs when Chromium believes the profile is locked by another
    process. Cleaning up Singleton* files before launching prevents this issue.

    Args:
        user_data_dir: Path to Chromium user data directory
    """
    if not user_data_dir.exists():
        return

    # Remove Singleton* files (SingletonLock, SingletonSocket, SingletonCookie, etc.)
    for lock_file in glob.glob(str(user_data_dir / "Singleton*")):
        try:
            Path(lock_file).unlink(missing_ok=True)
        except (OSError, PermissionError):
            # If we can't delete, proceed anyway - browser might handle it
            pass


def get_url_status(url: str, timeout: int = 10) -> int | None:
    """Return HTTP status code for the given URL or None on network/error.

    Uses a HEAD request first and falls back to GET if the server does not
    respond to HEAD. Returns the integer status code (e.g., 200, 404) or
    None if the request fails.

    Args:
        url: URL to check
        timeout: Request timeout in seconds

    Returns:
        HTTP status code or None on failure
    """
    try:
        import httpx

        with httpx.Client(follow_redirects=True, timeout=timeout) as client:
            try:
                r = client.head(url)
            except Exception:
                r = client.get(url)
            return int(r.status_code)
    except Exception:
        return None


@dataclass
class URLCheck:
    """Result of URL archivability check."""

    url: str
    is_reachable: bool
    status_code: int | None
    should_archive: bool

    @property
    def is_not_found(self) -> bool:
        """True if URL returned 404 status."""
        return self.status_code == 404

    @property
    def is_server_error(self) -> bool:
        """True if URL returned 5xx status."""
        return self.status_code is not None and 500 <= self.status_code < 600


def check_url_archivability(url: str, timeout: int = 10) -> URLCheck:
    """Check if a URL should be archived based on reachability.

    Returns a URLCheck object with status information. URLs that return 404
    are marked as should_archive=False, all other cases (including errors)
    are marked as should_archive=True to allow archiving attempts.

    Args:
        url: URL to check
        timeout: Request timeout in seconds (default: 10)

    Returns:
        URLCheck with reachability status and archiving recommendation
    """
    try:
        status = get_url_status(url, timeout=timeout)
        return URLCheck(
            url=url,
            is_reachable=status is not None,
            status_code=status,
            should_archive=status != 404,
        )
    except Exception:
        # On any error, still attempt archiving (better to try than skip)
        return URLCheck(
            url=url,
            is_reachable=False,
            status_code=None,
            should_archive=True,
        )


def get_directory_size(path: Path) -> int:
    """Calculate total size of a directory and all its contents recursively.

    Args:
        path: Directory or file path

    Returns:
        Size in bytes. Returns 0 if path doesn't exist or on error.
    """
    if not path.exists():
        return 0

    total = 0
    try:
        if path.is_file():
            return path.stat().st_size

        for item in path.rglob("*"):
            if item.is_file():
                try:
                    total += item.stat().st_size
                except (OSError, PermissionError):
                    # Skip files we can't access
                    pass
    except (OSError, PermissionError):
        pass

    return total


def format_bytes(size: int) -> str:
    """Format byte size to human-readable string.

    Args:
        size: Size in bytes

    Returns:
        Human-readable size string (e.g., "1.5 MB")
    """
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def is_valid_url(url: str) -> bool:
    """Check if a string is a valid URL.

    Args:
        url: String to validate

    Returns:
        True if valid URL
    """
    try:
        parsed = urlparse(url)
        return bool(parsed.scheme and parsed.netloc)
    except Exception:
        return False


def normalize_url(url: str) -> str:
    """Normalize a URL for comparison and storage.

    Removes trailing slashes and normalizes scheme to lowercase.

    Args:
        url: URL to normalize

    Returns:
        Normalized URL
    """
    url = url.strip()
    if not url:
        return url

    try:
        parsed = urlparse(url)
        # Normalize scheme to lowercase
        scheme = parsed.scheme.lower()
        # Remove default ports
        netloc = parsed.netloc
        if netloc.endswith(":80") and scheme == "http":
            netloc = netloc[:-3]
        elif netloc.endswith(":443") and scheme == "https":
            netloc = netloc[:-4]
        # Reconstruct URL
        path = parsed.path.rstrip("/") or "/"
        normalized = f"{scheme}://{netloc}{path}"
        if parsed.query:
            normalized += f"?{parsed.query}"
        if parsed.fragment:
            normalized += f"#{parsed.fragment}"
        return normalized
    except Exception:
        return url
