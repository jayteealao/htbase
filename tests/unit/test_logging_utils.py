"""
Unit tests for logging utilities (URL sanitization).
"""

import pytest

from shared.logging_utils import (
    sanitize_error_message,
    sanitize_url_for_logging,
    safe_url,
)


class TestSanitizeUrlForLogging:
    """Test URL sanitization for safe logging."""

    def test_redacts_api_key(self):
        """Should redact api_key parameter."""
        url = "https://api.example.com/data?api_key=sk-secret123"
        result = sanitize_url_for_logging(url)

        assert "sk-secret123" not in result
        assert "api_key=***REDACTED***" in result
        assert "https://api.example.com/data" in result

    def test_redacts_token(self):
        """Should redact token parameter."""
        url = "https://example.com/api?token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        result = sanitize_url_for_logging(url)

        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result
        assert "token=***REDACTED***" in result

    def test_redacts_password(self):
        """Should redact password parameter."""
        url = "https://example.com/login?username=user&password=hunter2"
        result = sanitize_url_for_logging(url)

        assert "hunter2" not in result
        assert "password=***REDACTED***" in result
        assert "username=user" in result  # Non-sensitive preserved

    def test_preserves_safe_parameters(self):
        """Should preserve non-sensitive query parameters."""
        url = "https://example.com?foo=bar&token=secret&baz=qux"
        result = sanitize_url_for_logging(url)

        assert "foo=bar" in result
        assert "baz=qux" in result
        assert "secret" not in result

    def test_case_insensitive_parameter_names(self):
        """Should redact parameters regardless of case."""
        url = "https://example.com?API_KEY=secret1&Token=secret2&PASSWORD=secret3"
        result = sanitize_url_for_logging(url)

        assert "secret1" not in result
        assert "secret2" not in result
        assert "secret3" not in result
        assert "API_KEY=***REDACTED***" in result

    def test_strips_userinfo(self):
        """Should strip username:password from URL."""
        url = "https://user:password@example.com/path"
        result = sanitize_url_for_logging(url)

        assert "user" not in result
        assert "password" not in result
        assert "example.com" in result
        assert "https://" in result

    def test_strips_fragment(self):
        """Should strip URL fragment for security."""
        url = "https://example.com/path?foo=bar#fragment"
        result = sanitize_url_for_logging(url)

        assert "#fragment" not in result
        assert "foo=bar" in result

    def test_redacts_multiple_sensitive_params(self):
        """Should redact multiple sensitive parameters."""
        url = "https://example.com?api_key=key1&token=tok1&secret=sec1&foo=bar"
        result = sanitize_url_for_logging(url)

        assert "key1" not in result
        assert "tok1" not in result
        assert "sec1" not in result
        assert "api_key=***REDACTED***" in result
        assert "token=***REDACTED***" in result
        assert "secret=***REDACTED***" in result
        assert "foo=bar" in result

    def test_custom_sensitive_params(self):
        """Should redact custom sensitive parameter names."""
        url = "https://example.com?custom_auth=secret123&foo=bar"
        result = sanitize_url_for_logging(
            url, sensitive_params={"custom_auth"}
        )

        assert "secret123" not in result
        assert "custom_auth=***REDACTED***" in result
        assert "foo=bar" in result

    def test_redact_all_query_params(self):
        """Should redact all query params in paranoid mode."""
        url = "https://example.com/path?foo=bar&baz=qux"
        result = sanitize_url_for_logging(url, redact_all_query_params=True)

        assert result == "https://example.com/path"
        assert "foo" not in result
        assert "bar" not in result

    def test_custom_replacement_string(self):
        """Should use custom replacement string."""
        url = "https://example.com?api_key=secret"
        result = sanitize_url_for_logging(url, replacement="[HIDDEN]")

        assert "api_key=[HIDDEN]" in result
        assert "secret" not in result

    def test_url_without_query_params(self):
        """Should handle URL without query parameters."""
        url = "https://example.com/path"
        result = sanitize_url_for_logging(url)

        assert result == url

    def test_url_with_empty_query_params(self):
        """Should handle URL with empty query string."""
        url = "https://example.com/path?"
        result = sanitize_url_for_logging(url)

        # Should preserve basic structure
        assert "https://example.com/path" in result

    def test_multiple_values_for_same_param(self):
        """Should redact all values for sensitive parameter with multiple values."""
        # URL with multiple values: ?key=val1&key=val2
        url = "https://example.com?api_key=secret1&api_key=secret2&foo=bar"
        result = sanitize_url_for_logging(url)

        assert "secret1" not in result
        assert "secret2" not in result
        assert "api_key=***REDACTED***" in result
        assert "foo=bar" in result

    def test_invalid_url_returns_safe_placeholder(self):
        """Should return safe placeholder for invalid URLs."""
        invalid_url = "not a valid URL at all"
        result = sanitize_url_for_logging(invalid_url)

        # Should not crash, return safe placeholder
        assert "REDACTED" in result or result == invalid_url

    def test_common_oauth_params(self):
        """Should redact common OAuth parameters."""
        url = "https://auth.example.com?code=abc123&state=xyz&client_id=app123"
        result = sanitize_url_for_logging(url)

        assert "abc123" not in result
        assert "xyz" not in result
        assert "app123" not in result


class TestSanitizeErrorMessage:
    """Test sanitization of error messages containing URLs."""

    def test_sanitizes_url_in_error_message(self):
        """Should sanitize URLs found in error messages."""
        message = "Failed to fetch https://api.example.com/data?token=secret123"
        result = sanitize_error_message(message)

        assert "secret123" not in result
        assert "token=***REDACTED***" in result
        assert "Failed to fetch" in result

    def test_sanitizes_multiple_urls(self):
        """Should sanitize multiple URLs in message."""
        message = (
            "Error fetching https://api1.example.com?api_key=key1 "
            "or https://api2.example.com?token=tok1"
        )
        result = sanitize_error_message(message)

        assert "key1" not in result
        assert "tok1" not in result
        assert "api_key=***REDACTED***" in result
        assert "token=***REDACTED***" in result

    def test_preserves_text_without_urls(self):
        """Should preserve text that doesn't contain URLs."""
        message = "An error occurred while processing the request"
        result = sanitize_error_message(message)

        assert result == message

    def test_handles_http_and_https(self):
        """Should handle both HTTP and HTTPS URLs."""
        message = "Error: http://example.com?password=pw1 and https://example.com?secret=s1"
        result = sanitize_error_message(message)

        assert "pw1" not in result
        assert "s1" not in result


class TestSafeUrl:
    """Test convenience function."""

    def test_safe_url_is_shorthand(self):
        """safe_url() should be shorthand for sanitize_url_for_logging()."""
        url = "https://example.com?api_key=secret"
        result1 = safe_url(url)
        result2 = sanitize_url_for_logging(url)

        assert result1 == result2

    def test_safe_url_redacts_sensitive_params(self):
        """safe_url() should redact sensitive parameters."""
        url = "https://example.com?token=secret123"
        result = safe_url(url)

        assert "secret123" not in result
        assert "token=***REDACTED***" in result


class TestEdgeCases:
    """Test edge cases and security scenarios."""

    def test_handles_encoded_params(self):
        """Should handle URL-encoded parameter values."""
        url = "https://example.com?api_key=sk%2D1234567890"
        result = sanitize_url_for_logging(url)

        # Should redact the encoded value
        assert "sk%2D1234567890" not in result or "***REDACTED***" in result

    def test_handles_unicode_urls(self):
        """Should handle URLs with unicode characters."""
        url = "https://example.com/über?api_key=secret"
        result = sanitize_url_for_logging(url)

        assert "secret" not in result

    def test_preserves_port_numbers(self):
        """Should preserve port numbers in URL."""
        url = "https://example.com:8080/path?api_key=secret"
        result = sanitize_url_for_logging(url)

        assert ":8080" in result
        assert "secret" not in result

    def test_handles_ipv4_addresses(self):
        """Should handle IPv4 addresses."""
        url = "https://192.168.1.1/path?token=secret"
        result = sanitize_url_for_logging(url)

        assert "192.168.1.1" in result
        assert "secret" not in result

    def test_handles_localhost(self):
        """Should handle localhost URLs."""
        url = "http://localhost:3000/api?api_key=dev_key_123"
        result = sanitize_url_for_logging(url)

        assert "localhost" in result
        assert "dev_key_123" not in result
