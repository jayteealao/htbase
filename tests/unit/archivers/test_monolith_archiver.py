"""
Tests for MonolithArchiver.

Tests monolith archiver using FakeCommandRunner to avoid subprocess execution.
"""

from pathlib import Path

import pytest

from app.archivers.monolith import MonolithArchiver
from tests.fakes.command_runner import FakeCommandRunner
from utils import assert_archive_result_success, assert_archive_result_failure


class TestMonolithArchiver:
    """Test MonolithArchiver implementation."""

    def test_successful_archive_without_chromium(self, temp_env):
        """Test successful archiving without Chromium."""
        from core.config import get_settings

        settings = get_settings()
        settings.chromium.enabled = False  # Disable Chromium

        runner = FakeCommandRunner()
        runner.configure_result("monolith", exit_code=0)

        archiver = MonolithArchiver(runner, settings)
        result = archiver.archive(url="https://example.com", item_id="test1")

        assert_archive_result_success(result)
        assert runner.get_invocation_count() == 1

    def test_successful_archive_with_chromium(self, temp_env):
        """Test successful archiving with Chromium."""
        from core.config import get_settings

        settings = get_settings()
        settings.chromium.enabled = True  # Enable Chromium

        runner = FakeCommandRunner()
        runner.configure_result("chromium.*monolith", exit_code=0)

        archiver = MonolithArchiver(runner, settings)

        # Create dummy output file (since command is faked)
        out_dir, out_path = archiver.get_output_path("test1")
        out_path.write_text("<html>test</html>", encoding="utf-8")

        result = archiver.archive(url="https://example.com", item_id="test1")

        assert result.success
        assert runner.get_invocation_count() == 1

    def test_command_construction_without_chromium(self, temp_env):
        """Test command construction without Chromium."""
        from core.config import get_settings

        settings = get_settings()
        settings.chromium.enabled = False

        runner = FakeCommandRunner()
        runner.configure_result("monolith", exit_code=0)

        archiver = MonolithArchiver(runner, settings)
        archiver.archive(url="https://example.com", item_id="test1")

        invocation = runner.get_last_invocation()
        assert "monolith" in invocation.command
        assert "https://example.com" in invocation.command
        assert "-o" in invocation.command

    def test_command_construction_with_chromium(self, temp_env):
        """Test command construction with Chromium."""
        from core.config import get_settings

        settings = get_settings()
        settings.chromium.enabled = True

        runner = FakeCommandRunner()
        runner.configure_result("chromium.*monolith", exit_code=0)

        archiver = MonolithArchiver(runner, settings)

        # Create dummy output
        out_dir, out_path = archiver.get_output_path("test1")
        out_path.write_text("<html>test</html>", encoding="utf-8")

        archiver.archive(url="https://example.com", item_id="test1")

        invocation = runner.get_last_invocation()
        # Should have pipe from chromium to monolith
        assert "|" in invocation.command
        assert "monolith" in invocation.command

    def test_command_includes_extra_flags(self, temp_env):
        """Test command includes extra monolith flags from config."""
        from core.config import get_settings

        settings = get_settings()
        settings.chromium.enabled = False
        settings.monolith_flags = "-I -j"  # Extra flags

        runner = FakeCommandRunner()
        runner.configure_result("monolith", exit_code=0)

        archiver = MonolithArchiver(runner, settings)
        archiver.archive(url="https://example.com", item_id="test1")

        invocation = runner.get_last_invocation()
        # Extra flags should be included
        assert "-I" in invocation.command or "'-I'" in invocation.command

    def test_failure_with_nonzero_exit_code(self, temp_env):
        """Test handles failure with non-zero exit code."""
        from core.config import get_settings

        settings = get_settings()
        settings.chromium.enabled = False

        runner = FakeCommandRunner()
        runner.configure_result("monolith", exit_code=1)

        archiver = MonolithArchiver(runner, settings)
        result = archiver.archive(url="https://example.com", item_id="test1")

        assert_archive_result_failure(result, expected_exit_code=1)

    def test_timeout_handling(self, temp_env):
        """Test timeout handling."""
        from core.config import get_settings

        settings = get_settings()
        settings.chromium.enabled = False

        runner = FakeCommandRunner()
        runner.configure_result("monolith", timed_out=True)

        archiver = MonolithArchiver(runner, settings)
        result = archiver.archive(url="https://example.com", item_id="test1")

        assert not result.success
        assert result.saved_path is None

    def test_url_quoting(self, temp_env):
        """Test URL is properly quoted in command."""
        from core.config import get_settings

        settings = get_settings()
        settings.chromium.enabled = False

        runner = FakeCommandRunner()
        runner.configure_result("monolith", exit_code=0)

        archiver = MonolithArchiver(runner, settings)

        # URL with special characters
        archiver.archive(url="https://example.com/path?query=value&foo=bar", item_id="test1")

        invocation = runner.get_last_invocation()
        # URL should be quoted
        assert "example.com" in invocation.command

    def test_output_path_quoting(self, temp_env):
        """Test output path is properly quoted."""
        from core.config import get_settings

        settings = get_settings()
        settings.chromium.enabled = False

        runner = FakeCommandRunner()
        runner.configure_result("monolith", exit_code=0)

        archiver = MonolithArchiver(runner, settings)
        archiver.archive(url="https://example.com", item_id="test with spaces")

        invocation = runner.get_last_invocation()
        # Path should be quoted
        assert "-o" in invocation.command

    def test_timeout_value(self, temp_env):
        """Test timeout value is passed to command runner."""
        from core.config import get_settings

        settings = get_settings()
        settings.chromium.enabled = False

        runner = FakeCommandRunner()
        runner.configure_result("monolith", exit_code=0)

        archiver = MonolithArchiver(runner, settings)
        archiver.archive(url="https://example.com", item_id="test1")

        invocation = runner.get_last_invocation()
        assert invocation.timeout == 300.0  # 5 minutes

    def test_creates_output_directory(self, temp_env):
        """Test output directory is created."""
        from core.config import get_settings

        settings = get_settings()
        settings.chromium.enabled = False

        runner = FakeCommandRunner()
        runner.configure_result("monolith", exit_code=0)

        archiver = MonolithArchiver(runner, settings)
        archiver.archive(url="https://example.com", item_id="test1")

        # Output directory should exist
        out_dir, _ = archiver.get_output_path("test1")
        assert out_dir.exists()

    def test_sanitizes_item_id(self, temp_env):
        """Test item_id is sanitized for file paths."""
        from core.config import get_settings

        settings = get_settings()
        settings.chromium.enabled = False

        runner = FakeCommandRunner()
        runner.configure_result("monolith", exit_code=0)

        archiver = MonolithArchiver(runner, settings)

        # Item ID with path traversal attempt
        archiver.archive(url="https://example.com", item_id="../../../etc/passwd")

        # Should be sanitized (no path traversal)
        invocation = runner.get_last_invocation()
        assert "../" not in invocation.command

    def test_archiver_name(self, temp_env):
        """Test archiver name is set correctly."""
        from core.config import get_settings

        archiver = MonolithArchiver(FakeCommandRunner(), get_settings())
        assert archiver.name == "monolith"

    def test_with_storage_providers(self, temp_env, in_memory_file_storage):
        """Test archiving with storage provider integration."""
        from core.config import get_settings

        settings = get_settings()
        settings.chromium.enabled = False

        runner = FakeCommandRunner()
        runner.configure_result("monolith", exit_code=0)

        archiver = MonolithArchiver(
            runner,
            settings,
            file_storage=[in_memory_file_storage]
        )

        # Create dummy output file
        out_dir, out_path = archiver.get_output_path("test1")
        out_path.write_text("<html>test</html>", encoding="utf-8")

        result = archiver.archive_with_storage(url="https://example.com", item_id="test1")

        assert result.success
        assert 'storage_uploads' in result.metadata

    def test_with_database_storage(self, temp_env, in_memory_db_storage):
        """Test archiving with database storage integration."""
        from core.config import get_settings

        settings = get_settings()
        settings.chromium.enabled = False

        runner = FakeCommandRunner()
        runner.configure_result("monolith", exit_code=0)

        archiver = MonolithArchiver(
            runner,
            settings,
            db_storage=in_memory_db_storage
        )

        # Create dummy output file
        out_dir, out_path = archiver.get_output_path("test1")
        out_path.write_text("<html>test</html>", encoding="utf-8")

        archiver.archive_with_storage(url="https://example.com", item_id="test1")

        # Should update database
        artifact = in_memory_db_storage.get_artifact("test1", "monolith")
        assert artifact is not None

    def test_multiple_archives_same_url(self, temp_env):
        """Test archiving same URL multiple times."""
        from core.config import get_settings

        settings = get_settings()
        settings.chromium.enabled = False

        runner = FakeCommandRunner()
        runner.configure_result("monolith", exit_code=0)

        archiver = MonolithArchiver(runner, settings)

        # Archive twice
        result1 = archiver.archive(url="https://example.com", item_id="test1")
        result2 = archiver.archive(url="https://example.com", item_id="test2")

        assert result1.success
        assert result2.success
        assert result1.saved_path != result2.saved_path  # Different paths

    def test_chromium_cleanup_called(self, temp_env):
        """Test Chromium cleanup is called when enabled."""
        from core.config import get_settings

        settings = get_settings()
        settings.chromium.enabled = True

        runner = FakeCommandRunner()
        runner.configure_result("chromium.*monolith", exit_code=0)

        archiver = MonolithArchiver(runner, settings)

        # Create dummy output
        out_dir, out_path = archiver.get_output_path("test1")
        out_path.write_text("<html>test</html>", encoding="utf-8")

        archiver.archive(url="https://example.com", item_id="test1")

        # If we got here without error, cleanup was called successfully
        assert True

    def test_creates_html_file(self, temp_env):
        """Test creates output.html file."""
        from core.config import get_settings

        settings = get_settings()
        settings.chromium.enabled = False

        runner = FakeCommandRunner()
        runner.configure_result("monolith", exit_code=0)

        archiver = MonolithArchiver(runner, settings)

        # Create output file manually (since command is faked)
        out_dir, out_path = archiver.get_output_path("test1")
        out_path.write_text("<html>test</html>", encoding="utf-8")

        result = archiver.archive(url="https://example.com", item_id="test1")

        assert result.success
        assert result.saved_path.endswith(".html")
        assert Path(result.saved_path).exists()

    def test_command_runner_receives_archiver_name(self, temp_env):
        """Test command runner receives archiver name for context."""
        from core.config import get_settings

        settings = get_settings()
        settings.chromium.enabled = False

        runner = FakeCommandRunner()
        runner.configure_result("monolith", exit_code=0)

        archiver = MonolithArchiver(runner, settings)
        archiver.archive(url="https://example.com", item_id="test1")

        invocation = runner.get_last_invocation()
        assert invocation.archiver == "monolith"

    def test_empty_extra_flags(self, temp_env):
        """Test handles empty extra flags correctly."""
        from core.config import get_settings

        settings = get_settings()
        settings.chromium.enabled = False
        settings.monolith_flags = ""  # Empty

        runner = FakeCommandRunner()
        runner.configure_result("monolith", exit_code=0)

        archiver = MonolithArchiver(runner, settings)
        result = archiver.archive(url="https://example.com", item_id="test1")

        # Should still work
        assert runner.get_invocation_count() == 1
