"""Pytest configuration and fixtures.

This module provides common fixtures used across all tests.
"""

import asyncio
from collections.abc import AsyncGenerator, Generator
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

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
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def test_engine() -> AsyncGenerator[Any, None]:
    """Create test database engine.

    Uses in-memory SQLite for fast testing.

    Yields:
        Test database engine
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        pool_pre_ping=True,
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine: Any) -> AsyncGenerator[AsyncSession, None]:
    """Create test database session.

    Each test gets a fresh session with transaction that rolls back after test.
    This ensures test isolation.

    Args:
        test_engine: Test database engine

    Yields:
        Test database session
    """
    # Create a connection
    async with test_engine.connect() as connection:
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


@pytest.fixture
def anyio_backend() -> str:
    """Specify backend for anyio.

    Returns:
        Backend name
    """
    return "asyncio"
