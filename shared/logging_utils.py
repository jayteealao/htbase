"""
Logging utilities for HTBase.

Provides safe logging helpers that prevent sensitive data exposure.
"""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


# Parameters that commonly contain sensitive data
SENSITIVE_PARAMS = {
    # API keys and tokens
    "api_key",
    "apikey",
    "api-key",
    "token",
    "access_token",
    "refresh_token",
    "auth_token",
    "bearer",
    "authorization",
    # Passwords and secrets
    "password",
    "passwd",
    "pwd",
    "secret",
    "client_secret",
    # Session identifiers
    "session",
    "sessionid",
    "session_id",
    "sid",
    # Authentication codes
    "code",
    "auth_code",
    "verification_code",
    # OAuth
    "client_id",
    "state",
    "nonce",
    # Other sensitive
    "key",
    "signature",
    "sig",
}


def sanitize_url_for_logging(
    url: str,
    *,
    sensitive_params: Optional[set[str]] = None,
    redact_all_query_params: bool = False,
    replacement: str = "***REDACTED***",
) -> str:
    """Sanitize URL for safe logging by redacting sensitive query parameters.

    Security Issue: URLs may contain sensitive data in query parameters:
    - API keys: ?api_key=sk-1234567890
    - Tokens: ?token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
    - Passwords: ?password=hunter2
    - Session IDs: ?session_id=abc123

    Logging raw URLs can expose these secrets in log files, monitoring systems,
    and error tracking services.

    This function redacts sensitive parameters while preserving the URL structure
    for debugging purposes.

    Args:
        url: The URL to sanitize
        sensitive_params: Additional parameter names to redact (case-insensitive).
                         If None, uses default SENSITIVE_PARAMS set.
        redact_all_query_params: If True, redact ALL query parameters (paranoid mode)
        replacement: The string to use for redacted values (default: "***REDACTED***")

    Returns:
        Sanitized URL with sensitive parameters redacted

    Examples:
        >>> sanitize_url_for_logging("https://api.example.com/data?api_key=secret123")
        'https://api.example.com/data?api_key=***REDACTED***'

        >>> sanitize_url_for_logging("https://example.com?foo=bar&token=abc&baz=qux")
        'https://example.com?foo=bar&token=***REDACTED***&baz=qux'

        >>> sanitize_url_for_logging("https://example.com/path", redact_all_query_params=True)
        'https://example.com/path'

        >>> sanitize_url_for_logging(
        ...     "https://api.example.com?custom_secret=xyz",
        ...     sensitive_params={"custom_secret"}
        ... )
        'https://api.example.com?custom_secret=***REDACTED***'

    Security Notes:
        - This function uses a best-effort approach based on common parameter names
        - Consider using redact_all_query_params=True for maximum security
        - URL fragments (#) and userinfo (user:pass@) are also stripped
        - Always review your logs to ensure no sensitive data leaks

    Usage in Logging:
        import logging
        from shared.logging_utils import sanitize_url_for_logging

        url = request.url  # May contain sensitive params
        safe_url = sanitize_url_for_logging(url)
        logging.info(f"Processing request: {safe_url}")

    Usage in Error Messages:
        try:
            response = requests.get(url)
        except Exception as e:
            safe_url = sanitize_url_for_logging(url)
            raise ValueError(f"Failed to fetch {safe_url}") from e
    """
    try:
        parsed = urlparse(url)

        # Build sensitive parameter set (case-insensitive)
        if sensitive_params is None:
            sensitive_set = SENSITIVE_PARAMS
        else:
            sensitive_set = SENSITIVE_PARAMS | {p.lower() for p in sensitive_params}

        # Strip userinfo (user:pass@host) for security
        netloc = parsed.netloc
        if "@" in netloc:
            # Remove everything before @ (username:password)
            netloc = netloc.split("@", 1)[1]

        # Process query parameters
        if parsed.query:
            if redact_all_query_params:
                # Paranoid mode: redact all query params
                query_string = ""
            else:
                # Parse query parameters
                params = parse_qs(parsed.query, keep_blank_values=True)
                sanitized_params = {}

                for key, values in params.items():
                    # Case-insensitive parameter name check
                    if key.lower() in sensitive_set:
                        # Redact sensitive parameter
                        sanitized_params[key] = [replacement] * len(values)
                    else:
                        # Keep non-sensitive parameter
                        sanitized_params[key] = values

                # Rebuild query string
                query_string = urlencode(sanitized_params, doseq=True)
        else:
            query_string = ""

        # Rebuild URL without fragment (fragments may contain sensitive data)
        sanitized = urlunparse(
            (
                parsed.scheme,
                netloc,
                parsed.path,
                parsed.params,
                query_string,
                "",  # Strip fragment for security
            )
        )

        return sanitized

    except Exception:
        # If parsing fails, return a safe placeholder
        # Better to lose debug info than leak secrets
        return f"{replacement} (URL parsing failed)"


def sanitize_error_message(message: str, *, replacement: str = "***REDACTED***") -> str:
    """Sanitize error messages that may contain URLs with sensitive data.

    Finds URL-like patterns in error messages and sanitizes them.

    Args:
        message: Error message that may contain URLs
        replacement: Replacement string for sensitive data

    Returns:
        Sanitized error message

    Example:
        >>> msg = "Failed to fetch https://api.example.com/data?token=secret123"
        >>> sanitize_error_message(msg)
        'Failed to fetch https://api.example.com/data?token=***REDACTED***'
    """
    # Pattern to match URLs in text
    url_pattern = re.compile(
        r"https?://[^\s<>\"'{}|\\^`\[\]]+", re.IGNORECASE | re.MULTILINE
    )

    def replace_url(match):
        """Replace each URL with sanitized version."""
        url = match.group(0)
        return sanitize_url_for_logging(url, replacement=replacement)

    return url_pattern.sub(replace_url, message)


# Convenience function for common use case
def safe_url(url: str) -> str:
    """Shorthand for sanitize_url_for_logging with defaults.

    Args:
        url: URL to sanitize

    Returns:
        Sanitized URL safe for logging

    Example:
        >>> from shared.logging_utils import safe_url
        >>> logger.info(f"Fetching {safe_url(request_url)}")
    """
    return sanitize_url_for_logging(url)
