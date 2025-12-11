"""Unit tests for Topic model.

Tests cover:
- Model creation and validation
- Three title variants (original, translated, normalized)
- Scoring components
- Status lifecycle
- Relationships with Channel and Source
- Indexes and constraints
- Deduplication hash
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel import Channel
from app.models.source import Source, SourceRegion, SourceType
from app.models.topic import Topic, TopicStatus


class TestTopic:
    """Test Topic model."""

    @pytest.mark.asyncio
    async def test_create_topic(self, db_session: AsyncSession) -> None:
        """Test creating a basic topic."""
        # Create channel first
        channel = Channel(
            name="Test Channel",
            topic_config={},
            source_config={},
            content_config={},
            operation_config={},
        )
        db_session.add(channel)
        await db_session.flush()

        # Create topic
        expires = datetime.now(UTC) + timedelta(days=7)
        topic = Topic(
            channel_id=channel.id,
            title_original="OpenAI releases GPT-4.5",
            title_translated="OpenAI가 GPT-4.5를 출시하다",
            title_normalized="OpenAI releases GPT-4.5",
            summary="OpenAI announced the release of GPT-4.5 with improved capabilities.",
            source_url="https://news.example.com/gpt45",
            categories=["tech", "ai"],
            keywords=["openai", "gpt", "ai"],
            entities={"companies": ["OpenAI"], "products": ["GPT-4.5"]},
            language="en",
            score_source=0.9,
            score_freshness=1.0,
            score_trend=0.85,
            score_relevance=0.75,
            score_total=85,
            status=TopicStatus.PENDING,
            published_at=datetime.now(UTC),
            expires_at=expires,
            content_hash="abc123def456",
        )

        db_session.add(topic)
        await db_session.commit()
        await db_session.refresh(topic)

        # Verify
        assert topic.id is not None
        assert isinstance(topic.id, uuid.UUID)
        assert topic.title_original == "OpenAI releases GPT-4.5"
        assert topic.title_translated == "OpenAI가 GPT-4.5를 출시하다"
        assert topic.score_total == 85
        assert topic.status == TopicStatus.PENDING
        assert len(topic.categories) == 2
        assert len(topic.keywords) == 3
        assert "OpenAI" in topic.entities["companies"]

    @pytest.mark.asyncio
    async def test_topic_default_values(self, db_session: AsyncSession) -> None:
        """Test topic default values."""
        channel = Channel(
            name="Default Channel",
            topic_config={},
            source_config={},
            content_config={},
            operation_config={},
        )
        db_session.add(channel)
        await db_session.flush()

        topic = Topic(
            channel_id=channel.id,
            title_original="Test",
            title_normalized="test",
            summary="Summary",
            source_url="https://example.com",
            categories=[],
            keywords=[],
            entities={},
            expires_at=datetime.now(UTC) + timedelta(days=1),
            content_hash="hash123",
        )

        db_session.add(topic)
        await db_session.commit()
        await db_session.refresh(topic)

        assert topic.score_source == 0.0
        assert topic.score_freshness == 0.0
        assert topic.score_trend == 0.0
        assert topic.score_relevance == 0.0
        assert topic.score_total == 0
        assert topic.status == TopicStatus.PENDING
        assert topic.language == "en"
        assert topic.title_translated is None
        assert topic.published_at is None

    @pytest.mark.asyncio
    async def test_topic_channel_relationship(self, db_session: AsyncSession) -> None:
        """Test Topic-Channel relationship."""
        channel = Channel(
            name="Relationship Test",
            topic_config={},
            source_config={},
            content_config={},
            operation_config={},
        )
        db_session.add(channel)
        await db_session.flush()

        # Create multiple topics for same channel
        for i in range(3):
            topic = Topic(
                channel_id=channel.id,
                title_original=f"Topic {i}",
                title_normalized=f"topic {i}",
                summary=f"Summary {i}",
                source_url=f"https://example.com/{i}",
                categories=["test"],
                keywords=[],
                entities={},
                expires_at=datetime.now(UTC) + timedelta(days=1),
                content_hash=f"hash{i}",
            )
            db_session.add(topic)

        await db_session.commit()
        await db_session.refresh(channel, ["topics"])

        assert len(channel.topics) == 3

    @pytest.mark.asyncio
    async def test_topic_source_relationship(self, db_session: AsyncSession) -> None:
        """Test Topic-Source relationship."""
        channel = Channel(
            name="Source Test",
            topic_config={},
            source_config={},
            content_config={},
            operation_config={},
        )
        source = Source(
            name="test-source",
            type=SourceType.API,
            region=SourceRegion.GLOBAL,
            connection_config={},
            parser_config={},
            default_filters={},
        )
        db_session.add_all([channel, source])
        await db_session.flush()

        topic = Topic(
            channel_id=channel.id,
            source_id=source.id,
            title_original="Source Test Topic",
            title_normalized="source test topic",
            summary="A topic from a source",
            source_url="https://source.com",
            categories=["test"],
            keywords=[],
            entities={},
            expires_at=datetime.now(UTC) + timedelta(days=1),
            content_hash="sourcehash",
        )

        db_session.add(topic)
        await db_session.commit()
        await db_session.refresh(topic, ["source"])

        assert topic.source is not None
        assert topic.source.name == "test-source"

    @pytest.mark.asyncio
    async def test_topic_source_set_null_on_delete(self, db_session: AsyncSession) -> None:
        """Test source_id is SET NULL when source is deleted."""
        channel = Channel(
            name="Null Test",
            topic_config={},
            source_config={},
            content_config={},
            operation_config={},
        )
        source = Source(
            name="deletable-source",
            type=SourceType.RSS,
            region=SourceRegion.DOMESTIC,
            connection_config={},
            parser_config={},
            default_filters={},
        )
        db_session.add_all([channel, source])
        await db_session.flush()

        topic = Topic(
            channel_id=channel.id,
            source_id=source.id,
            title_original="Delete Test",
            title_normalized="delete test",
            summary="Test",
            source_url="https://example.com",
            categories=[],
            keywords=[],
            entities={},
            expires_at=datetime.now(UTC) + timedelta(days=1),
            content_hash="delhash",
        )
        db_session.add(topic)
        await db_session.commit()

        topic_id = topic.id

        # Delete source
        await db_session.delete(source)
        await db_session.commit()

        # Verify topic still exists but source_id is NULL
        result = await db_session.execute(select(Topic).where(Topic.id == topic_id))
        remaining_topic = result.scalar_one()
        assert remaining_topic.source_id is None

    @pytest.mark.asyncio
    async def test_topic_status_lifecycle(self, db_session: AsyncSession) -> None:
        """Test topic status transitions."""
        channel = Channel(
            name="Status Test",
            topic_config={},
            source_config={},
            content_config={},
            operation_config={},
        )
        db_session.add(channel)
        await db_session.flush()

        topic = Topic(
            channel_id=channel.id,
            title_original="Status Topic",
            title_normalized="status topic",
            summary="Testing status",
            source_url="https://example.com",
            categories=[],
            keywords=[],
            entities={},
            expires_at=datetime.now(UTC) + timedelta(days=7),
            content_hash="statushash",
        )
        db_session.add(topic)
        await db_session.commit()

        # Initially PENDING
        assert topic.status == TopicStatus.PENDING

        # Approve
        topic.status = TopicStatus.APPROVED
        await db_session.commit()
        await db_session.refresh(topic)
        assert topic.status == TopicStatus.APPROVED

        # Mark as used
        topic.status = TopicStatus.USED
        await db_session.commit()
        await db_session.refresh(topic)
        assert topic.status == TopicStatus.USED

    @pytest.mark.asyncio
    async def test_topic_scoring_components(self, db_session: AsyncSession) -> None:
        """Test all scoring components."""
        channel = Channel(
            name="Score Test",
            topic_config={},
            source_config={},
            content_config={},
            operation_config={},
        )
        db_session.add(channel)
        await db_session.flush()

        # Create topic with specific scores
        topic = Topic(
            channel_id=channel.id,
            title_original="Score Test",
            title_normalized="score test",
            summary="Testing scores",
            source_url="https://example.com",
            categories=["test"],
            keywords=[],
            entities={},
            score_source=0.9,  # 90% credible source
            score_freshness=1.0,  # Very fresh (recent)
            score_trend=0.75,  # Trending
            score_relevance=0.85,  # Highly relevant
            score_total=87,  # Weighted total
            expires_at=datetime.now(UTC) + timedelta(days=1),
            content_hash="scorehash",
        )

        db_session.add(topic)
        await db_session.commit()
        await db_session.refresh(topic)

        assert topic.score_source == 0.9
        assert topic.score_freshness == 1.0
        assert topic.score_trend == 0.75
        assert topic.score_relevance == 0.85
        assert topic.score_total == 87

    @pytest.mark.asyncio
    async def test_topic_expiration(self, db_session: AsyncSession) -> None:
        """Test topic expiration logic."""
        channel = Channel(
            name="Expiry Test",
            topic_config={},
            source_config={},
            content_config={},
            operation_config={},
        )
        db_session.add(channel)
        await db_session.flush()

        # Create expired topic
        past_date = datetime.now(UTC) - timedelta(days=1)
        topic = Topic(
            channel_id=channel.id,
            title_original="Expired Topic",
            title_normalized="expired topic",
            summary="Old topic",
            source_url="https://example.com",
            categories=[],
            keywords=[],
            entities={},
            expires_at=past_date,
            content_hash="expiredhash",
        )

        db_session.add(topic)
        await db_session.commit()

        # Query expired topics
        now = datetime.now(UTC)
        result = await db_session.execute(select(Topic).where(Topic.expires_at < now))
        expired_topics = result.scalars().all()

        assert len(expired_topics) >= 1
        assert topic in expired_topics

    @pytest.mark.asyncio
    async def test_topic_content_hash_deduplication(self, db_session: AsyncSession) -> None:
        """Test content hash for deduplication."""
        channel = Channel(
            name="Dedup Test",
            topic_config={},
            source_config={},
            content_config={},
            operation_config={},
        )
        db_session.add(channel)
        await db_session.flush()

        # Create topic with specific hash
        hash_value = "unique_hash_12345"
        topic1 = Topic(
            channel_id=channel.id,
            title_original="Original Topic",
            title_normalized="original topic",
            summary="First",
            source_url="https://example.com/1",
            categories=[],
            keywords=[],
            entities={},
            expires_at=datetime.now(UTC) + timedelta(days=1),
            content_hash=hash_value,
        )
        db_session.add(topic1)
        await db_session.commit()

        # Query by hash
        result = await db_session.execute(select(Topic).where(Topic.content_hash == hash_value))
        found_topic = result.scalar_one()

        assert found_topic.id == topic1.id


class TestTopicStatus:
    """Test TopicStatus enum."""

    def test_topic_status_values(self) -> None:
        """Test TopicStatus enum values."""
        assert TopicStatus.PENDING == "pending"
        assert TopicStatus.APPROVED == "approved"
        assert TopicStatus.REJECTED == "rejected"
        assert TopicStatus.USED == "used"
        assert TopicStatus.EXPIRED == "expired"

        # Test all values exist
        statuses = [s.value for s in TopicStatus]
        assert len(statuses) == 5
