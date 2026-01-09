"""
Error handling example - Robust archive with retry and fallback logic.

Usage:
    python error_handling.py

Requirements:
    pip install requests
"""

import requests
import time
from typing import Dict, Any, Optional, List


def archive_with_retry(
    url: str,
    item_id: str,
    archiver: str = "readability",
    base_url: str = "http://localhost:8000",
    max_retries: int = 3,
    base_delay: int = 2
) -> Optional[Dict[str, Any]]:
    """
    Archive with exponential backoff retry.

    Args:
        url: URL to archive
        item_id: Unique identifier
        archiver: Archiver to use
        base_url: HTBase API URL
        max_retries: Maximum retry attempts
        base_delay: Base delay in seconds (exponential)

    Returns:
        Archive result or None if all retries failed
    """
    endpoint = f"{base_url}/api/save/{archiver}"
    payload = {"url": url, "id": item_id}

    for attempt in range(max_retries):
        try:
            response = requests.post(
                endpoint,
                json=payload,
                timeout=300
            )
            response.raise_for_status()
            result = response.json()

            # Check exit code
            exit_code = result.get("exit_code")

            if exit_code == 0:
                print(f"✅ Success on attempt {attempt + 1}")
                return result

            # Non-retryable errors
            if exit_code == 404:
                print(f"❌ URL not found (404)")
                return result

            # Retryable error
            if attempt < max_retries - 1:
                wait = base_delay ** attempt  # 2s, 4s, 8s
                print(f"⚠️  Attempt {attempt + 1} failed (exit_code={exit_code}), retrying in {wait}s...")
                time.sleep(wait)
                continue

        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                wait = base_delay ** attempt
                print(f"⚠️  Timeout on attempt {attempt + 1}, retrying in {wait}s...")
                time.sleep(wait)
                continue
            else:
                print(f"❌ Timeout after {max_retries} attempts")

        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code

            # Non-retryable HTTP errors
            if status_code in [400, 401, 403, 404]:
                print(f"❌ HTTP {status_code}: {e.response.text}")
                return None

            # Retryable HTTP errors (5xx)
            if attempt < max_retries - 1:
                wait = base_delay ** attempt
                print(f"⚠️  HTTP {status_code} on attempt {attempt + 1}, retrying in {wait}s...")
                time.sleep(wait)
                continue

        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                wait = base_delay ** attempt
                print(f"⚠️  Request error on attempt {attempt + 1}: {e}, retrying in {wait}s...")
                time.sleep(wait)
                continue
            else:
                print(f"❌ Request failed after {max_retries} attempts: {e}")

    return None


def archive_with_fallback(
    url: str,
    item_id: str,
    archivers: Optional[List[str]] = None,
    base_url: str = "http://localhost:8000"
) -> Optional[Dict[str, Any]]:
    """
    Try multiple archivers until one succeeds.

    Args:
        url: URL to archive
        item_id: Unique identifier
        archivers: List of archivers to try (in order)
        base_url: HTBase API URL

    Returns:
        Archive result or None if all archivers failed
    """
    if archivers is None:
        archivers = ["readability", "monolith", "singlefile-cli"]

    print(f"Trying archivers in order: {', '.join(archivers)}")

    for archiver in archivers:
        print(f"\n🔄 Attempting with {archiver}...")

        try:
            endpoint = f"{base_url}/api/save/{archiver}"
            response = requests.post(
                endpoint,
                json={"url": url, "id": item_id},
                timeout=300
            )
            response.raise_for_status()
            result = response.json()

            if result.get("ok") and result.get("exit_code") == 0:
                print(f"✅ Success with {archiver}")
                return result
            else:
                print(f"❌ Failed with {archiver} (exit_code={result.get('exit_code')})")

        except Exception as e:
            print(f"❌ {archiver} error: {e}")

    print("\n❌ All archivers failed")
    return None


def validate_archive(result: Dict[str, Any], min_size: int = 1000) -> bool:
    """
    Validate archive quality.

    Args:
        result: Archive result from HTBase
        min_size: Minimum acceptable file size in bytes

    Returns:
        True if archive meets quality standards
    """
    if not result.get("ok"):
        print("❌ Archive not OK")
        return False

    if result.get("exit_code") != 0:
        print(f"❌ Non-zero exit code: {result.get('exit_code')}")
        return False

    saved_path = result.get("saved_path")
    if not saved_path:
        print("❌ No saved_path in result")
        return False

    # Note: File size validation would require file system access
    # In production, you might retrieve and check the file size
    print("✅ Archive validation passed")
    return True


def main():
    """Example usage."""
    print("=" * 60)
    print("Example 1: Archive with Retry")
    print("=" * 60)

    result = archive_with_retry(
        url="https://example.com",
        item_id="retry-example",
        archiver="readability",
        max_retries=3
    )

    if result:
        validate_archive(result)

    print("\n" + "=" * 60)
    print("Example 2: Archive with Fallback")
    print("=" * 60)

    result = archive_with_fallback(
        url="https://example.com",
        item_id="fallback-example",
        archivers=["readability", "monolith", "singlefile-cli"]
    )

    if result:
        validate_archive(result)

    print("\n" + "=" * 60)
    print("Example 3: Combined Retry + Fallback")
    print("=" * 60)

    # Try each archiver with retry
    for archiver in ["readability", "monolith"]:
        print(f"\nTrying {archiver} with retry...")
        result = archive_with_retry(
            url="https://example.com",
            item_id=f"combined-{archiver}",
            archiver=archiver,
            max_retries=2
        )

        if result and validate_archive(result):
            print(f"✅ Successfully archived with {archiver}")
            break
    else:
        print("❌ All strategies exhausted")


if __name__ == "__main__":
    main()
