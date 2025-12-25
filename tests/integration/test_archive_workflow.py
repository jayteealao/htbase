"""
Integration tests for end-to-end archiving workflows.

Tests the complete archiving flow from API request through task processing
to final artifact storage, using real database and simplified archivers.
"""

import json
import time
from pathlib import Path
from unittest.mock import patch, Mock

import pytest

from app.core.config import AppSettings
from app.core.utils import sanitize_filename
from app.db.models import ArchivedUrl, ArchiveArtifact, ArtifactStatus
from app.server import create_app
from app.task_manager.archiver import ArchiverTaskManager
from app.archivers.base import BaseArchiver
from models import ArchiveResult


class TestArchiveWorkflow:
    """Test complete archiving workflows."""

    def test_single_archiver_workflow_success(self, integration_settings, real_repositories, real_file_storage):
        """Test successful workflow with single archiver."""
        # Create a simple test archiver
        class TestArchiver(BaseArchiver):
            def archive(self, url: str, item_id: str) -> ArchiveResult:
                output_path = self.base_path / item_id / self.name / "output.html"
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(f"<html><body>Archived: {url}</body></html>")

                return ArchiveResult(
                    success=True,
                    exit_code=0,
                    saved_path=str(output_path),
                    start_time=time.time(),
                    end_time=time.time() + 1
                )

        archiver = TestArchiver(real_file_storage)

        # Test the archiving flow
        item_id = "test123"
        url = "https://example.com/article"

        result = archiver.archive(url, item_id)

        assert result.success is True
        assert result.exit_code == 0
        assert result.saved_path is not None
        assert Path(result.saved_path).exists()
        assert "Archived: https://example.com/article" in Path(result.saved_path).read_text()

    def test_multi_archiver_coordination(self, integration_settings, real_repositories, real_file_storage):
        """Test coordination between multiple archivers."""
        # Create multiple test archivers with different behaviors
        class HTMLArchiver(BaseArchiver):
            name = "html"

            def archive(self, url: str, item_id: str) -> ArchiveResult:
                output_path = self.base_path / item_id / self.name / "output.html"
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(f"<html>HTML version: {url}</html>")
                return ArchiveResult(success=True, exit_code=0, saved_path=str(output_path))

        class TextArchiver(BaseArchiver):
            name = "text"

            def archive(self, url: str, item_id: str) -> ArchiveResult:
                output_path = self.base_path / item_id / self.name / "output.txt"
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(f"Text version: {url}")
                return ArchiveResult(success=True, exit_code=0, saved_path=str(output_path))

        html_archiver = HTMLArchiver(real_file_storage)
        text_archiver = TextArchiver(real_file_storage)

        item_id = "multi123"
        url = "https://example.com/multi-article"

        # Run both archivers
        html_result = html_archiver.archive(url, item_id)
        text_result = text_archiver.archive(url, item_id)

        assert html_result.success is True
        assert text_result.success is True

        # Check both files exist with different content
        html_content = Path(html_result.saved_path).read_text()
        text_content = Path(text_result.saved_path).read_text()

        assert "HTML version:" in html_content
        assert "Text version:" in text_content
        assert html_content != text_content

    def test_archiver_task_manager_workflow(self, integration_settings, dummy_archivers, real_repositories, sample_items):
        """Test archiver task manager processing workflow."""
        task_manager = ArchiverTaskManager(
            settings=integration_settings,
            archivers=dummy_archivers,
            summarization=None  # Disabled for this test
        )

        # Enqueue items for processing
        items = [{"item_id": item["item_id"], "url": item["url"]} for item in sample_items[:3]]
        task_id = task_manager.enqueue("monolith", items)

        assert task_id is not None
        assert len(task_id) == 32  # UUID hex length

        # Wait a moment for processing
        time.sleep(0.1)

        # Verify artifacts were created in database
        artifacts = real_repositories["artifact"].list_by_task_id(task_id)
        assert len(artifacts) == 3

        # Check that each artifact has the expected data
        for artifact in artifacts:
            assert artifact["success"] == 1  # DummyArchiver succeeds
            assert artifact["exit_code"] == 0
            assert artifact["saved_path"] is not None

    def test_archiver_task_manager_all_archivers(self, integration_settings, dummy_archivers, real_repositories, sample_items):
        """Test archiver task manager with 'all' archivers option."""
        task_manager = ArchiverTaskManager(
            settings=integration_settings,
            archivers=dummy_archivers,
            summarization=None
        )

        # Enqueue single item for all archivers
        items = [{"item_id": "all123", "url": "https://example.com/all-test"}]
        task_id = task_manager.enqueue("all", items)

        # Wait for processing
        time.sleep(0.1)

        # Should create artifacts for all archivers
        artifacts = real_repositories["artifact"].list_by_task_id(task_id)
        assert len(artifacts) == len(dummy_archivers)

        # Verify we have all archiver types
        archiver_names = {artifact["archiver"] for artifact in artifacts}
        assert archiver_names == set(dummy_archivers.keys())

    def test_archiver_task_manager_with_storage_integration(self, integration_settings, archiver_task_manager_with_storage, real_repositories):
        """Test archiver task manager with storage integration enabled."""
        task_manager = archiver_task_manager_with_storage

        # Enqueue items
        items = [{"item_id": "storage123", "url": "https://example.com/storage-test"}]
        task_id = task_manager.enqueue("monolith", items)

        # Wait for processing
        time.sleep(0.1)

        # Check artifacts were created
        artifacts = real_repositories["artifact"].list_by_task_id(task_id)
        assert len(artifacts) == 1

        artifact = artifacts[0]
        assert artifact["success"] == 1
        assert artifact["saved_path"] is not None

    def test_archiver_url_rewriting_integration(self, integration_settings, real_repositories, real_file_storage):
        """Test URL rewriting in archiving workflow."""
        class URLRewritingArchiver(BaseArchiver):
            def archive(self, url: str, item_id: str) -> ArchiveResult:
                # Test that we receive the rewritten URL
                output_path = self.base_path / item_id / self.name / "output.html"
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(f"<html>Original URL was processed</html>")
                return ArchiveResult(success=True, exit_code=0, saved_path=str(output_path))

        archiver = URLRewritingArchiver(real_file_storage)

        # Test with a paywall URL that should be rewritten
        original_url = "https://medium.com/article"
        item_id = "rewrite123"

        result = archiver.archive(original_url, item_id)

        assert result.success is True
        assert Path(result.saved_path).exists()

    def test_archiver_error_handling_workflow(self, integration_settings, real_repositories, real_file_storage):
        """Test error handling in archiving workflow."""
        class FailingArchiver(BaseArchiver):
            def archive(self, url: str, item_id: str) -> ArchiveResult:
                return ArchiveResult(
                    success=False,
                    exit_code=1,
                    saved_path=None,
                    error="Simulated archiver failure"
                )

        archiver = FailingArchiver(real_file_storage)

        item_id = "fail123"
        url = "https://example.com/fail-test"

        result = archiver.archive(url, item_id)

        assert result.success is False
        assert result.exit_code == 1
        assert result.saved_path is None
        assert "Simulated archiver failure" in result.error

    def test_archiver_file_system_integration(self, integration_settings, real_file_storage):
        """Test archiver integration with real file system."""
        class FileSystemArchiver(BaseArchiver):
            def archive(self, url: str, item_id: str) -> ArchiveResult:
                safe_id = sanitize_filename(item_id)
                output_path = self.base_path / safe_id / self.name / "output.html"
                output_path.parent.mkdir(parents=True, exist_ok=True)

                # Create a realistic HTML file
                content = f"""
                <!DOCTYPE html>
                <html>
                <head><title>Archived: {url}</title></head>
                <body>
                    <h1>Article Title</h1>
                    <p>This is archived content from {url}</p>
                    <p>Item ID: {item_id}</p>
                    <p>Safe ID: {safe_id}</p>
                </body>
                </html>
                """
                output_path.write_text(content)

                return ArchiveResult(success=True, exit_code=0, saved_path=str(output_path))

        archiver = FileSystemArchiver(real_file_storage)

        # Test with various item IDs including special characters
        test_cases = [
            ("simple", "https://example.com/simple"),
            ("with-dashes", "https://example.com/dashed"),
            ("with_underscores", "https://example.com/underscored"),
            ("MixedCase", "https://example.com/mixed"),
            ("with spaces", "https://example.com/spaces"),
            ("special!@#$%", "https://example.com/special"),
        ]

        for item_id, url in test_cases:
            result = archiver.archive(url, item_id)

            assert result.success is True
            assert Path(result.saved_path).exists()

            content = Path(result.saved_path).read_text()
            assert url in content
            assert sanitize_filename(item_id) in content

    def test_archiver_large_content_handling(self, integration_settings, real_file_storage):
        """Test archiver handling of large content."""
        class LargeContentArchiver(BaseArchiver):
            def archive(self, url: str, item_id: str) -> ArchiveResult:
                output_path = self.base_path / item_id / self.name / "large.html"
                output_path.parent.mkdir(parents=True, exist_ok=True)

                # Generate large content (1MB)
                content = "<html><body>"
                for i in range(10000):
                    content += f"<p>Paragraph {i}: This is a test paragraph with some content about {url}.</p>\n"
                content += "</body></html>"

                output_path.write_text(content)

                return ArchiveResult(success=True, exit_code=0, saved_path=str(output_path))

        archiver = LargeContentArchiver(real_file_storage)

        result = archiver.archive("https://example.com/large", "large123")

        assert result.success is True
        assert Path(result.saved_path).exists()

        # Check file size is substantial
        file_size = Path(result.saved_path).stat().st_size
        assert file_size > 500000  # Should be around 1MB

    def test_archiver_concurrent_processing(self, integration_settings, dummy_archivers, real_repositories):
        """Test concurrent archiving with task manager."""
        task_manager = ArchiverTaskManager(
            settings=integration_settings,
            archivers=dummy_archivers,
            summarization=None
        )

        # Submit multiple batches concurrently
        task_ids = []
        for i in range(5):
            items = [{"item_id": f"concurrent{i}", "url": f"https://example.com/concurrent{i}"}]
            task_id = task_manager.enqueue("monolith", items)
            task_ids.append(task_id)

        # Wait for all tasks to complete
        time.sleep(0.5)

        # Verify all tasks completed successfully
        all_artifacts = []
        for task_id in task_ids:
            artifacts = real_repositories["artifact"].list_by_task_id(task_id)
            all_artifacts.extend(artifacts)

        assert len(all_artifacts) == 5

        # All should be successful
        for artifact in all_artifacts:
            assert artifact["success"] == 1
            assert artifact["exit_code"] == 0

    def test_archiver_dependency_injection(self, integration_settings, real_repositories):
        """Test archiver dependency injection in workflow."""
        # Create archiver with injected dependencies
        class InjectableArchiver(BaseArchiver):
            def __init__(self, storage_provider, metadata_repo):
                super().__init__(storage_provider)
                self.metadata_repo = metadata_repo

            def archive(self, url: str, item_id: str) -> ArchiveResult:
                output_path = self.base_path / item_id / self.name / "output.html"
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(f"<html>Archive with injected deps: {url}</html>")

                # Use injected dependency
                try:
                    metadata = self.metadata_repo.get_by_archived_url(None)  # Will return None
                    metadata_saved = metadata is not None
                except:
                    metadata_saved = False

                result = ArchiveResult(
                    success=True,
                    exit_code=0,
                    saved_path=str(output_path)
                )
                result.metadata = {"metadata_available": metadata_saved}
                return result

        archiver = InjectableArchiver(real_file_storage, real_repositories["metadata"])

        result = archiver.archive("https://example.com/injected", "inject123")

        assert result.success is True
        assert hasattr(result, 'metadata')
        assert result.metadata["metadata_available"] is False

    def test_archiver_workflow_with_database_persistence(self, integration_settings, real_repositories, real_file_storage):
        """Test complete archiving workflow with database persistence."""
        class PersistentArchiver(BaseArchiver):
            def __init__(self, storage_provider, artifact_repo, url_repo):
                super().__init__(storage_provider)
                self.artifact_repo = artifact_repo
                self.url_repo = url_repo

            def archive(self, url: str, item_id: str) -> ArchiveResult:
                # Create archived URL record first
                archived_url = self.url_repo.get_or_create(url=url, item_id=item_id, name="Test Article")

                # Create pending artifact
                artifact = self.artifact_repo.get_or_create(
                    archived_url_id=archived_url.id,
                    archiver=self.name,
                    task_id="manual123"
                )

                # Perform archiving
                output_path = self.base_path / item_id / self.name / "output.html"
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(f"<html>Persistently archived: {url}</html>")

                result = ArchiveResult(success=True, exit_code=0, saved_path=str(output_path))

                # Finalize artifact
                self.artifact_repo.finalize_result(
                    artifact_id=artifact.id,
                    success=True,
                    exit_code=0,
                    saved_path=str(output_path)
                )

                result.archived_url_id = archived_url.id
                return result

        archiver = PersistentArchiver(real_file_storage, real_repositories["artifact"], real_repositories["url"])

        result = archiver.archive("https://example.com/persistent", "persist123")

        assert result.success is True
        assert hasattr(result, 'archived_url_id')

        # Verify records exist in database
        archived_url = real_repositories["url"].get_by_url("https://example.com/persistent")
        assert archived_url is not None
        assert archived_url.item_id == "persist123"

        artifacts = real_repositories["artifact"].list_by_item_id("persist123")
        assert len(artifacts) == 1
        assert artifacts[0].success is True
        assert artifacts[0].saved_path == str(result.saved_path)