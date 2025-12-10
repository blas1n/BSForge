"""FastAPI application entry point.

This module creates and configures the FastAPI application instance.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import close_db, init_db
from app.core.logging import get_logger, setup_logging
from app.core.redis import close_redis

# Setup logging
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan events.

    Handles startup and shutdown events for the FastAPI application.

    Args:
        app: FastAPI application instance

    Yields:
        None
    """
    # Startup
    logger.info("Starting BSForge application", env=settings.app_env)

    # Initialize database (only in development with available DB)
    if settings.is_development:
        try:
            from app.core.database import check_db_connection

            if await check_db_connection():
                await init_db()
                logger.info("Database initialized")
            else:
                logger.warning("Database connection not available, skipping initialization")
        except Exception as e:
            logger.warning(
                "Database initialization skipped", error=str(e), hint="Use migrations in production"
            )

    yield

    # Shutdown
    logger.info("Shutting down BSForge application")
    await close_db()
    await close_redis()
    logger.info("Cleanup complete")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    description="AI-powered YouTube Shorts automation system",
    version="0.1.0",
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check endpoint
@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint.

    Returns:
        Health status
    """
    return {
        "status": "healthy",
        "app": settings.app_name,
        "env": settings.app_env,
    }


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint.

    Returns:
        Welcome message
    """
    return {
        "message": "BSForge API",
        "version": "0.1.0",
        "docs": "/docs" if settings.is_development else "disabled",
    }


# API routers will be added in later phases
# from app.api.v1 import channels, review, stats
# app.include_router(channels.router, prefix="/api/v1", tags=["channels"])
# app.include_router(review.router, prefix="/api/v1", tags=["review"])
# app.include_router(stats.router, prefix="/api/v1", tags=["stats"])
