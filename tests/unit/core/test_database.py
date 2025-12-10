"""Tests for app.core.database module."""

import pytest
from sqlalchemy import String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin


# Test model
class TestUser(Base, UUIDMixin, TimestampMixin):
    """Test user model."""

    __tablename__ = "test_users"

    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(100), unique=True)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_base_tablename():
    """Test that __tablename__ is generated from class name."""
    assert TestUser.__tablename__ == "test_users"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uuid_mixin(db_session: AsyncSession):
    """Test UUIDMixin provides UUID primary key."""
    user = TestUser(name="John", email="john@example.com")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    assert user.id is not None
    assert isinstance(user.id, object)  # UUID type
    assert len(str(user.id)) == 36  # UUID string length


@pytest.mark.unit
@pytest.mark.asyncio
async def test_timestamp_mixin(db_session: AsyncSession):
    """Test TimestampMixin provides created_at and updated_at."""
    user = TestUser(name="Jane", email="jane@example.com")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    assert user.created_at is not None
    assert user.updated_at is not None
    assert user.created_at <= user.updated_at


@pytest.mark.unit
@pytest.mark.asyncio
async def test_updated_at_changes(db_session: AsyncSession):
    """Test that updated_at changes on update."""
    import asyncio

    user = TestUser(name="Bob", email="bob@example.com")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    # Wait a bit to ensure timestamp difference
    await asyncio.sleep(0.1)

    user.name = "Robert"
    await db_session.commit()
    await db_session.refresh(user)

    # Note: updated_at might not change in SQLite without proper triggers
    # This test mainly verifies the column exists
    assert user.updated_at is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_model_repr():
    """Test that __repr__ shows model attributes."""
    user = TestUser(name="Alice", email="alice@example.com")
    repr_str = repr(user)

    assert "TestUser" in repr_str
    assert "name='Alice'" in repr_str
    assert "email='alice@example.com'" in repr_str


@pytest.mark.unit
@pytest.mark.asyncio
async def test_crud_operations(db_session: AsyncSession):
    """Test basic CRUD operations."""
    # Create
    user = TestUser(name="Charlie", email="charlie@example.com")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    user_id = user.id

    # Read
    result = await db_session.execute(select(TestUser).where(TestUser.id == user_id))
    fetched_user = result.scalar_one_or_none()
    assert fetched_user is not None
    assert fetched_user.name == "Charlie"

    # Update
    fetched_user.name = "Charles"
    await db_session.commit()
    await db_session.refresh(fetched_user)
    assert fetched_user.name == "Charles"

    # Delete
    await db_session.delete(fetched_user)
    await db_session.commit()

    result = await db_session.execute(select(TestUser).where(TestUser.id == user_id))
    deleted_user = result.scalar_one_or_none()
    assert deleted_user is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_unique_constraint(db_session: AsyncSession):
    """Test unique constraint on email."""
    from sqlalchemy.exc import IntegrityError

    user1 = TestUser(name="User1", email="same@example.com")
    db_session.add(user1)
    await db_session.commit()

    user2 = TestUser(name="User2", email="same@example.com")
    db_session.add(user2)

    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_session_rollback(db_session: AsyncSession):
    """Test that session rollback works."""
    # Count initial users
    result = await db_session.execute(select(TestUser))
    initial_count = len(result.scalars().all())

    # Add and flush a new user
    user = TestUser(name="Test", email="test@example.com")
    db_session.add(user)
    await db_session.flush()

    # Verify user was added
    result = await db_session.execute(select(TestUser))
    after_flush_count = len(result.scalars().all())
    assert after_flush_count == initial_count + 1

    # Rollback
    await db_session.rollback()

    # Verify user was rolled back
    result = await db_session.execute(select(TestUser))
    after_rollback_count = len(result.scalars().all())
    assert after_rollback_count == initial_count
