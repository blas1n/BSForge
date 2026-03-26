"""Pytest configuration and fixtures.

This module provides common fixtures used across all tests.
"""

import asyncio
from collections.abc import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.models  # noqa: F401 — ensure all models register with Base.metadata
from app.core.database import Base
from app.core.logging import setup_logging

# Setup logging for tests
setup_logging()


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests.

    Yields:
        Event loop for the test session
    """
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create test database session.

    Each test gets a fresh session with transaction that rolls back after test.
    This ensures test isolation.

    Yields:
        Test database session
    """
    # Create engine for this test
    engine = create_async_engine(
        "postgresql+asyncpg://postgres:postgres@postgres:5432/bsforge",
        echo=False,
        pool_pre_ping=True,
    )

    # Ensure all tables exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create a connection
    async with engine.connect() as connection:
        # Start a transaction
        transaction = await connection.begin()

        # Create session bound to this connection
        async_session = async_sessionmaker(
            bind=connection,
            class_=AsyncSession,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )

        async with async_session() as session:
            yield session

            # Rollback transaction after test
            await transaction.rollback()

    # Dispose engine
    await engine.dispose()


@pytest.fixture
def anyio_backend() -> str:
    """Specify backend for anyio.

    Returns:
        Backend name
    """
    return "asyncio"


# =============================================================================
# Mock Session Factory
# =============================================================================


def make_mock_session_factory(session: AsyncMock | None = None) -> tuple[MagicMock, AsyncMock]:
    """Create a mock async session factory for unit/e2e tests.

    Args:
        session: Pre-configured mock session. Creates a new one if None.

    Returns:
        Tuple of (factory, session) for test assertions.
    """
    if session is None:
        session = AsyncMock()
        session.get = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.execute = AsyncMock()
        session.refresh = AsyncMock()

    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    return factory, session
