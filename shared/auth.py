"""
Authentication middleware for API Gateway.

Provides API key-based authentication using FastAPI Security.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import Security, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

# HTTP Bearer token security scheme
security = HTTPBearer()


async def verify_api_key(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> str:
    """
    Verify API key from Authorization header.

    Expects: Authorization: Bearer <api_key>

    Args:
        credentials: HTTP Bearer credentials from request header

    Returns:
        str: The validated API key

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


async def optional_verify_api_key(
    request: Request,
) -> Optional[str]:
    """
    Optional API key verification for endpoints that support both authenticated and public access.

    Args:
        request: FastAPI Request object

    Returns:
        Optional[str]: The validated API key if provided, None otherwise

    Raises:
        HTTPException: 401 if API key is provided but invalid
    """
    # Check for Authorization header
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return None

    # Parse Bearer token
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication scheme. Expected: Bearer",
            headers={"WWW-Authenticate": "Bearer"},
        )

    api_key = auth_header[7:]  # Remove "Bearer " prefix

    # Validate API key
    expected_key = os.getenv("API_KEY")
    if not expected_key:
        logger.warning("API_KEY environment variable not set")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API authentication not configured",
        )

    if api_key != expected_key:
        logger.warning(f"Invalid API key provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    logger.debug("API key validated successfully")
    return api_key
