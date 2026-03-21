"""Unit tests for topic collection pipeline."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.collector.base import NormalizedTopic, RawTopic
from app.services.collector.pipeline import (
    CollectionConfig,
    CollectionStats,
    TopicCollectionPipeline,
)


class TestCollectionStats:
    """Tests for CollectionStats model."""

    def test_default_values(self):
        """Test default values."""
        stats = CollectionStats()

        assert stats.total_collected == 0
        assert stats.normalized_count == 0
        assert stats.filtered_count == 0
        assert stats.deduplicated_count == 0
        assert stats.saved_count == 0
        assert stats.errors == []

    def test_with_values(self):
        """Test with custom values."""
        stats = CollectionStats(
            total_collected=30,
            normalized_count=28,
            filtered_count=25,
            deduplicated_count=20,
            saved_count=15,
            errors=["Error 1", "Error 2"],
        )

        assert stats.total_collected == 30
        assert stats.normalized_count == 28
        assert stats.filtered_count == 25
        assert stats.deduplicated_count == 20
        assert stats.saved_count == 15
        assert len(stats.errors) == 2


class TestCollectionConfig:
    """Tests for CollectionConfig dataclass."""

    def test_minimal_config(self):
        """Test minimal configuration."""
        config = CollectionConfig(
            sources=[],
            target_language="ko",
        )

        assert config.target_language == "ko"
        assert config.sources == []
        assert config.include == []
        assert config.exclude == []

    def test_full_config(self):
        """Test full configuration."""
        config = CollectionConfig(
            sources=["reddit", "google_trends", "rss"],
            target_language="ko",
            source_overrides={
                "reddit": {"subreddits": ["technology", "programming"]},
            },
            include=["ai", "ml"],
            exclude=["crypto"],
            max_topics=100,
            save_to_db=True,
        )

        assert "reddit" in config.sources
        assert "google_trends" in config.sources
        assert config.target_language == "ko"
        assert "reddit" in config.source_overrides
        assert config.max_topics == 100
        assert config.save_to_db is True

    def test_enabled_sources_property(self):
        """Test sources list."""
        config = CollectionConfig(
            sources=["reddit", "google_trends", "rss"],
            target_language="ko",
        )

        assert len(config.sources) == 3
        assert "reddit" in config.sources
        assert "google_trends" in config.sources
        assert "rss" in config.sources

    def test_filtering_config(self):
        """Test include/exclude filtering configuration."""
        config = CollectionConfig(
            sources=[],
            target_language="ko",
            include=["ai", "technology", "future"],
            exclude=["spam", "advertisement"],
        )

        assert len(config.include) == 3
        assert len(config.exclude) == 2
        assert "ai" in config.include
        assert "spam" in config.exclude

    def test_from_channel_config(self):
        """Test creating config from channel YAML dict."""
        channel_config = {
            "topic_collection": {
                "sources": ["reddit", "google_trends"],
                "target_language": "en",
            },
            "filtering": {
                "include": ["ai"],
                "exclude": ["spam"],
            },
        }

        config = CollectionConfig.from_channel_config(channel_config)

        assert config.target_language == "en"
        assert "reddit" in config.sources
        assert "google_trends" in config.sources

    def test_from_channel_config_defaults(self):
        """Test from_channel_config with empty config uses defaults."""
        channel_config = {}

        config = CollectionConfig.from_channel_config(channel_config)

        assert config.target_language == "ko"  # Default
        assert config.sources == []


def _make_normalized_topic(**kwargs: object) -> NormalizedTopic:
    """Create a NormalizedTopic with defaults for testing."""
    defaults = {
        "source_id": uuid.uuid4(),
        "source_url": "https://example.com/test",
        "title_original": "Test Title",
        "title_normalized": "test title",
        "summary": "Test summary",
        "terms": ["test"],
        "language": "en",
        "content_hash": "abc123",
    }
    defaults.update(kwargs)
    return NormalizedTopic(**defaults)


def _make_raw_topic(**kwargs: object) -> RawTopic:
    """Create a RawTopic with defaults for testing."""
    defaults = {
        "source_id": "src-1",
        "source_url": "https://example.com/test",
        "title": "Test Title",
    }
    defaults.update(kwargs)
    return RawTopic(**defaults)


class TestComputeContentHash:
    """Tests for _compute_content_hash static method."""

    def test_returns_consistent_hash(self) -> None:
        """Same input produces same hash."""
        norm = _make_normalized_topic(
            title_normalized="hello world",
            source_url="https://example.com/1",
        )
        pipeline = TopicCollectionPipeline(
            session=MagicMock(), http_client=MagicMock(), normalizer=MagicMock()
        )
        h1 = pipeline._compute_content_hash(norm)
        h2 = pipeline._compute_content_hash(norm)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_different_title_different_hash(self) -> None:
        """Different titles produce different hashes."""
        norm1 = _make_normalized_topic(title_normalized="hello")
        norm2 = _make_normalized_topic(title_normalized="world")
        h1 = TopicCollectionPipeline._compute_content_hash(norm1)
        h2 = TopicCollectionPipeline._compute_content_hash(norm2)
        assert h1 != h2

    def test_different_url_different_hash(self) -> None:
        """Different URLs produce different hashes."""
        norm1 = _make_normalized_topic(source_url="https://a.com/1")
        norm2 = _make_normalized_topic(source_url="https://b.com/2")
        h1 = TopicCollectionPipeline._compute_content_hash(norm1)
        h2 = TopicCollectionPipeline._compute_content_hash(norm2)
        assert h1 != h2


class TestCreateTopicModel:
    """Tests for _create_topic_model."""

    def test_expires_at_uses_published_at(self) -> None:
        """Topic expiration uses published_at when available."""
        published = datetime(2026, 3, 15, tzinfo=UTC)
        norm = _make_normalized_topic(published_at=published)
        raw = _make_raw_topic()
        channel = MagicMock()
        channel.id = uuid.uuid4()

        pipeline = TopicCollectionPipeline(
            session=MagicMock(), http_client=MagicMock(), normalizer=MagicMock()
        )
        topic = pipeline._create_topic_model(channel, raw, norm)

        assert topic.expires_at == published + timedelta(days=7)

    def test_expires_at_falls_back_to_now(self) -> None:
        """Topic expiration uses now() when published_at is None."""
        norm = _make_normalized_topic(published_at=None)
        raw = _make_raw_topic()
        channel = MagicMock()
        channel.id = uuid.uuid4()

        pipeline = TopicCollectionPipeline(
            session=MagicMock(), http_client=MagicMock(), normalizer=MagicMock()
        )
        before = datetime.now(UTC)
        topic = pipeline._create_topic_model(channel, raw, norm)
        after = datetime.now(UTC)

        assert before + timedelta(days=7) <= topic.expires_at <= after + timedelta(days=7)

    def test_content_hash_matches_compute(self) -> None:
        """Topic content_hash matches _compute_content_hash."""
        norm = _make_normalized_topic()
        raw = _make_raw_topic()
        channel = MagicMock()
        channel.id = uuid.uuid4()

        pipeline = TopicCollectionPipeline(
            session=MagicMock(), http_client=MagicMock(), normalizer=MagicMock()
        )
        topic = pipeline._create_topic_model(channel, raw, norm)
        expected_hash = pipeline._compute_content_hash(norm)
        assert topic.content_hash == expected_hash


class TestSaveTopics:
    """Tests for _save_topics error handling."""

    @pytest.mark.asyncio
    async def test_commit_failure_rolls_back(self) -> None:
        """Session rollback is called and saved list cleared when commit fails."""
        session = AsyncMock()
        session.commit.side_effect = RuntimeError("DB error")

        pipeline = TopicCollectionPipeline(
            session=session, http_client=MagicMock(), normalizer=MagicMock()
        )

        norm = _make_normalized_topic()
        raw = _make_raw_topic()
        channel = MagicMock()
        channel.id = uuid.uuid4()

        with pytest.raises(RuntimeError, match="DB error"):
            await pipeline._save_topics(channel, [(raw, norm)], max_topics=10)

        session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_integrity_error_returns_empty(self) -> None:
        """IntegrityError on flush returns empty list without raising."""
        from sqlalchemy.exc import IntegrityError

        session = AsyncMock()
        session.flush.side_effect = IntegrityError("dup", params=None, orig=Exception())

        pipeline = TopicCollectionPipeline(
            session=session, http_client=MagicMock(), normalizer=MagicMock()
        )

        norm = _make_normalized_topic()
        raw = _make_raw_topic()
        channel = MagicMock()
        channel.id = uuid.uuid4()

        result = await pipeline._save_topics(channel, [(raw, norm)], max_topics=10)

        assert result == []
        session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_save_respects_max_topics(self) -> None:
        """Only max_topics items are saved."""
        session = AsyncMock()

        pipeline = TopicCollectionPipeline(
            session=session, http_client=MagicMock(), normalizer=MagicMock()
        )

        topics = [
            (
                _make_raw_topic(title=f"Topic {i}"),
                _make_normalized_topic(title_normalized=f"topic {i}"),
            )
            for i in range(5)
        ]
        channel = MagicMock()
        channel.id = uuid.uuid4()

        saved = await pipeline._save_topics(channel, topics, max_topics=2)

        assert len(saved) == 2
        assert session.add.call_count == 2


class TestDeduplicateTopics:
    """Tests for _deduplicate_topics."""

    @pytest.mark.asyncio
    async def test_filters_existing_topics(self) -> None:
        """Topics already in DB are filtered out via batch query."""
        norm_existing = _make_normalized_topic(title_normalized="existing")
        norm_new = _make_normalized_topic(title_normalized="new")
        existing_hash = TopicCollectionPipeline._compute_content_hash(norm_existing)

        session = AsyncMock()
        # Batch query returns the hash of the existing topic
        session.execute.return_value = [(existing_hash,)]

        pipeline = TopicCollectionPipeline(
            session=session, http_client=MagicMock(), normalizer=MagicMock()
        )

        topics = [
            (_make_raw_topic(title="Existing"), norm_existing),
            (_make_raw_topic(title="New"), norm_new),
        ]

        result = await pipeline._deduplicate_topics(topics, uuid.uuid4())

        assert len(result) == 1
        assert result[0][1].title_normalized == "new"
        # Single batch query instead of N+1
        assert session.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty(self) -> None:
        """Empty input returns empty without DB query."""
        session = AsyncMock()
        pipeline = TopicCollectionPipeline(
            session=session, http_client=MagicMock(), normalizer=MagicMock()
        )

        result = await pipeline._deduplicate_topics([], uuid.uuid4())

        assert result == []
        session.execute.assert_not_called()


class TestCollectRawTopics:
    """Tests for _collect_raw_topics."""

    @pytest.mark.asyncio
    async def test_source_error_captured_in_stats(self) -> None:
        """Source collection errors are captured in stats, not raised."""
        session = AsyncMock()
        http_client = MagicMock()
        pipeline = TopicCollectionPipeline(
            session=session, http_client=http_client, normalizer=MagicMock()
        )

        config = CollectionConfig(sources=["nonexistent_source"])
        stats = CollectionStats()

        result = await pipeline._collect_raw_topics(config, stats)

        assert result == []
        assert len(stats.errors) == 1
        assert "nonexistent_source" in stats.errors[0]
