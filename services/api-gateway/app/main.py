"""
API Gateway - Main FastAPI Application

This is the main entry point for the API Gateway service.
It handles HTTP requests and dispatches tasks to Celery workers.
"""

from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from shared.config import get_settings, configure_logging
from shared.models import HealthResponse
from shared.rate_limit import slowapi_limiter, _rate_limit_exceeded_handler, RateLimitMiddleware

from app.routes import tasks, sync, archives, artifacts, system

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""
    settings = get_settings()
    configure_logging(settings)

    logger.info(
        "Starting API Gateway",
        extra={
            "service": "api-gateway",
            "environment": settings.environment,
        },
    )

    # Startup: verify connections
    # Firestore connections are lazy-loaded, no need for startup check

    yield

    # Shutdown
    logger.info("Shutting down API Gateway")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="HTBase API Gateway",
        description="API Gateway for HTBase archiving service",
        version="2.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # Configure SlowAPI rate limiter
    app.state.limiter = slowapi_limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # Add rate limit middleware for response headers
    app.add_middleware(RateLimitMiddleware)

    # CORS middleware - configure allowed origins from environment
    cors_origins = settings.cors_origins if hasattr(settings, 'cors_origins') else []

    # In production, be more restrictive
    if settings.environment == "production":
        # Only allow credentials in development
        allow_credentials = False
        # If no origins configured in production, block all CORS
        if not cors_origins:
            logger.warning("No CORS origins configured for production - CORS will be disabled")
            cors_origins = []
    else:
        # Development: Allow credentials for easier local development
        allow_credentials = True

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=allow_credentials,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
    )

    # Include routers - Consolidated API structure
    app.include_router(archives.router, prefix="/api/v1", tags=["archives"])
    app.include_router(artifacts.router, prefix="/api/v1", tags=["artifacts"])
    app.include_router(system.router, prefix="/api/v1", tags=["system"])
    app.include_router(tasks.router, prefix="/api/v1", tags=["tasks"])
    app.include_router(sync.router, prefix="/api/v1", tags=["sync"])

    # Exception handlers
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(
            f"Unhandled exception: {exc}",
            exc_info=True,
            extra={"path": request.url.path},
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    # Health check endpoint
    @app.get("/health", response_model=HealthResponse)
    async def health_check():
        """Health check endpoint."""
        services = {}

        # Check Redis/Celery
        try:
            from shared.celery_config import celery_app

            celery_app.control.ping(timeout=1)
            services["celery"] = "healthy"
        except Exception:
            services["celery"] = "unhealthy"

        # Check Firestore (lazy-loaded, assume healthy if configured)
        try:
            from shared.firestore_client import get_firestore_client
            get_firestore_client()  # Will raise if not configured
            services["firestore"] = "healthy"
        except Exception:
            services["firestore"] = "unhealthy"

        status = "healthy" if all(v == "healthy" for v in services.values()) else "degraded"

        return HealthResponse(
            status=status,
            version="2.0.0",
            services=services,
        )

    @app.get("/")
    async def root():
        """Root endpoint."""
        return {
            "service": "htbase-api-gateway",
            "version": "2.0.0",
            "docs": "/docs",
        }

    return app


# Create application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
        reload=os.getenv("ENVIRONMENT", "development") == "development",
    )
