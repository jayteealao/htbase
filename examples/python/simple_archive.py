"""
Simple archive example - Archive a single URL with HTBase.

Usage:
    python simple_archive.py

Requirements:
    pip install requests
"""

import requests
from typing import Dict, Any


def archive_url(
    url: str,
    item_id: str,
    archiver: str = "readability",
    base_url: str = "http://localhost:8000"
) -> Dict[str, Any]:
    """
    Archive a single URL using HTBase.

    Args:
        url: The URL to archive
        item_id: Unique identifier for this archive
        archiver: Archiver to use (readability, monolith, singlefile-cli, pdf, screenshot, all)
        base_url: HTBase API base URL

    Returns:
        Dictionary with archive result

    Raises:
        requests.exceptions.RequestException: If the request fails
    """
    endpoint = f"{base_url}/api/save/{archiver}"

    payload = {
        "url": url,
        "id": item_id
    }

    response = requests.post(
        endpoint,
        json=payload,
        timeout=300  # 5 minutes
    )

    # Raise exception for HTTP errors
    response.raise_for_status()

    return response.json()


def main():
    """Example usage."""
    # Configuration
    URL_TO_ARCHIVE = "https://example.com"
    ITEM_ID = "example-article-2026-01-09"
    ARCHIVER = "readability"

    print(f"Archiving: {URL_TO_ARCHIVE}")
    print(f"Item ID: {ITEM_ID}")
    print(f"Archiver: {ARCHIVER}")
    print("-" * 50)

    try:
        # Archive the URL
        result = archive_url(
            url=URL_TO_ARCHIVE,
            item_id=ITEM_ID,
            archiver=ARCHIVER
        )

        # Check result
        if result.get("ok") and result.get("exit_code") == 0:
            print("✅ Archive successful!")
            print(f"Saved to: {result['saved_path']}")
            print(f"Database row ID: {result['db_rowid']}")
        else:
            print("❌ Archive failed!")
            print(f"Exit code: {result.get('exit_code')}")
            print(f"Details: {result}")

    except requests.exceptions.Timeout:
        print("❌ Request timed out (archive took >5 minutes)")

    except requests.exceptions.HTTPError as e:
        print(f"❌ HTTP error: {e}")
        print(f"Response: {e.response.text}")

    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")


if __name__ == "__main__":
    main()
