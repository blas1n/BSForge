"""Database configuration and session management.

This module provides SQLAlchemy 2.0 async engine and session management.
It includes the Base class for all ORM models and utility functions.
"""

from collections.abc import AsyncGenerator
from typing import ClassVar

from sqlalchemy import MetaData, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, declared_attr

from app.core.config import get_config
from app.core.logging import get_logger

logger = get_logger(__name__)

# ============================================
# Naming Convention
# ============================================
# Consistent naming for constraints and indexes
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",  # Index
    "uq": "uq_%(table_name)s_%(column_0_name)s",  # Unique constraint
    "ck": "ck_%(table_name)s_%(constraint_name)s",  # Check constraint
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",  # Foreign key
    "pk": "pk_%(table_name)s",  # Primary key
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)


# ============================================
# Base Model
# ============================================


class Base(DeclarativeBase):
    """Base class for all ORM models.

    Provides common functionality for all models including:
    - Consistent table naming (snake_case)
    - Metadata with naming conventions
    - __repr__ implementation

    Example:
        >>> class User(Base):
        ...     __tablename__ = "users"
        ...     id: Mapped[int] = mapped_column(primary_key=True)
        ...     name: Mapped[str]
    """

    metadata: ClassVar[MetaData] = metadata

    @declared_attr.directive
    @classmethod
    def __tablename__(cls) -> str:
        """Generate table name from class name.

        Converts CamelCase to snake_case automatically.

        Returns:
            Snake case table name
        """
        # Convert CamelCase to snake_case
        import re

        name = re.sub(r"(?<!^)(?=[A-Z])", "_", cls.__name__).lower()
        return name

    def __repr__(self) -> str:
        """String representation of model instance.

        Returns:
            String representation showing class and primary key
        """
        columns = ", ".join(
            f"{k}={v!r}"
            for k, v in self.__dict__.items()
            if not k.startswith("_") and k != "metadata"
        )
        return f"{self.__class__.__name__}({columns})"


# ============================================
# Engine and Session
# ============================================

# Create async engine
_config = get_config()
engine: AsyncEngine = create_async_engine(
    str(_config.database_url),
    echo=_config.database_echo,
    pool_size=_config.database_pool_size,
    max_overflow=_config.database_max_overflow,
    pool_pre_ping=True,  # Verify connections before using
    pool_recycle=3600,  # Recycle connections after 1 hour
)

# Create session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get database session dependency.

    Yields async database session and ensures proper cleanup.
    Use this as a FastAPI dependency.

    Yields:
        AsyncSession: Database session

    Example:
        >>> from fastapi import Depends
        >>> async def get_user(db: AsyncSession = Depends(get_db)):
        ...     result = await db.execute(select(User))
        ...     return result.scalars().all()
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database (create all tables).

    This is mainly for development/testing. In production, use Alembic migrations.

    Example:
        >>> await init_db()
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialized")


async def close_db() -> None:
    """Close database connections.

    Call this when shutting down the application.

    Example:
        >>> await close_db()
    """
    await engine.dispose()
    logger.info("Database connections closed")


# ============================================
# Health Check
# ============================================


async def check_db_connection() -> bool:
    """Check if database connection is healthy.

    Returns:
        True if connection is successful, False otherwise

    Example:
        >>> is_healthy = await check_db_connection()
        >>> if not is_healthy:
        ...     logger.error("Database connection failed")
    """
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error("Database health check failed", error=str(e), exc_info=True)
        return False
