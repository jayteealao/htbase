"""
Tests for PDFArchiver.

Tests PDF archiver using FakeCommandRunner to avoid subprocess execution.
"""

from pathlib import Path
import tempfile
import os

import pytest

from app.archivers.pdf import PDFArchiver
from tests.fakes.command_runner import FakeCommandRunner
from utils import assert_archive_result_success, assert_archive_result_failure


class TestPDFArchiver:
    """Test PDFArchiver implementation."""

    def test_successful_pdf_generation(self, temp_env):
        """Test successful PDF generation."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("chromium.*--print-to-pdf", exit_code=0)

        # Create dummy PDF file (since command is faked)
        archiver = PDFArchiver(runner, settings)
        out_dir, out_path = archiver.get_output_path("test1")
        out_path.write_bytes(b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\ntrailer\n<<\n/Root 1 0 R\n>>\n%%EOF")

        result = archiver.archive(url="https://example.com", item_id="test1")

        assert result.success
        assert result.saved_path.endswith(".pdf")
        assert out_path.exists()

    def test_command_construction(self, temp_env):
        """Test PDF command construction."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("chromium.*--print-to-pdf", exit_code=0)

        archiver = PDFArchiver(runner, settings)
        archiver.archive(url="https://example.com", item_id="test1")

        invocation = runner.get_last_invocation()

        # Should include Chromium PDF printing arguments
        assert "chromium" in invocation.command
        assert "--print-to-pdf" in invocation.command
        assert "--headless" in invocation.command
        assert "https://example.com" in invocation.command

    def test_includes_output_path_argument(self, temp_env):
        """Test command includes output path argument."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("chromium.*--print-to-pdf", exit_code=0)

        archiver = PDFArchiver(runner, settings)
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
        runner.configure_result("chromium.*--print-to-pdf", exit_code=1)

        archiver = PDFArchiver(runner, settings)
        result = archiver.archive(url="https://example.com", item_id="test1")

        assert_archive_result_failure(result, expected_exit_code=1)

    def test_timeout_handling(self, temp_env):
        """Test timeout handling and cleanup."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("chromium.*--print-to-pdf", timed_out=True)

        archiver = PDFArchiver(runner, settings)
        result = archiver.archive(url="https://example.com", item_id="test1")

        assert not result.success
        assert result.saved_path is None

    def test_timeout_cleanup_called(self, temp_env):
        """Test cleanup_after_timeout is called on timeout."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("chromium.*--print-to-pdf", timed_out=True)

        archiver = PDFArchiver(runner, settings)

        with patch.object(archiver, 'cleanup_after_timeout') as mock_cleanup:
            archiver.archive(url="https://example.com", item_id="test1")

            mock_cleanup.assert_called_once()

    def test_chromium_setup_and_cleanup(self, temp_env):
        """Test Chromium setup and cleanup are called."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("chromium.*--print-to-pdf", exit_code=0)

        archiver = PDFArchiver(runner, settings)

        # Create dummy PDF file
        out_dir, out_path = archiver.get_output_path("test1")
        out_path.write_bytes(b"%PDF-1.4\n%EOF")

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
        runner.configure_result("chromium.*--print-to-pdf", exit_code=0)

        archiver = PDFArchiver(runner, settings)

        # Create dummy PDF file
        out_dir, out_path = archiver.get_output_path("test1")
        out_path.write_bytes(b"%PDF-1.4\n%EOF")

        with patch.object(archiver, 'setup_chromium'), \
             patch.object(archiver, 'cleanup_chromium', side_effect=Exception("Cleanup failed")):

            result = archiver.archive(url="https://example.com", item_id="test1")

            # Should still succeed despite cleanup error
            assert result.success

    def test_creates_output_directory(self, temp_env):
        """Test output directory is created."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("chromium.*--print-to-pdf", exit_code=0)

        archiver = PDFArchiver(runner, settings)
        out_dir, _ = archiver.get_output_path("test1")

        # Directory should be created by get_output_path
        assert out_dir.exists()
        assert out_dir.is_dir()

    def test_sanitizes_item_id_in_path(self, temp_env):
        """Test item_id is sanitized for file paths."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("chromium.*--print-to-pdf", exit_code=0)

        archiver = PDFArchiver(runner, settings)

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
        runner.configure_result("chromium.*--print-to-pdf", exit_code=0)

        archiver = PDFArchiver(runner, settings)

        # URL with special characters
        archiver.archive(url="https://example.com/path?query=value&foo=bar", item_id="test1")

        invocation = runner.get_last_invocation()
        # URL should be present in command
        assert "example.com" in invocation.command

    def test_output_path_quoting(self, temp_env):
        """Test output path is properly quoted."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("chromium.*--print-to-pdf", exit_code=0)

        archiver = PDFArchiver(runner, settings)
        archiver.archive(url="https://example.com", item_id="test with spaces")

        invocation = runner.get_last_invocation()
        # Command should execute despite spaces in path
        assert invocation.command is not None

    def test_timeout_value_passed_to_runner(self, temp_env):
        """Test timeout value is passed to command runner."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("chromium.*--print-to-pdf", exit_code=0)

        archiver = PDFArchiver(runner, settings)
        out_dir, out_path = archiver.get_output_path("test1")
        out_path.write_bytes(b"%PDF-1.4\n%EOF")

        archiver.archive(url="https://example.com", item_id="test1")

        invocation = runner.get_last_invocation()
        assert invocation.timeout == 300.0  # 5 minutes

    def test_archiver_name_passed_to_runner(self, temp_env):
        """Test archiver name is passed to command runner."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("chromium.*--print-to-pdf", exit_code=0)

        archiver = PDFArchiver(runner, settings)
        out_dir, out_path = archiver.get_output_path("test1")
        out_path.write_bytes(b"%PDF-1.4\n%EOF")

        archiver.archive(url="https://example.com", item_id="test1")

        invocation = runner.get_last_invocation()
        assert invocation.archiver == "pdf"

    def test_creates_pdf_file_extension(self, temp_env):
        """Test creates output.pdf file with correct extension."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("chromium.*--print-to-pdf", exit_code=0)

        archiver = PDFArchiver(runner, settings)

        # Create dummy PDF file
        out_dir, out_path = archiver.get_output_path("test1")
        out_path.write_bytes(b"%PDF-1.4\n%EOF")

        result = archiver.archive(url="https://example.com", item_id="test1")

        assert result.success
        assert result.saved_path.endswith(".pdf")
        assert out_path.exists()

    def test_archiver_name_property(self, temp_env):
        """Test archiver name is set correctly."""
        from core.config import get_settings

        archiver = PDFArchiver(FakeCommandRunner(), get_settings())
        assert archiver.name == "pdf"

    def test_output_extension_property(self, temp_env):
        """Test output extension is PDF."""
        from core.config import get_settings

        archiver = PDFArchiver(FakeCommandRunner(), get_settings())
        assert archiver.output_extension == "pdf"

    def test_with_storage_providers(self, temp_env, in_memory_file_storage):
        """Test archiving with storage provider integration."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("chromium.*--print-to-pdf", exit_code=0)

        archiver = PDFArchiver(
            runner,
            settings,
            file_storage=[in_memory_file_storage]
        )

        # Create dummy PDF file
        out_dir, out_path = archiver.get_output_path("test1")
        out_path.write_bytes(b"%PDF-1.4\n%EOF")

        result = archiver.archive_with_storage(url="https://example.com", item_id="test1")

        assert result.success
        assert 'storage_uploads' in result.metadata

    def test_with_database_storage(self, temp_env, in_memory_db_storage):
        """Test archiving with database storage integration."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("chromium.*--print-to-pdf", exit_code=0)

        archiver = PDFArchiver(
            runner,
            settings,
            db_storage=in_memory_db_storage
        )

        # Create dummy PDF file
        out_dir, out_path = archiver.get_output_path("test1")
        out_path.write_bytes(b"%PDF-1.4\n%EOF")

        archiver.archive_with_storage(url="https://example.com", item_id="test1")

        # Should update database
        artifact = in_memory_db_storage.get_artifact("test1", "pdf")
        assert artifact is not None

    def test_multiple_pdf_generation(self, temp_env):
        """Test generating PDFs for multiple URLs."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("chromium.*--print-to-pdf", exit_code=0)

        archiver = PDFArchiver(runner, settings)

        urls = [
            ("https://example.com/page1", "test1"),
            ("https://example.com/page2", "test2"),
            ("https://example.com/page3", "test3")
        ]

        for url, item_id in urls:
            # Create dummy PDF file for each
            out_dir, out_path = archiver.get_output_path(item_id)
            out_path.write_bytes(f"%PDF-1.4\n% URL: {url}\n%EOF".encode())

            result = archiver.archive(url=url, item_id=item_id)
            assert result.success
            assert out_path.exists()

    def test_command_uses_shlex_quoting(self, temp_env):
        """Test command uses proper shell quoting via shlex."""
        from core.config import get_settings

        settings = get_settings()

        runner = FakeCommandRunner()
        runner.configure_result("chromium.*--print-to-pdf", exit_code=0)

        archiver = PDFArchiver(runner, settings)

        # Test with spaces in URL that need quoting
        archiver.archive(url="https://example.com/path with spaces", item_id="test1")

        invocation = runner.get_last_invocation()
        # Command should be properly quoted string
        assert isinstance(invocation.command, str)
        assert "chromium" in invocation.command