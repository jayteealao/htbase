"""
Tests for ScreenshotArchiver.

Tests screenshot archiver using FakeCommandRunner to avoid subprocess execution.
"""

from pathlib import Path

import pytest

from app.archivers.screenshot import ScreenshotArchiver
from tests.fakes.command_runner import FakeCommandRunner
from utils import assert_archive_result_success, assert_archive_result_failure


class TestScreenshotArchiver:
    """Test ScreenshotArchiver implementation."""

    def test_successful_screenshot_generation(self, temp_env):
        """Test successful screenshot generation."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("chromium.*--screenshot", exit_code=0)

        # Create dummy PNG file (since command is faked)
        archiver = ScreenshotArchiver(runner, settings)
        out_dir, out_path = archiver.get_output_path("test1")

        # Create minimal PNG header
        png_header = b'\x89PNG\r\n\x1a\n' + b'\x00\x00\x00\rIHDR' + b'\x00\x00\x00' * 5 + b'IDAT' + b'\x00\x00\x00\x00IEND\xaeB`\x82'
        out_path.write_bytes(png_header)

        result = archiver.archive(url="https://example.com", item_id="test1")

        assert result.success
        assert result.saved_path.endswith(".png")
        assert out_path.exists()

    def test_command_construction(self, temp_env):
        """Test screenshot command construction."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("chromium.*--screenshot", exit_code=0)

        archiver = ScreenshotArchiver(runner, settings)
        archiver.archive(url="https://example.com", item_id="test1")

        invocation = runner.get_last_invocation()

        # Should include Chromium screenshot arguments
        assert "chromium" in invocation.command
        assert "--screenshot" in invocation.command
        assert "--headless" in invocation.command
        assert "https://example.com" in invocation.command

    def test_includes_viewport_arguments(self, temp_env):
        """Test command includes viewport size arguments."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("chromium.*--screenshot", exit_code=0)

        archiver = ScreenshotArchiver(runner, settings)
        archiver.archive(url="https://example.com", item_id="test1")

        invocation = runner.get_last_invocation()

        # Should include default viewport dimensions
        assert "--window-size=1920,8000" in invocation.command

    def test_includes_output_path_argument(self, temp_env):
        """Test command includes output path argument."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("chromium.*--screenshot", exit_code=0)

        archiver = ScreenshotArchiver(runner, settings)
        out_dir, out_path = archiver.get_output_path("test1")

        archiver.archive(url="https://example.com", item_id="test1")

        invocation = runner.get_last_invocation()
        # Should include the output path
        assert str(out_path) in invocation.command

    def test_failure_with_nonzero_exit_code(self, temp_env):
        """Test handles failure with non-zero exit code."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("chromium.*--screenshot", exit_code=1)

        archiver = ScreenshotArchiver(runner, settings)
        result = archiver.archive(url="https://example.com", item_id="test1")

        assert_archive_result_failure(result, expected_exit_code=1)

    def test_timeout_handling(self, temp_env):
        """Test timeout handling and cleanup."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("chromium.*--screenshot", timed_out=True)

        archiver = ScreenshotArchiver(runner, settings)
        result = archiver.archive(url="https://example.com", item_id="test1")

        assert not result.success
        assert result.saved_path is None

    def test_timeout_cleanup_called(self, temp_env):
        """Test cleanup_after_timeout is called on timeout."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("chromium.*--screenshot", timed_out=True)

        archiver = ScreenshotArchiver(runner, settings)

        with patch.object(archiver, 'cleanup_after_timeout') as mock_cleanup:
            archiver.archive(url="https://example.com", item_id="test1")

            mock_cleanup.assert_called_once()

    def test_chromium_setup_and_cleanup(self, temp_env):
        """Test Chromium setup and cleanup are called."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("chromium.*--screenshot", exit_code=0)

        archiver = ScreenshotArchiver(runner, settings)

        # Create dummy PNG file
        out_dir, out_path = archiver.get_output_path("test1")
        png_header = b'\x89PNG\r\n\x1a\n' + b'IHDR' + b'IDAT' + b'IEND\xaeB`\x82'
        out_path.write_bytes(png_header)

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
        runner.configure_result("chromium.*--screenshot", exit_code=0)

        archiver = ScreenshotArchiver(runner, settings)

        # Create dummy PNG file
        out_dir, out_path = archiver.get_output_path("test1")
        png_header = b'\x89PNG\r\n\x1a\n' + b'IHDR' + b'IDAT' + b'IEND\xaeB`\x82'
        out_path.write_bytes(png_header)

        with patch.object(archiver, 'setup_chromium'), \
             patch.object(archiver, 'cleanup_chromium', side_effect=Exception("Cleanup failed")):

            result = archiver.archive(url="https://example.com", item_id="test1")

            # Should still succeed despite cleanup error
            assert result.success

    def test_default_viewport_dimensions(self, temp_env):
        """Test default viewport dimensions are set correctly."""
        from core.config import get_settings

        settings = get_settings()

        archiver = ScreenshotArchiver(FakeCommandRunner(), settings)

        assert archiver.viewport_width == 1920
        assert archiver.viewport_height == 8000

    def test_creates_output_directory(self, temp_env):
        """Test output directory is created."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("chromium.*--screenshot", exit_code=0)

        archiver = ScreenshotArchiver(runner, settings)
        out_dir, _ = archiver.get_output_path("test1")

        # Directory should be created by get_output_path
        assert out_dir.exists()
        assert out_dir.is_dir()

    def test_sanitizes_item_id_in_path(self, temp_env):
        """Test item_id is sanitized for file paths."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("chromium.*--screenshot", exit_code=0)

        archiver = ScreenshotArchiver(runner, settings)

        # Item ID with path traversal attempt
        archiver.archive(url="https://example.com", item_id="../../../etc/passwd")

        # Should be sanitized (no path traversal in command)
        invocation = runner.get_last_invocation()
        assert "../" not in invocation.command

    def test_url_quoting_in_command(self, temp_env):
        """Test URL is properly quoted in command."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("chromium.*--screenshot", exit_code=0)

        archiver = ScreenshotArchiver(runner, settings)

        # URL with special characters
        archiver.archive(url="https://example.com/path?query=value&foo=bar", item_id="test1")

        invocation = runner.get_last_invocation()
        # URL should be present in command
        assert "example.com" in invocation.command

    def test_timeout_value_passed_to_runner(self, temp_env):
        """Test timeout value is passed to command runner."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("chromium.*--screenshot", exit_code=0)

        archiver = ScreenshotArchiver(runner, settings)
        out_dir, out_path = archiver.get_output_path("test1")
        png_header = b'\x89PNG\r\n\x1a\n' + b'IHDR' + b'IDAT' + b'IEND\xaeB`\x82'
        out_path.write_bytes(png_header)

        archiver.archive(url="https://example.com", item_id="test1")

        invocation = runner.get_last_invocation()
        assert invocation.timeout == 300.0  # 5 minutes

    def test_archiver_name_passed_to_runner(self, temp_env):
        """Test archiver name is passed to command runner."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("chromium.*--screenshot", exit_code=0)

        archiver = ScreenshotArchiver(runner, settings)
        out_dir, out_path = archiver.get_output_path("test1")
        png_header = b'\x89PNG\r\n\x1a\n' + b'IHDR' + b'IDAT' + b'IEND\xaeB`\x82'
        out_path.write_bytes(png_header)

        archiver.archive(url="https://example.com", item_id="test1")

        invocation = runner.get_last_invocation()
        assert invocation.archiver == "screenshot"

    def test_creates_png_file_extension(self, temp_env):
        """Test creates output.png file with correct extension."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("chromium.*--screenshot", exit_code=0)

        archiver = ScreenshotArchiver(runner, settings)

        # Create dummy PNG file
        out_dir, out_path = archiver.get_output_path("test1")
        png_header = b'\x89PNG\r\n\x1a\n' + b'IHDR' + b'IDAT' + b'IEND\xaeB`\x82'
        out_path.write_bytes(png_header)

        result = archiver.archive(url="https://example.com", item_id="test1")

        assert result.success
        assert result.saved_path.endswith(".png")
        assert out_path.exists()

    def test_archiver_name_property(self, temp_env):
        """Test archiver name is set correctly."""
        from core.config import get_settings

        archiver = ScreenshotArchiver(FakeCommandRunner(), get_settings())
        assert archiver.name == "screenshot"

    def test_output_extension_property(self, temp_env):
        """Test output extension is PNG."""
        from core.config import get_settings

        archiver = ScreenshotArchiver(FakeCommandRunner(), get_settings())
        assert archiver.output_extension == "png"

    def test_with_storage_providers(self, temp_env, in_memory_file_storage):
        """Test archiving with storage provider integration."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("chromium.*--screenshot", exit_code=0)

        archiver = ScreenshotArchiver(
            runner,
            settings,
            file_storage=[in_memory_file_storage]
        )

        # Create dummy PNG file
        out_dir, out_path = archiver.get_output_path("test1")
        png_header = b'\x89PNG\r\n\x1a\n' + b'IHDR' + b'IDAT' + b'IEND\xaeB`\x82'
        out_path.write_bytes(png_header)

        result = archiver.archive_with_storage(url="https://example.com", item_id="test1")

        assert result.success
        assert 'storage_uploads' in result.metadata

    def test_with_database_storage(self, temp_env, in_memory_db_storage):
        """Test archiving with database storage integration."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("chromium.*--screenshot", exit_code=0)

        archiver = ScreenshotArchiver(
            runner,
            settings,
            db_storage=in_memory_db_storage
        )

        # Create dummy PNG file
        out_dir, out_path = archiver.get_output_path("test1")
        png_header = b'\x89PNG\r\n\x1a\n' + b'IHDR' + b'IDAT' + b'IEND\xaeB`\x82'
        out_path.write_bytes(png_header)

        archiver.archive_with_storage(url="https://example.com", item_id="test1")

        # Should update database
        artifact = in_memory_db_storage.get_artifact("test1", "screenshot")
        assert artifact is not None

    def test_multiple_screenshot_generation(self, temp_env):
        """Test generating screenshots for multiple URLs."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("chromium.*--screenshot", exit_code=0)

        archiver = ScreenshotArchiver(runner, settings)

        urls = [
            ("https://example.com/page1", "test1"),
            ("https://example.com/page2", "test2"),
            ("https://example.com/page3", "test3")
        ]

        for url, item_id in urls:
            # Create dummy PNG file for each
            out_dir, out_path = archiver.get_output_path(item_id)
            png_header = b'\x89PNG\r\n\x1a\n' + f'IHDR{item_id}'.encode() + b'IDAT' + b'IEND\xaeB`\x82'
            out_path.write_bytes(png_header)

            result = archiver.archive(url=url, item_id=item_id)
            assert result.success
            assert out_path.exists()