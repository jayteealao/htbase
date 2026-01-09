"""
RSS feed archiver - Archive all articles from an RSS feed.

Usage:
    python rss_archiver.py

Requirements:
    pip install requests feedparser
"""

import feedparser
import hashlib
import requests
import time
from typing import List, Dict, Any
from urllib.parse import urlparse


class RSSArchiver:
    """Archive articles from RSS feeds."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        """
        Initialize RSS archiver.

        Args:
            base_url: HTBase API base URL
        """
        self.base_url = base_url

    def generate_id(self, url: str) -> str:
        """
        Generate stable ID from URL.

        Args:
            url: Article URL

        Returns:
            MD5 hash of URL
        """
        return hashlib.md5(url.encode()).hexdigest()

    def parse_feed(self, feed_url: str) -> List[Dict[str, str]]:
        """
        Parse RSS feed and extract articles.

        Args:
            feed_url: RSS feed URL

        Returns:
            List of dicts with 'url' and 'id' keys
        """
        print(f"Parsing feed: {feed_url}")
        feed = feedparser.parse(feed_url)

        if feed.bozo:
            print(f"⚠️  Warning: Feed parsing had issues: {feed.bozo_exception}")

        items = []
        for entry in feed.entries:
            # Get article URL
            url = entry.get("link")
            if not url:
                continue

            # Generate stable ID
            item_id = self.generate_id(url)

            # Get title for logging
            title = entry.get("title", "Untitled")

            items.append({
                "url": url,
                "id": item_id,
                "title": title
            })

        print(f"Found {len(items)} articles")
        return items

    def batch_archive(
        self,
        items: List[Dict[str, str]],
        archiver: str = "readability"
    ) -> str:
        """
        Submit batch archive request.

        Args:
            items: List of items to archive
            archiver: Archiver to use

        Returns:
            Task ID
        """
        endpoint = f"{self.base_url}/api/batch/{archiver}"

        # Strip title from items (not needed in API request)
        api_items = [
            {"url": item["url"], "id": item["id"]}
            for item in items
        ]

        response = requests.post(
            endpoint,
            json={"items": api_items},
            timeout=30
        )
        response.raise_for_status()

        result = response.json()
        return result["task_id"]

    def wait_for_completion(
        self,
        task_id: str,
        poll_interval: int = 5,
        max_wait: int = 1800  # 30 minutes
    ) -> Dict[str, Any]:
        """
        Wait for batch task to complete.

        Args:
            task_id: Task ID to wait for
            poll_interval: Seconds between checks
            max_wait: Maximum seconds to wait

        Returns:
            Task status
        """
        endpoint = f"{self.base_url}/api/tasks/{task_id}"
        start = time.time()

        while time.time() - start < max_wait:
            response = requests.get(endpoint, timeout=10)
            response.raise_for_status()
            status = response.json()

            if status["status"] in ["success", "failed"]:
                return status

            elapsed = int(time.time() - start)
            print(f"⏳ Waiting... ({elapsed}s elapsed)")
            time.sleep(poll_interval)

        raise TimeoutError(f"Task {task_id} did not complete in {max_wait}s")

    def archive_feed(
        self,
        feed_url: str,
        archiver: str = "readability"
    ) -> Dict[str, Any]:
        """
        Archive all articles from an RSS feed.

        Args:
            feed_url: RSS feed URL
            archiver: Archiver to use

        Returns:
            Results summary
        """
        # Parse feed
        items = self.parse_feed(feed_url)

        if not items:
            print("❌ No articles found in feed")
            return {
                "total": 0,
                "successful": 0,
                "failed": 0,
                "items": []
            }

        # Print articles
        print("\nArticles to archive:")
        for i, item in enumerate(items[:10], 1):  # Show first 10
            print(f"  {i}. {item['title']}")
        if len(items) > 10:
            print(f"  ... and {len(items) - 10} more")

        # Submit batch request
        print(f"\n🚀 Submitting batch archive request...")
        task_id = self.batch_archive(items, archiver=archiver)
        print(f"✅ Task created: {task_id}")

        # Wait for completion
        print("\n⏳ Waiting for completion...")
        result = self.wait_for_completion(task_id)

        # Analyze results
        successes = [item for item in result["items"] if item["status"] == "success"]
        failures = [item for item in result["items"] if item["status"] == "failed"]

        print("\n" + "=" * 60)
        print("RESULTS")
        print("=" * 60)
        print(f"Total: {len(result['items'])}")
        print(f"✅ Successful: {len(successes)}")
        print(f"❌ Failed: {len(failures)}")

        # Show failures
        if failures:
            print("\nFailed archives:")
            for item in failures[:5]:  # Show first 5
                print(f"  - {item['id']}: exit_code={item.get('exit_code')}")
            if len(failures) > 5:
                print(f"  ... and {len(failures) - 5} more")

        return {
            "total": len(result["items"]),
            "successful": len(successes),
            "failed": len(failures),
            "items": result["items"]
        }


def main():
    """Example usage."""
    # Initialize archiver
    archiver = RSSArchiver()

    # Example RSS feeds (replace with real feeds)
    feeds = [
        "https://example.com/feed.xml",
        # Add more feeds here
    ]

    print("=" * 60)
    print("RSS FEED ARCHIVER")
    print("=" * 60)

    for feed_url in feeds:
        print(f"\n📰 Processing: {feed_url}")
        print("-" * 60)

        try:
            results = archiver.archive_feed(
                feed_url=feed_url,
                archiver="readability"
            )

            # Summary
            success_rate = (
                (results["successful"] / results["total"] * 100)
                if results["total"] > 0 else 0
            )
            print(f"\n✅ Success rate: {success_rate:.1f}%")

        except Exception as e:
            print(f"❌ Error processing feed: {e}")

        print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
