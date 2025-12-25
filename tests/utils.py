"""
Test utilities, factories, and assertions.

Provides helper functions for creating test data and asserting results.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from app.archivers.base import ArchiveResult


# ==================== Factories ====================

def create_test_article(
    item_id: str = "test_article_1",
    url: str = "https://example.com/test",
    created_at: Optional[datetime] = None,
    pocket_data: Optional[dict] = None,
    metadata: Optional[dict] = None
) -> dict:
    """
    Create a test article data structure.

    Args:
        item_id: Unique item identifier
        url: Article URL
        created_at: Creation timestamp (defaults to now)
        pocket_data: Pocket metadata
        metadata: Readability metadata

    Returns:
        Article dict matching database/storage format

    Example:
        article = create_test_article(item_id="pocket_123", url="https://example.com")
        storage.create_article(**article)
    """
    return {
        'item_id': item_id,
        'url': url,
        'created_at': created_at or datetime.utcnow(),
        'pocket_data': pocket_data or {},
        'metadata': metadata or {}
    }


def create_test_artifact(
    item_id: str = "test_article_1",
    archiver: str = "monolith",
    status: str = "success",
    gcs_path: Optional[str] = None,
    gcs_bucket: Optional[str] = None,
    compressed_size: Optional[int] = None,
    compression_ratio: Optional[float] = None,
    exit_code: int = 0,
    storage_uploads: Optional[list[dict]] = None
) -> dict:
    """
    Create a test artifact data structure.

    Args:
        item_id: Article item_id
        archiver: Archiver name (monolith, singlefile, etc.)
        status: Status (pending, success, failed)
        gcs_path: GCS storage path
        gcs_bucket: GCS bucket name
        compressed_size: Compressed file size in bytes
        compression_ratio: Compression ratio percentage
        exit_code: Archiver exit code
        storage_uploads: List of storage upload results

    Returns:
        Artifact dict matching database/storage format

    Example:
        artifact = create_test_artifact(item_id="test_1", archiver="monolith", status="success")
        storage.update_artifact_status(**artifact)
    """
    return {
        'item_id': item_id,
        'archiver': archiver,
        'status': status,
        'gcs_path': gcs_path or f"gs://test-bucket/archives/{item_id}/{archiver}/output.html.gz",
        'gcs_bucket': gcs_bucket or "test-bucket",
        'compressed_size': compressed_size or 12345,
        'compression_ratio': compression_ratio or 85.5,
        'exit_code': exit_code,
        'storage_uploads': storage_uploads or []
    }


def create_test_summary(
    item_id: str = "test_article_1",
    summary: str = "Test summary",
    tags: Optional[list[str]] = None,
    entities: Optional[list[dict]] = None
) -> dict:
    """
    Create a test summary data structure.

    Args:
        item_id: Article item_id
        summary: Summary text
        tags: List of tags
        entities: List of named entities

    Returns:
        Summary dict matching database/storage format

    Example:
        summary = create_test_summary(item_id="test_1", summary="Article about testing")
        storage.create_summary(**summary)
    """
    return {
        'item_id': item_id,
        'summary': summary,
        'tags': tags or ['test', 'example'],
        'entities': entities or [
            {'text': 'Test Corp', 'type': 'ORG'},
            {'text': 'New York', 'type': 'LOC'}
        ]
    }


# ==================== Assertions ====================

def assert_archive_result_success(result: ArchiveResult):
    """
    Assert that an ArchiveResult indicates success.

    Args:
        result: ArchiveResult to check

    Raises:
        AssertionError: If result is not successful

    Example:
        result = archiver.archive(url="https://example.com", item_id="test")
        assert_archive_result_success(result)
    """
    assert result is not None, "ArchiveResult is None"
    assert result.success, f"Archive failed: exit_code={result.exit_code}, output={result.combined_output}"
    assert result.exit_code == 0, f"Exit code should be 0, got {result.exit_code}"
    assert result.saved_path is not None, "Saved path should not be None"


def assert_archive_result_failure(result: ArchiveResult, expected_exit_code: Optional[int] = None):
    """
    Assert that an ArchiveResult indicates failure.

    Args:
        result: ArchiveResult to check
        expected_exit_code: Optional expected exit code

    Raises:
        AssertionError: If result is not a failure or exit code doesn't match

    Example:
        result = archiver.archive(url="https://404.example.com", item_id="test")
        assert_archive_result_failure(result, expected_exit_code=1)
    """
    assert result is not None, "ArchiveResult is None"
    assert not result.success, f"Archive should have failed but succeeded: {result.saved_path}"

    if expected_exit_code is not None:
        assert result.exit_code == expected_exit_code, \
            f"Expected exit code {expected_exit_code}, got {result.exit_code}"


def assert_file_exists_with_content(file_path: Path, min_size: int = 0):
    """
    Assert that a file exists and has minimum size.

    Args:
        file_path: Path to file
        min_size: Minimum file size in bytes

    Raises:
        AssertionError: If file doesn't exist or is too small

    Example:
        assert_file_exists_with_content(Path("/tmp/output.html"), min_size=100)
    """
    assert file_path.exists(), f"File does not exist: {file_path}"
    assert file_path.is_file(), f"Path is not a file: {file_path}"

    size = file_path.stat().st_size
    assert size >= min_size, f"File too small: {size} bytes (expected at least {min_size})"


def assert_file_not_exists(file_path: Path):
    """
    Assert that a file does not exist.

    Args:
        file_path: Path to file

    Raises:
        AssertionError: If file exists

    Example:
        assert_file_not_exists(Path("/tmp/should_not_exist.html"))
    """
    assert not file_path.exists(), f"File should not exist: {file_path}"


def assert_dict_contains(actual: dict, expected: dict):
    """
    Assert that actual dict contains all expected key-value pairs.

    Partial matching - actual can have additional keys.

    Args:
        actual: Dict to check
        expected: Dict with expected key-value pairs

    Raises:
        AssertionError: If expected keys missing or values don't match

    Example:
        actual = {'a': 1, 'b': 2, 'c': 3}
        assert_dict_contains(actual, {'a': 1, 'b': 2})  # Passes
        assert_dict_contains(actual, {'a': 1, 'd': 4})  # Fails
    """
    for key, value in expected.items():
        assert key in actual, f"Key '{key}' missing from dict"
        assert actual[key] == value, f"Expected {key}={value}, got {actual[key]}"


# ==================== Test Data Generators ====================

def generate_test_urls(count: int = 5) -> list[str]:
    """
    Generate test URLs.

    Args:
        count: Number of URLs to generate

    Returns:
        List of test URLs

    Example:
        urls = generate_test_urls(count=10)
        for url in urls:
            archiver.archive(url=url, item_id=f"test_{i}")
    """
    return [f"https://example.com/article/{i}" for i in range(count)]


def generate_test_item_ids(prefix: str = "test", count: int = 5) -> list[str]:
    """
    Generate test item IDs.

    Args:
        prefix: Prefix for item IDs
        count: Number of IDs to generate

    Returns:
        List of item IDs

    Example:
        item_ids = generate_test_item_ids(prefix="pocket", count=10)
    """
    return [f"{prefix}_{i}" for i in range(count)]


# ==================== File Helpers ====================

def create_dummy_html_file(path: Path, content: Optional[str] = None) -> Path:
    """
    Create a dummy HTML file for testing.

    Args:
        path: Where to create the file
        content: HTML content (default: minimal HTML)

    Returns:
        Path to created file

    Example:
        html_file = create_dummy_html_file(tmp_path / "test.html")
        result = storage.upload_file(html_file, "test/file.html")
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    if content is None:
        content = "<html><head><title>Test</title></head><body><h1>Test Page</h1></body></html>"

    path.write_text(content, encoding='utf-8')
    return path


def create_dummy_binary_file(path: Path, size_bytes: int = 1024) -> Path:
    """
    Create a dummy binary file for testing.

    Args:
        path: Where to create the file
        size_bytes: File size in bytes

    Returns:
        Path to created file

    Example:
        binary_file = create_dummy_binary_file(tmp_path / "test.bin", size_bytes=10240)
        result = storage.upload_file(binary_file, "test/file.bin", compress=True)
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'\x00' * size_bytes)
    return path


# ==================== Comparison Helpers ====================

def files_are_identical(file1: Path, file2: Path) -> bool:
    """
    Check if two files have identical content.

    Args:
        file1: First file
        file2: Second file

    Returns:
        True if files are identical

    Example:
        storage.download_file("path/to/file", local_path)
        assert files_are_identical(original_file, local_path)
    """
    if not file1.exists() or not file2.exists():
        return False

    return file1.read_bytes() == file2.read_bytes()


def assert_files_identical(file1: Path, file2: Path):
    """
    Assert that two files have identical content.

    Args:
        file1: First file
        file2: Second file

    Raises:
        AssertionError: If files are not identical

    Example:
        assert_files_identical(original_file, downloaded_file)
    """
    assert file1.exists(), f"File 1 does not exist: {file1}"
    assert file2.exists(), f"File 2 does not exist: {file2}"

    content1 = file1.read_bytes()
    content2 = file2.read_bytes()

    assert content1 == content2, \
        f"Files differ: {file1} ({len(content1)} bytes) vs {file2} ({len(content2)} bytes)"
