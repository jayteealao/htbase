"""
Tests for SingleFileCLIArchiver.

Tests SingleFile CLI archiver using FakeCommandRunner to avoid subprocess execution.
"""

from pathlib import Path
import json

import pytest

from app.archivers.singlefile_cli import SingleFileCLIArchiver
from tests.fakes.command_runner import FakeCommandRunner
from utils import assert_archive_result_success, assert_archive_result_failure


class TestSingleFileCLIArchiver:
    """Test SingleFileCLIArchiver implementation."""

    def test_successful_archive_basic(self, temp_env):
        """Test successful archiving with basic configuration."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("single-file", exit_code=0)

        # Create dummy HTML file (since command is faked)
        archiver = SingleFileCLIArchiver(runner, settings)
        out_dir, out_path = archiver.get_output_path("test1")
        out_path.write_text("<html><body>SingleFile archive</body></html>", encoding="utf-8")

        result = archiver.archive(url="https://example.com", item_id="test1")

        assert result.success
        assert result.saved_path.endswith(".html")
        assert out_path.exists()

    def test_command_construction_basic(self, temp_env):
        """Test basic SingleFile command construction."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("single-file", exit_code=0)

        archiver = SingleFileCLIArchiver(runner, settings)
        archiver.archive(url="https://example.com", item_id="test1")

        invocation = runner.get_last_invocation()

        # Should include SingleFile binary and URL
        assert "single-file" in invocation.command or "singlefile" in invocation.command
        assert "https://example.com" in invocation.command

    def test_command_includes_output_path(self, temp_env):
        """Test command includes output path."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("single-file", exit_code=0)

        archiver = SingleFileCLIArchiver(runner, settings)
        out_dir, out_path = archiver.get_output_path("test1")

        archiver.archive(url="https://example.com", item_id="test1")

        invocation = runner.get_last_invocation()
        # Should include the output path
        assert str(out_path) in invocation.command

    def test_includes_browser_executable_path(self, temp_env):
        """Test command includes browser executable path when configured."""
        from core.config import get_settings

        settings = get_settings()
        settings.chromium_bin = "/usr/bin/chromium"

        runner = FakeCommandRunner()
        runner.configure_result("single-file", exit_code=0)

        archiver = SingleFileCLIArchiver(runner, settings)
        archiver.archive(url="https://example.com", item_id="test1")

        invocation = runner.get_last_invocation()
        assert "--browser-executable-path=/usr/bin/chromium" in invocation.command

    def test_no_browser_executable_when_already_specified(self, temp_env):
        """Test no duplicate browser executable when already in flags."""
        from core.config import get_settings

        settings = get_settings()
        settings.chromium_bin = "/usr/bin/chromium"
        settings.singlefile_flags = "--browser-executable-path=/custom/chrome"

        runner = FakeCommandRunner()
        runner.configure_result("single-file", exit_code=0)

        archiver = SingleFileCLIArchiver(runner, settings)
        archiver.archive(url="https://example.com", item_id="test1")

        invocation = runner.get_last_invocation()
        # Should not add duplicate browser-executable-path
        assert invocation.command.count("--browser-executable-path") == 1
        assert "/custom/chrome" in invocation.command

    def test_browser_args_user_data_dir(self, temp_env):
        """Test browser args include user data directory."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("single-file", exit_code=0)

        archiver = SingleFileCLIArchiver(runner, settings)
        archiver.archive(url="https://example.com", item_id="test1")

        invocation = runner.get_last_invocation()
        # Should include browser-args with user-data-dir
        assert "--browser-args=" in invocation.command
        assert "--user-data-dir=" in invocation.command

    def test_browser_args_prevent_profile_locks(self, temp_env):
        """Test browser args include flags to prevent profile locks."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("single-file", exit_code=0)

        archiver = SingleFileCLIArchiver(runner, settings)
        archiver.archive(url="https://example.com", item_id="test1")

        invocation = runner.get_last_invocation()

        # Should include critical flags to prevent lock conflicts
        assert "--no-first-run" in invocation.command
        assert "--no-default-browser-check" in invocation.command
        assert "--disable-features=LockProfileCookieDatabase" in invocation.command

    def test_merges_existing_browser_args(self, temp_env):
        """Test existing browser args are merged with default args."""
        from core.config import get_settings

        settings = get_settings()
        # Pre-existing browser args
        existing_args = ["--some-flag=value", "--another-flag"]
        settings.singlefile_flags = f'--browser-args={json.dumps(existing_args)}'

        runner = FakeCommandRunner()
        runner.configure_result("single-file", exit_code=0)

        archiver = SingleFileCLIArchiver(runner, settings)
        archiver.archive(url="https://example.com", item_id="test1")

        invocation = runner.get_last_invocation()

        # Should include both existing and new args
        assert "--some-flag=value" in invocation.command
        assert "--another-flag" in invocation.command
        assert "--user-data-dir=" in invocation.command

    def test_handles_malformed_browser_args(self, temp_env):
        """Test handling of malformed browser args JSON."""
        from core.config import get_settings

        settings = get_settings()
        settings.singlefile_flags = '--browser-args="not valid json"'

        runner = FakeCommandRunner()
        runner.configure_result("single-file", exit_code=0)

        archiver = SingleFileCLIArchiver(runner, settings)
        archiver.archive(url="https://example.com", item_id="test1")

        invocation = runner.get_last_invocation()

        # Should still work with fallback args
        assert "--user-data-dir=" in invocation.command
        assert "--no-first-run" in invocation.command

    def test_extra_singlefile_flags(self, temp_env):
        """Test extra SingleFile flags are included."""
        from core.config import get_settings

        settings = get_settings()
        settings.singlefile_flags = "--option1=value1 --option2=value2"

        runner = FakeCommandRunner()
        runner.configure_result("single-file", exit_code=0)

        archiver = SingleFileCLIArchiver(runner, settings)
        archiver.archive(url="https://example.com", item_id="test1")

        invocation = runner.get_last_invocation()

        # Should include extra flags
        assert "--option1=value1" in invocation.command
        assert "--option2=value2" in invocation.command

    def test_failure_with_nonzero_exit_code(self, temp_env):
        """Test handles failure with non-zero exit code."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("single-file", exit_code=1)

        archiver = SingleFileCLIArchiver(runner, settings)
        result = archiver.archive(url="https://example.com", item_id="test1")

        assert_archive_result_failure(result, expected_exit_code=1)

    def test_timeout_handling(self, temp_env):
        """Test timeout handling."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("single-file", timed_out=True)

        archiver = SingleFileCLIArchiver(runner, settings)
        result = archiver.archive(url="https://example.com", item_id="test1")

        assert not result.success
        assert result.saved_path is None

    def test_chromium_setup_and_cleanup(self, temp_env):
        """Test Chromium setup and cleanup are called."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("single-file", exit_code=0)

        archiver = SingleFileCLIArchiver(runner, settings)

        # Create dummy HTML file
        out_dir, out_path = archiver.get_output_path("test1")
        out_path.write_text("<html><body>Test</body></html>", encoding="utf-8")

        with patch.object(archiver, 'setup_chromium') as mock_setup, \
             patch.object(archiver, 'cleanup_chromium') as mock_cleanup:

            result = archiver.archive(url="https://example.com", item_id="test1")

            assert result.success
            mock_setup.assert_called_once()
            mock_cleanup.assert_called_once()

    def test_error_during_chromium_cleanup(self, temp_env):
        """Test archive succeeds even if Chromium cleanup fails."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("single-file", exit_code=0)

        archiver = SingleFileCLIArchiver(runner, settings)

        # Create dummy HTML file
        out_dir, out_path = archiver.get_output_path("test1")
        out_path.write_text("<html><body>Test</body></html>", encoding="utf-8")

        with patch.object(archiver, 'setup_chromium'), \
             patch.object(archiver, 'cleanup_chromium', side_effect=Exception("Cleanup failed")):

            result = archiver.archive(url="https://example.com", item_id="test1")

            # Should still succeed despite cleanup error
            assert result.success

    def test_url_quoting(self, temp_env):
        """Test URL is properly quoted."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("single-file", exit_code=0)

        archiver = SingleFileCLIArchiver(runner, settings)

        # URL with special characters
        archiver.archive(url="https://example.com/path?query=value&foo=bar", item_id="test1")

        invocation = runner.get_last_invocation()
        # URL should be quoted but still present
        assert "example.com" in invocation.command

    def test_output_path_quoting(self, temp_env):
        """Test output path is properly quoted."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("single-file", exit_code=0)

        archiver = SingleFileCLIArchiver(runner, settings)
        archiver.archive(url="https://example.com", item_id="test with spaces")

        invocation = runner.get_last_invocation()
        # Command should execute despite spaces in path
        assert invocation.command is not None

    def test_sanitizes_item_id_in_path(self, temp_env):
        """Test item_id is sanitized for file paths."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("single-file", exit_code=0)

        archiver = SingleFileCLIArchiver(runner, settings)

        # Item ID with path traversal attempt
        archiver.archive(url="https://example.com", item_id="../../../etc/passwd")

        # Should be sanitized (no path traversal in command)
        invocation = runner.get_last_invocation()
        assert "../" not in invocation.command

    def test_timeout_value_passed_to_runner(self, temp_env):
        """Test timeout value is passed to command runner."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("single-file", exit_code=0)

        archiver = SingleFileCLIArchiver(runner, settings)
        out_dir, out_path = archiver.get_output_path("test1")
        out_path.write_text("<html><body>Test</body></html>", encoding="utf-8")

        archiver.archive(url="https://example.com", item_id="test1")

        invocation = runner.get_last_invocation()
        assert invocation.timeout == 300.0  # 5 minutes

    def test_archiver_name_passed_to_runner(self, temp_env):
        """Test archiver name is passed to command runner."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("single-file", exit_code=0)

        archiver = SingleFileCLIArchiver(runner, settings)
        out_dir, out_path = archiver.get_output_path("test1")
        out_path.write_text("<html><body>Test</body></html>", encoding="utf-8")

        archiver.archive(url="https://example.com", item_id="test1")

        invocation = runner.get_last_invocation()
        assert invocation.archiver == "singlefile"

    def test_creates_html_file_extension(self, temp_env):
        """Test creates output.html file with correct extension."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("single-file", exit_code=0)

        archiver = SingleFileCLIArchiver(runner, settings)

        # Create dummy HTML file
        out_dir, out_path = archiver.get_output_path("test1")
        out_path.write_text("<html><body>SingleFile test</body></html>", encoding="utf-8")

        result = archiver.archive(url="https://example.com", item_id="test1")

        assert result.success
        assert result.saved_path.endswith(".html")
        assert out_path.exists()

    def test_archiver_name_property(self, temp_env):
        """Test archiver name is set correctly."""
        from core.config import get_settings

        archiver = SingleFileCLIArchiver(FakeCommandRunner(), get_settings())
        assert archiver.name == "singlefile"

    def test_empty_extra_flags(self, temp_env):
        """Test handles empty extra flags correctly."""
        from core.config import get_settings

        settings = get_settings()
        settings.singlefile_flags = ""  # Empty

        runner = FakeCommandRunner()
        runner.configure_result("single-file", exit_code=0)

        archiver = SingleFileCLIArchiver(runner, settings)
        out_dir, out_path = archiver.get_output_path("test1")
        out_path.write_text("<html><body>Test</body></html>", encoding="utf-8")

        result = archiver.archive(url="https://example.com", item_id="test1")

        # Should still work with default args
        assert result.success

    def test_with_storage_providers(self, temp_env, in_memory_file_storage):
        """Test archiving with storage provider integration."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("single-file", exit_code=0)

        archiver = SingleFileCLIArchiver(
            runner,
            settings,
            file_storage=[in_memory_file_storage]
        )

        # Create dummy HTML file
        out_dir, out_path = archiver.get_output_path("test1")
        out_path.write_text("<html><body>Storage test</body></html>", encoding="utf-8")

        result = archiver.archive_with_storage(url="https://example.com", item_id="test1")

        assert result.success
        assert 'storage_uploads' in result.metadata

    def test_with_database_storage(self, temp_env, in_memory_db_storage):
        """Test archiving with database storage integration."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("single-file", exit_code=0)

        archiver = SingleFileCLIArchiver(
            runner,
            settings,
            db_storage=in_memory_db_storage
        )

        # Create dummy HTML file
        out_dir, out_path = archiver.get_output_path("test1")
        out_path.write_text("<html><body>DB test</body></html>", encoding="utf-8")

        archiver.archive_with_storage(url="https://example.com", item_id="test1")

        # Should update database
        artifact = in_memory_db_storage.get_artifact("test1", "singlefile")
        assert artifact is not None

    def test_multiple_singlefile_generation(self, temp_env):
        """Test generating SingleFile archives for multiple URLs."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("single-file", exit_code=0)

        archiver = SingleFileCLIArchiver(runner, settings)

        urls = [
            ("https://example.com/page1", "test1"),
            ("https://example.com/page2", "test2"),
            ("https://example.com/page3", "test3")
        ]

        for url, item_id in urls:
            # Create dummy HTML file for each
            out_dir, out_path = archiver.get_output_path(item_id)
            out_path.write_text(f"<html><body>SingleFile: {url}</body></html>", encoding="utf-8")

            result = archiver.archive(url=url, item_id=item_id)
            assert result.success
            assert out_path.exists()