import glob
import re
from pathlib import Path
from urllib.parse import urlparse


PAYWALL_BYPASS_SUFFIXES: tuple[str, ...] = (
    "medium.com",
    "proandroiddev.com",
)


def rewrite_paywalled_url(url: str) -> str:
    """Rewrite Medium-like URLs to their freedium mirror when applicable."""
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
        if host == suffix or host.endswith(f'.{suffix}'):
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
    path = parsed.path.lstrip('/')
    if not path:
        return None

    # The path should be the full original URL
    if path.startswith('http://') or path.startswith('https://'):
        return path

    return None


def sanitize_filename(name: str) -> str:
    """Return a safe filename by keeping [A-Za-z0-9._-] and trimming length.

    Also prevents hidden filenames by stripping leading dots and ensures
    a non-empty fallback value.
    """
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    # remove leading dots to prevent hidden files
    safe = safe.lstrip(".")
    # also trim leading separators produced by replacements
    safe = safe.lstrip("_-")
    if not safe:
        safe = "file"
    return safe[:200]


def cleanup_chromium_singleton_locks(user_data_dir: Path) -> None:
    """Remove stale Chromium Singleton lock files to prevent exit code 21.

    Exit code 21 occurs when Chromium believes the profile is locked by another
    process. Cleaning up Singleton* files before launching prevents this issue.
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


def get_directory_size(path: Path) -> int:
    """Calculate total size of a directory and all its contents recursively.

    Returns size in bytes. Returns 0 if path doesn't exist or on error.
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
