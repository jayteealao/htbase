"""
Tests for ReadabilityArchiver.

Tests readability archiver using FakeCommandRunner and mocked HTTP requests to avoid external dependencies.
"""

from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import json

import pytest

from app.archivers.readability import ReadabilityArchiver
from tests.fakes.command_runner import FakeCommandRunner
from utils import assert_archive_result_success, assert_archive_result_failure


class TestReadabilityArchiver:
    """Test ReadabilityArchiver implementation."""

    def test_successful_archive_with_chromium(self, temp_env):
        """Test successful archiving with Chromium DOM dumping."""
        from core.config import get_settings

        settings = get_settings()
        settings.use_chromium = True  # Enable Chromium

        runner = FakeCommandRunner()
        runner.configure_result("chromium.*dump-dom", exit_code=0, stdout="<html><body>Test content</body></html>")

        archiver = ReadabilityArchiver(runner, settings)
        result = archiver.archive(url="https://example.com", item_id="test1")

        assert result.success
        assert result.saved_path.endswith(".html")
        assert Path(result.saved_path).exists()

    def test_successful_archive_with_http_fallback(self, temp_env):
        """Test successful archiving with HTTP fallback when Chromium fails."""
        from core.config import get_settings

        settings = get_settings()
        settings.use_chromium = True

        runner = FakeCommandRunner()
        runner.configure_result("chromium.*dump-dom", exit_code=1)  # Chromium fails

        # Mock successful HTTP request
        mock_response = Mock()
        mock_response.text = "<html><head><title>Test Article</title></head><body><article>Test content</article></body></html>"
        mock_response.raise_for_status.return_value = None

        with patch('requests.get', return_value=mock_response):
            archiver = ReadabilityArchiver(runner, settings)
            result = archiver.archive(url="https://example.com", item_id="test1")

            assert result.success
            assert result.saved_path.endswith(".html")

    def test_chromium_disabled_uses_http(self, temp_env):
        """Test that HTTP is used when Chromium is disabled."""
        from core.config import get_settings

        settings = get_settings()
        settings.use_chromium = False  # Disable Chromium

        runner = FakeCommandRunner()

        # Mock successful HTTP request
        mock_response = Mock()
        mock_response.text = "<html><head><title>Test</title></head><body><p>Article content</p></body></html>"
        mock_response.raise_for_status.return_value = None

        with patch('requests.get', return_value=mock_response):
            archiver = ReadabilityArchiver(runner, settings)
            result = archiver.archive(url="https://example.com", item_id="test1")

            assert result.success
            # Should not have called Chromium
            assert runner.get_invocation_count() == 0

    def test_failure_no_html_content(self, temp_env):
        """Test failure when no HTML content can be obtained."""
        from core.config import get_settings

        settings = get_settings()
        settings.use_chromium = False

        runner = FakeCommandRunner()

        # Mock HTTP request failure
        with patch('requests.get', side_effect=Exception("Network error")):
            archiver = ReadabilityArchiver(runner, settings)
            result = archiver.archive(url="https://example.com", item_id="test1")

            assert not result.success
            assert result.exit_code == 1
            assert result.saved_path is None

    def test_failure_readability_not_available(self, temp_env):
        """Test failure when readability library is not available."""
        from core.config import get_settings

        settings = get_settings()
        settings.use_chromium = False

        runner = FakeCommandRunner()

        # Mock successful HTTP but readability import fails
        mock_response = Mock()
        mock_response.text = "<html><body>Test</body></html>"
        mock_response.raise_for_status.return_value = None

        with patch('requests.get', return_value=mock_response), \
             patch('archivers.readability.Document', side_effect=ImportError("No module named 'readability'")):

            archiver = ReadabilityArchiver(runner, settings)
            result = archiver.archive(url="https://example.com", item_id="test1")

            assert not result.success
            assert result.exit_code == 127  # Command not found equivalent

    def test_metadata_extraction_success(self, temp_env):
        """Test successful metadata extraction from HTML."""
        from core.config import get_settings

        settings = get_settings()
        settings.use_chromium = False

        runner = FakeCommandRunner()

        # Mock HTML with rich metadata
        html_content = """
        <html lang="en">
        <head>
            <title>Test Article Title</title>
            <meta name="author" content="John Doe">
            <meta property="og:site_name" content="Example Site">
            <meta name="description" content="Article description">
            <meta property="article:published_time" content="2023-01-01T00:00:00Z">
            <link rel="canonical" href="https://example.com/canonical">
            <meta property="og:image" content="https://example.com/image.jpg">
            <link rel="icon" href="https://example.com/favicon.ico">
            <meta name="keywords" content="tag1, tag2, tag3">
        </head>
        <body>
            <article>
                <p>This is a test article with some content for readability extraction.</p>
                <p>It has multiple paragraphs to test word counting.</p>
            </article>
        </body>
        </html>
        """

        mock_response = Mock()
        mock_response.text = html_content
        mock_response.raise_for_status.return_value = None

        with patch('requests.get', return_value=mock_response):
            archiver = ReadabilityArchiver(runner, settings)
            result = archiver.archive(url="https://example.com", item_id="test1")

            assert result.success

            # Check metadata was extracted
            assert result.metadata is not None
            assert result.metadata.get('title') == "Test Article Title"
            assert result.metadata.get('byline') == "John Doe"
            assert result.metadata.get('site_name') == "Example Site"
            assert result.metadata.get('description') == "Article description"
            assert result.metadata.get('language') == "en"
            assert result.metadata.get('canonical_url') == "https://example.com/canonical"
            assert result.metadata.get('top_image') == "https://example.com/image.jpg"
            assert result.metadata.get('favicon') == "https://example.com/favicon.ico"
            assert "tag1" in result.metadata.get('keywords', [])
            assert "tag2" in result.metadata.get('keywords', [])
            assert "tag3" in result.metadata.get('keywords', [])

    def test_creates_metadata_json_file(self, temp_env):
        """Test that metadata JSON file is created alongside HTML."""
        from core.config import get_settings

        settings = get_settings()
        settings.use_chromium = False

        runner = FakeCommandRunner()

        mock_response = Mock()
        mock_response.text = "<html><head><title>Test</title></head><body><p>Content</p></body></html>"
        mock_response.raise_for_status.return_value = None

        with patch('requests.get', return_value=mock_response):
            archiver = ReadabilityArchiver(runner, settings)
            result = archiver.archive(url="https://example.com", item_id="test1")

            assert result.success

            # Check metadata JSON file exists
            out_dir, _ = archiver.get_output_path("test1")
            meta_path = out_dir / "output.json"
            assert meta_path.exists()

            # Check metadata content
            with open(meta_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            assert 'title' in metadata
            assert 'source_url' in metadata

    def test_word_count_and_reading_time(self, temp_env):
        """Test word count and reading time calculation."""
        from core.config import get_settings

        settings = get_settings()
        settings.use_chromium = False

        runner = FakeCommandRunner()

        # Create HTML with known word count
        words = "word " * 50  # 50 words
        html_content = f"<html><body><article><p>{words}</p></article></body></html>"

        mock_response = Mock()
        mock_response.text = html_content
        mock_response.raise_for_status.return_value = None

        with patch('requests.get', return_value=mock_response):
            archiver = ReadabilityArchiver(runner, settings)
            result = archiver.archive(url="https://example.com", item_id="test1")

            assert result.success
            assert result.metadata.get('word_count') == 50
            # Reading time should be word_count / 200, rounded to 2 decimal places
            assert result.metadata.get('reading_time_minutes') == round(50 / 200.0, 2)

    def test_handles_malformed_html(self, temp_env):
        """Test handling of malformed HTML content."""
        from core.config import get_settings

        settings = get_settings()
        settings.use_chromium = False

        runner = FakeCommandRunner()

        # Malformed HTML
        mock_response = Mock()
        mock_response.text = "<html><body><p>Unclosed paragraph"
        mock_response.raise_for_status.return_value = None

        with patch('requests.get', return_value=mock_response):
            archiver = ReadabilityArchiver(runner, settings)
            result = archiver.archive(url="https://example.com", item_id="test1")

            # Should still succeed, readability can handle malformed HTML
            assert result.success

    def test_chromium_timeout_fallback_to_http(self, temp_env):
        """Test fallback to HTTP when Chromium times out."""
        from core.config import get_settings

        settings = get_settings()
        settings.use_chromium = True

        runner = FakeCommandRunner()
        runner.configure_result("chromium.*dump-dom", timed_out=True)  # Chromium times out

        # Mock successful HTTP fallback
        mock_response = Mock()
        mock_response.text = "<html><body>Fallback content</body></html>"
        mock_response.raise_for_status.return_value = None

        with patch('requests.get', return_value=mock_response):
            archiver = ReadabilityArchiver(runner, settings)
            result = archiver.archive(url="https://example.com", item_id="test1")

            assert result.success

    def test_http_request_with_custom_headers(self, temp_env):
        """Test that HTTP requests include proper User-Agent header."""
        from core.config import get_settings

        settings = get_settings()
        settings.use_chromium = False

        runner = FakeCommandRunner()

        mock_response = Mock()
        mock_response.text = "<html><body>Test</body></html>"
        mock_response.raise_for_status.return_value = None

        with patch('requests.get', return_value=mock_response) as mock_get:
            archiver = ReadabilityArchiver(runner, settings)
            result = archiver.archive(url="https://example.com", item_id="test1")

            assert result.success

            # Check that proper headers were used
            call_args = mock_get.call_args
            headers = call_args[1]['headers']
            assert 'User-Agent' in headers
            assert 'Chrome' in headers['User-Agent']

    def test_http_request_timeout(self, temp_env):
        """Test handling of HTTP request timeout."""
        from core.config import get_settings

        settings = get_settings()
        settings.use_chromium = False

        runner = FakeCommandRunner()

        # Mock HTTP timeout
        with patch('requests.get', side_effect=Exception("Request timeout")):
            archiver = ReadabilityArchiver(runner, settings)
            result = archiver.archive(url="https://example.com", item_id="test1")

            assert not result.success
            assert result.exit_code == 1

    def test_empty_html_content(self, temp_env):
        """Test handling of empty HTML content."""
        from core.config import get_settings

        settings = get_settings()
        settings.use_chromium = False

        runner = FakeCommandRunner()

        # Mock empty response
        mock_response = Mock()
        mock_response.text = ""
        mock_response.raise_for_status.return_value = None

        with patch('requests.get', return_value=mock_response):
            archiver = ReadabilityArchiver(runner, settings)
            result = archiver.archive(url="https://example.com", item_id="test1")

            # Readability should handle empty content
            assert not result.success  # Likely to fail with empty content

    def test_minimal_html_wrapper(self, temp_env):
        """Test that output includes minimal HTML wrapper."""
        from core.config import get_settings

        settings = get_settings()
        settings.use_chromium = False

        runner = FakeCommandRunner()

        mock_response = Mock()
        mock_response.text = "<html><head><title>Test Title</title></head><body><article>Content</article></body></html>"
        mock_response.raise_for_status.return_value = None

        with patch('requests.get', return_value=mock_response):
            archiver = ReadabilityArchiver(runner, settings)
            result = archiver.archive(url="https://example.com", item_id="test1")

            assert result.success

            # Check output has proper HTML structure
            output_path = Path(result.saved_path)
            content = output_path.read_text(encoding='utf-8')
            assert '<!DOCTYPE html>' in content
            assert '<html><head><meta charset="utf-8">' in content
            assert '<title>Test Title</title>' in content
            assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in content
            assert '<body>' in content
            assert '</body></html>' in content

    def test_archiver_name_property(self, temp_env):
        """Test archiver name is set correctly."""
        from core.config import get_settings

        archiver = ReadabilityArchiver(FakeCommandRunner(), get_settings())
        assert archiver.name == "readability"

    def test_output_extension_property(self, temp_env):
        """Test output extension is HTML."""
        from core.config import get_settings

        archiver = ReadabilityArchiver(FakeCommandRunner(), get_settings())
        assert archiver.output_extension == "html"

    def test_with_storage_providers(self, temp_env, in_memory_file_storage):
        """Test archiving with storage provider integration."""
        from core.config import get_settings

        settings = get_settings()
        settings.use_chromium = False

        runner = FakeCommandRunner()

        mock_response = Mock()
        mock_response.text = "<html><head><title>Test</title></head><body><p>Storage test</p></body></html>"
        mock_response.raise_for_status.return_value = None

        with patch('requests.get', return_value=mock_response):
            archiver = ReadabilityArchiver(
                runner,
                settings,
                file_storage=[in_memory_file_storage]
            )
            result = archiver.archive_with_storage(url="https://example.com", item_id="test1")

            assert result.success
            assert 'storage_uploads' in result.metadata

    def test_with_database_storage(self, temp_env, in_memory_db_storage):
        """Test archiving with database storage integration."""
        from core.config import get_settings

        settings = get_settings()
        settings.use_chromium = False

        runner = FakeCommandRunner()

        mock_response = Mock()
        mock_response.text = "<html><head><title>DB Test</title></head><body><p>Database test</p></body></html>"
        mock_response.raise_for_status.return_value = None

        with patch('requests.get', return_value=mock_response):
            archiver = ReadabilityArchiver(
                runner,
                settings,
                db_storage=in_memory_db_storage
            )
            archiver.archive_with_storage(url="https://example.com", item_id="test1")

            # Should update database with metadata
            artifact = in_memory_db_storage.get_artifact("test1", "readability")
            assert artifact is not None

    def test_chromium_setup_and_cleanup_called(self, temp_env):
        """Test that Chromium setup and cleanup are called when using Chromium."""
        from core.config import get_settings

        settings = get_settings()
        settings.use_chromium = True

        runner = FakeCommandRunner()
        runner.configure_result("chromium.*dump-dom", exit_code=0, stdout="<html><body>Test</body></html>")

        archiver = ReadabilityArchiver(runner, settings)

        # Mock setup and cleanup methods
        with patch.object(archiver, 'setup_chromium') as mock_setup, \
             patch.object(archiver, 'cleanup_chromium') as mock_cleanup:

            result = archiver.archive(url="https://example.com", item_id="test1")

            assert result.success
            mock_setup.assert_called_once()
            mock_cleanup.assert_called_once()

    def test_error_during_chromium_cleanup(self, temp_env):
        """Test that archive succeeds even if Chromium cleanup fails."""
        from core.config import get_settings

        settings = get_settings()
        settings.use_chromium = True

        runner = FakeCommandRunner()
        runner.configure_result("chromium.*dump-dom", exit_code=0, stdout="<html><body>Test</body></html>")

        archiver = ReadabilityArchiver(runner, settings)

        # Mock cleanup to raise exception
        with patch.object(archiver, 'setup_chromium'), \
             patch.object(archiver, 'cleanup_chromium', side_effect=Exception("Cleanup failed")):

            result = archiver.archive(url="https://example.com", item_id="test1")

            # Should still succeed despite cleanup error
            assert result.success

    def test_multiple_archives_different_urls(self, temp_env):
        """Test archiving multiple different URLs."""
        from core.config import get_settings

        settings = get_settings()
        settings.use_chromium = False

        runner = FakeCommandRunner()

        urls = [
            ("https://example.com/article1", "test1", "<html><title>Article 1</title><body>Content 1</body></html>"),
            ("https://example.com/article2", "test2", "<html><title>Article 2</title><body>Content 2</body></html>"),
            ("https://example.com/article3", "test3", "<html><title>Article 3</title><body>Content 3</body></html>")
        ]

        for url, item_id, html in urls:
            mock_response = Mock()
            mock_response.text = html
            mock_response.raise_for_status.return_value = None

            with patch('requests.get', return_value=mock_response):
                archiver = ReadabilityArchiver(runner, settings)
                result = archiver.archive(url=url, item_id=item_id)

                assert result.success
                assert result.metadata.get('title') == f"Article {item_id[-1]}"

    def test_preserves_encoding(self, temp_env):
        """Test that HTML encoding is preserved in output."""
        from core.config import get_settings

        settings = get_settings()
        settings.use_chromium = False

        runner = FakeCommandRunner()

        # HTML with Unicode content
        html_content = "<html><head><title>Test: Café résumé</title></head><body><p>Unicode: 🌟</p></body></html>"

        mock_response = Mock()
        mock_response.text = html_content
        mock_response.raise_for_status.return_value = None

        with patch('requests.get', return_value=mock_response):
            archiver = ReadabilityArchiver(runner, settings)
            result = archiver.archive(url="https://example.com", item_id="test1")

            assert result.success

            # Check Unicode content is preserved
            output_path = Path(result.saved_path)
            content = output_path.read_text(encoding='utf-8')
            assert 'Café résumé' in content
            assert '🌟' in content