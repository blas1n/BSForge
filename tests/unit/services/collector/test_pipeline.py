"""Unit tests for topic collection pipeline."""

from app.services.collector.pipeline import CollectionConfig, CollectionStats


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
