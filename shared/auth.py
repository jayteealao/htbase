"""
Authentication middleware for API Gateway.

Provides API key-based authentication using FastAPI Security.
"""

from __future__ import annotations

import logging
import os

from fastapi import Security, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

# HTTP Bearer token security scheme
security = HTTPBearer()


async def get_validated_api_key(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> str:
    """
    Validate and return API key from Authorization header.

    Expects: Authorization: Bearer <api_key>

    Args:
        credentials: HTTP Bearer credentials from request header

    Returns:
        The validated API key string

    Raises:
        HTTPException: 401 if API key is invalid or missing
    """
    api_key = credentials.credentials

    # Get valid API keys from environment variable (comma-separated)
    valid_keys_str = os.getenv("API_KEYS", "")

    if not valid_keys_str:
        logger.error("API_KEYS environment variable not configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication not configured",
        )

    # Split and clean API keys
    valid_keys = [key.strip() for key in valid_keys_str.split(",") if key.strip()]

    if not valid_keys:
        logger.error("No valid API keys found in API_KEYS environment variable")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication not configured",
        )

    # Verify the provided key
    if api_key not in valid_keys:
        logger.warning(
            "Invalid API key attempt",
            extra={"key_prefix": api_key[:8] if len(api_key) >= 8 else "***"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    logger.debug("API key validated successfully")
    return api_key


# Backward compatibility alias (deprecated)
async def verify_api_key(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> str:
    """DEPRECATED: Use get_validated_api_key() instead.

    This function is maintained for backward compatibility only.

    Args:
        credentials: HTTP Bearer credentials from request header

    Returns:
        The validated API key string

    Raises:
        HTTPException: 401 if API key is invalid or missing
    """
    return await get_validated_api_key(credentials)
