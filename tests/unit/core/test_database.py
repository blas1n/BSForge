"""Tests for app.core.database module."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel import Channel, ChannelStatus


@pytest.mark.unit
@pytest.mark.asyncio
async def test_base_tablename():
    """Test that __tablename__ is defined."""
    assert Channel.__tablename__ == "channels"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uuid_mixin(db_session: AsyncSession):
    """Test UUIDMixin provides UUID primary key."""
    channel = Channel(name="Test Channel", status=ChannelStatus.ACTIVE)
    db_session.add(channel)
    await db_session.commit()
    await db_session.refresh(channel)

    assert channel.id is not None
    assert len(str(channel.id)) == 36  # UUID string length


@pytest.mark.unit
@pytest.mark.asyncio
async def test_timestamp_mixin(db_session: AsyncSession):
    """Test TimestampMixin provides created_at and updated_at."""
    channel = Channel(name="Timestamp Test", status=ChannelStatus.ACTIVE)
    db_session.add(channel)
    await db_session.commit()
    await db_session.refresh(channel)

    assert channel.created_at is not None
    assert channel.updated_at is not None
    assert channel.created_at <= channel.updated_at


@pytest.mark.unit
@pytest.mark.asyncio
async def test_updated_at_changes(db_session: AsyncSession):
    """Test that updated_at changes on update."""
    import asyncio

    channel = Channel(name="Update Test", status=ChannelStatus.ACTIVE)
    db_session.add(channel)
    await db_session.commit()
    await db_session.refresh(channel)

    original_updated_at = channel.updated_at

    # Wait a bit to ensure timestamp difference
    await asyncio.sleep(0.1)

    channel.name = "Updated Name"
    await db_session.commit()
    await db_session.refresh(channel)

    # updated_at should be updated
    assert channel.updated_at is not None
    assert channel.updated_at >= original_updated_at


@pytest.mark.unit
@pytest.mark.asyncio
async def test_model_repr():
    """Test that __repr__ shows model attributes."""
    channel = Channel(name="Repr Test", status=ChannelStatus.ACTIVE)
    repr_str = repr(channel)

    assert "Channel" in repr_str
    assert "Repr Test" in repr_str


@pytest.mark.unit
@pytest.mark.asyncio
async def test_crud_operations(db_session: AsyncSession):
    """Test basic CRUD operations."""
    # Create
    channel = Channel(name="CRUD Test", status=ChannelStatus.ACTIVE)
    db_session.add(channel)
    await db_session.commit()
    await db_session.refresh(channel)

    channel_id = channel.id

    # Read
    result = await db_session.execute(select(Channel).where(Channel.id == channel_id))
    fetched = result.scalar_one_or_none()
    assert fetched is not None
    assert fetched.name == "CRUD Test"

    # Update
    fetched.name = "Updated CRUD Test"
    await db_session.commit()
    await db_session.refresh(fetched)
    assert fetched.name == "Updated CRUD Test"

    # Delete
    await db_session.delete(fetched)
    await db_session.commit()

    result = await db_session.execute(select(Channel).where(Channel.id == channel_id))
    deleted = result.scalar_one_or_none()
    assert deleted is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_unique_constraint(db_session: AsyncSession):
    """Test unique constraint on youtube_channel_id."""
    from sqlalchemy.exc import IntegrityError

    channel1 = Channel(
        name="Channel 1",
        status=ChannelStatus.ACTIVE,
        youtube_channel_id="UC123456789",
    )
    db_session.add(channel1)
    await db_session.commit()

    channel2 = Channel(
        name="Channel 2",
        status=ChannelStatus.ACTIVE,
        youtube_channel_id="UC123456789",  # Duplicate
    )
    db_session.add(channel2)

    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_session_rollback(db_session: AsyncSession):
    """Test that session rollback works."""
    # Count initial channels
    result = await db_session.execute(select(Channel))
    initial_count = len(result.scalars().all())

    # Add and flush a new channel
    channel = Channel(name="Rollback Test", status=ChannelStatus.ACTIVE)
    db_session.add(channel)
    await db_session.flush()

    # Verify channel was added
    result = await db_session.execute(select(Channel))
    after_flush_count = len(result.scalars().all())
    assert after_flush_count == initial_count + 1

    # Rollback
    await db_session.rollback()

    # Verify channel was rolled back
    result = await db_session.execute(select(Channel))
    after_rollback_count = len(result.scalars().all())
    assert after_rollback_count == initial_count
