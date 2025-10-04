import glob
import re
from pathlib import Path


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
