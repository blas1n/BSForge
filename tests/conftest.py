"""Pytest configuration and fixtures.

This module provides common fixtures used across all tests.
"""

import asyncio
from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

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
