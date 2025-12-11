"""Unit tests for Source model.

Tests cover:
- Model creation and validation
- Enum types (SourceType, SourceRegion)
- M:N relationship with Channel
- Association table (channel_sources)
- Default values and constraints
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel import Channel
from app.models.source import Source, SourceRegion, SourceType, channel_sources


class TestSource:
    """Test Source model."""

    @pytest.mark.asyncio
    async def test_create_source(self, db_session: AsyncSession) -> None:
        """Test creating a basic source."""
        source = Source(
            name="reddit-programming",
            type=SourceType.API,
            region=SourceRegion.GLOBAL,
            connection_config={
                "subreddit": "programming",
                "client_id": "test123",
            },
            parser_config={"fields": ["title", "score"]},
            default_filters={"min_score": 10},
        )

        db_session.add(source)
        await db_session.commit()
        await db_session.refresh(source)

        # Verify
        assert source.id is not None
        assert isinstance(source.id, uuid.UUID)
        assert source.name == "reddit-programming"
        assert source.type == SourceType.API
        assert source.region == SourceRegion.GLOBAL
        assert source.connection_config["subreddit"] == "programming"
        assert source.created_at is not None

    @pytest.mark.asyncio
    async def test_source_default_values(self, db_session: AsyncSession) -> None:
        """Test source default values."""
        source = Source(
            name="default-source",
            type=SourceType.RSS,
            region=SourceRegion.DOMESTIC,
            connection_config={},
            parser_config={},
            default_filters={},
        )

        db_session.add(source)
        await db_session.commit()
        await db_session.refresh(source)

        assert source.rate_limit == 60
        assert source.credibility == 5.0
        assert source.language == "en"
        assert source.is_active is True
        assert source.last_collected_at is None

    @pytest.mark.asyncio
    async def test_source_name_unique(self, db_session: AsyncSession) -> None:
        """Test source name uniqueness constraint."""
        source1 = Source(
            name="unique-source",
            type=SourceType.API,
            region=SourceRegion.GLOBAL,
            connection_config={},
            parser_config={},
            default_filters={},
        )
        db_session.add(source1)
        await db_session.commit()

        # Try to create duplicate
        source2 = Source(
            name="unique-source",
            type=SourceType.RSS,
            region=SourceRegion.DOMESTIC,
            connection_config={},
            parser_config={},
            default_filters={},
        )
        db_session.add(source2)

        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_source_with_categories(self, db_session: AsyncSession) -> None:
        """Test source with category array."""
        source = Source(
            name="categorized-source",
            type=SourceType.SCRAPER,
            region=SourceRegion.DOMESTIC,
            categories=["tech", "news", "science"],
            connection_config={},
            parser_config={},
            default_filters={},
        )

        db_session.add(source)
        await db_session.commit()
        await db_session.refresh(source)

        assert len(source.categories) == 3
        assert "tech" in source.categories

    @pytest.mark.asyncio
    async def test_source_with_schedule(self, db_session: AsyncSession) -> None:
        """Test source with cron schedule."""
        source = Source(
            name="scheduled-source",
            type=SourceType.API,
            region=SourceRegion.GLOBAL,
            cron_expression="0 */6 * * *",  # Every 6 hours
            rate_limit=120,
            connection_config={},
            parser_config={},
            default_filters={},
        )

        db_session.add(source)
        await db_session.commit()
        await db_session.refresh(source)

        assert source.cron_expression == "0 */6 * * *"
        assert source.rate_limit == 120

    @pytest.mark.asyncio
    async def test_source_last_collected_update(self, db_session: AsyncSession) -> None:
        """Test updating last_collected_at timestamp."""
        source = Source(
            name="timestamp-test",
            type=SourceType.RSS,
            region=SourceRegion.FOREIGN,
            connection_config={},
            parser_config={},
            default_filters={},
        )

        db_session.add(source)
        await db_session.commit()
        await db_session.refresh(source)

        assert source.last_collected_at is None

        # Update timestamp
        now = datetime.now(UTC)
        source.last_collected_at = now
        await db_session.commit()
        await db_session.refresh(source)

        assert source.last_collected_at is not None
        assert source.last_collected_at.tzinfo is not None


class TestChannelSourceRelationship:
    """Test M:N relationship between Channel and Source."""

    @pytest.mark.asyncio
    async def test_channel_sources_association(self, db_session: AsyncSession) -> None:
        """Test associating channels with sources."""
        # Create channel
        channel = Channel(
            name="Test Channel",
            topic_config={},
            source_config={},
            content_config={},
            operation_config={},
        )
        db_session.add(channel)

        # Create source
        source = Source(
            name="test-source",
            type=SourceType.API,
            region=SourceRegion.GLOBAL,
            connection_config={},
            parser_config={},
            default_filters={},
        )
        db_session.add(source)
        await db_session.flush()

        # Associate via relationship
        channel.sources.append(source)
        await db_session.commit()

        # Refresh and verify
        await db_session.refresh(channel, ["sources"])
        await db_session.refresh(source, ["channels"])

        assert len(channel.sources) == 1
        assert channel.sources[0].name == "test-source"
        assert len(source.channels) == 1
        assert source.channels[0].name == "Test Channel"

    @pytest.mark.asyncio
    async def test_multiple_sources_per_channel(self, db_session: AsyncSession) -> None:
        """Test channel can have multiple sources."""
        channel = Channel(
            name="Multi-Source Channel",
            topic_config={},
            source_config={},
            content_config={},
            operation_config={},
        )
        db_session.add(channel)

        sources = []
        for i in range(3):
            source = Source(
                name=f"source-{i}",
                type=SourceType.API,
                region=SourceRegion.GLOBAL,
                connection_config={},
                parser_config={},
                default_filters={},
            )
            sources.append(source)
            db_session.add(source)

        await db_session.flush()

        # Associate all sources
        channel.sources.extend(sources)
        await db_session.commit()
        await db_session.refresh(channel, ["sources"])

        assert len(channel.sources) == 3

    @pytest.mark.asyncio
    async def test_channel_sources_cascade_delete(self, db_session: AsyncSession) -> None:
        """Test CASCADE deletion of association when channel or source is deleted."""
        channel = Channel(
            name="Delete Test",
            topic_config={},
            source_config={},
            content_config={},
            operation_config={},
        )
        source = Source(
            name="delete-source",
            type=SourceType.RSS,
            region=SourceRegion.DOMESTIC,
            connection_config={},
            parser_config={},
            default_filters={},
        )
        db_session.add_all([channel, source])
        await db_session.flush()

        channel.sources.append(source)
        await db_session.commit()

        channel_id = channel.id
        source_id = source.id

        # Delete channel
        await db_session.delete(channel)
        await db_session.commit()

        # Verify association is deleted but source still exists
        result = await db_session.execute(
            select(channel_sources).where(
                channel_sources.c.channel_id == channel_id,
                channel_sources.c.source_id == source_id,
            )
        )
        assert result.first() is None

        # Source should still exist
        source_result = await db_session.execute(select(Source).where(Source.id == source_id))
        assert source_result.scalar_one_or_none() is not None


class TestSourceType:
    """Test SourceType enum."""

    def test_source_type_values(self) -> None:
        """Test SourceType enum values."""
        assert SourceType.API == "api"
        assert SourceType.RSS == "rss"
        assert SourceType.SCRAPER == "scraper"
        assert SourceType.BROWSER == "browser"
        assert SourceType.VIDEO == "video"
        assert SourceType.SOCIAL == "social"
        assert SourceType.TREND == "trend"

        # Test all values exist
        types = [t.value for t in SourceType]
        assert len(types) == 7


class TestSourceRegion:
    """Test SourceRegion enum."""

    def test_source_region_values(self) -> None:
        """Test SourceRegion enum values."""
        assert SourceRegion.DOMESTIC == "domestic"
        assert SourceRegion.FOREIGN == "foreign"
        assert SourceRegion.GLOBAL == "global"

        # Test all values exist
        regions = [r.value for r in SourceRegion]
        assert len(regions) == 3
