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

# Add shared module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from shared.config import get_settings, configure_logging
from shared.models import HealthResponse

from app.routes import saves, tasks, admin

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
    try:
        from shared.db import check_connection

        if check_connection():
            logger.info("Database connection verified")
        else:
            logger.warning("Database connection failed - some features may not work")
    except Exception as e:
        logger.warning(f"Database check failed: {e}")

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

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(saves.router, prefix="/api/v1", tags=["saves"])
    app.include_router(tasks.router, prefix="/api/v1", tags=["tasks"])
    app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])

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

        # Check database
        try:
            from shared.db import check_connection

            if check_connection():
                services["database"] = "healthy"
            else:
                services["database"] = "unhealthy"
        except Exception:
            services["database"] = "unhealthy"

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
