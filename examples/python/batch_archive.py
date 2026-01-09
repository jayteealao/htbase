"""
Batch archive example - Archive multiple URLs efficiently.

Usage:
    python batch_archive.py

Requirements:
    pip install requests
"""

import requests
import time
from typing import List, Dict, Any


class HTBaseClient:
    """Client for HTBase API."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        """
        Initialize HTBase client.

        Args:
            base_url: HTBase API base URL
        """
        self.base_url = base_url

    def batch_archive(
        self,
        items: List[Dict[str, str]],
        archiver: str = "readability"
    ) -> str:
        """
        Submit batch archive request.

        Args:
            items: List of dicts with 'url' and 'id' keys
            archiver: Archiver to use

        Returns:
            Task ID for tracking

        Raises:
            requests.exceptions.RequestException: If the request fails
        """
        endpoint = f"{self.base_url}/api/batch/{archiver}"

        response = requests.post(
            endpoint,
            json={"items": items},
            timeout=30
        )
        response.raise_for_status()

        result = response.json()
        return result["task_id"]

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        Get status of a batch task.

        Args:
            task_id: Task ID from batch_archive()

        Returns:
            Dictionary with task status

        Raises:
            requests.exceptions.RequestException: If the request fails
        """
        endpoint = f"{self.base_url}/api/tasks/{task_id}"

        response = requests.get(endpoint, timeout=10)
        response.raise_for_status()

        return response.json()

    def wait_for_completion(
        self,
        task_id: str,
        poll_interval: int = 5,
        max_wait: int = 600
    ) -> Dict[str, Any]:
        """
        Wait for batch task to complete.

        Args:
            task_id: Task ID to wait for
            poll_interval: Seconds between status checks
            max_wait: Maximum seconds to wait

        Returns:
            Final task status

        Raises:
            TimeoutError: If task doesn't complete in max_wait seconds
        """
        start = time.time()
        while time.time() - start < max_wait:
            status = self.get_task_status(task_id)

            # Check if completed
            if status["status"] in ["success", "failed"]:
                return status

            # Wait before next poll
            time.sleep(poll_interval)

        raise TimeoutError(f"Task {task_id} did not complete in {max_wait}s")


def main():
    """Example usage."""
    # Initialize client
    client = HTBaseClient()

    # URLs to archive
    urls_to_archive = [
        "https://example.com/article-1",
        "https://example.com/article-2",
        "https://example.com/article-3",
        "https://example.com/article-4",
        "https://example.com/article-5",
    ]

    # Prepare batch items
    items = [
        {
            "url": url,
            "id": f"article-{i+1}"
        }
        for i, url in enumerate(urls_to_archive)
    ]

    print(f"Batch archiving {len(items)} URLs...")
    print("-" * 50)

    try:
        # Submit batch request
        task_id = client.batch_archive(items, archiver="readability")
        print(f"✅ Batch task created: {task_id}")

        # Wait for completion
        print("Waiting for completion...")
        result = client.wait_for_completion(task_id, poll_interval=5)

        # Print results
        print("-" * 50)
        print(f"Batch status: {result['status']}")
        print(f"Total items: {len(result['items'])}")

        # Count successes and failures
        successes = [item for item in result["items"] if item["status"] == "success"]
        failures = [item for item in result["items"] if item["status"] == "failed"]

        print(f"✅ Successful: {len(successes)}")
        print(f"❌ Failed: {len(failures)}")

        # Print details
        if successes:
            print("\nSuccessful archives:")
            for item in successes:
                print(f"  - {item['id']}: {item['saved_path']}")

        if failures:
            print("\nFailed archives:")
            for item in failures:
                print(f"  - {item['id']}: exit_code={item.get('exit_code')}")

    except TimeoutError as e:
        print(f"❌ {e}")

    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")


if __name__ == "__main__":
    main()
