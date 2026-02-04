"""Unit tests for series configuration models."""

import pytest
from pydantic import ValidationError

from app.config.series import (
    SeriesConfig,
    SeriesCriteria,
    SeriesMatcherConfig,
)


class TestSeriesCriteria:
    """Tests for SeriesCriteria model."""

    def test_default_values(self):
        """Test default configuration values."""
        criteria = SeriesCriteria()
        assert criteria.terms == []
        assert criteria.min_similarity == 0.6

    def test_terms_lowercased(self):
        """Test terms are automatically lowercased."""
        criteria = SeriesCriteria(terms=["AI", "MACHINE Learning", "TeSt"])
        assert criteria.terms == ["ai", "machine learning", "test"]

    def test_min_similarity_range(self):
        """Test min_similarity validation."""
        criteria = SeriesCriteria(min_similarity=0.0)
        assert criteria.min_similarity == 0.0

        criteria = SeriesCriteria(min_similarity=1.0)
        assert criteria.min_similarity == 1.0

        criteria = SeriesCriteria(min_similarity=0.5)
        assert criteria.min_similarity == 0.5

        with pytest.raises(ValidationError):
            SeriesCriteria(min_similarity=-0.1)

        with pytest.raises(ValidationError):
            SeriesCriteria(min_similarity=1.1)

    def test_single_string_input(self):
        """Test single string input is converted to list."""
        criteria = SeriesCriteria(terms="single")
        assert criteria.terms == ["single"]


class TestSeriesConfig:
    """Tests for SeriesConfig model."""

    def test_required_fields(self):
        """Test required fields."""
        with pytest.raises(ValidationError):
            SeriesConfig()  # Missing id, name, criteria

    def test_minimal_config(self):
        """Test minimal valid configuration."""
        config = SeriesConfig(
            id="test-series",
            name="Test Series",
            criteria=SeriesCriteria(),
        )
        assert config.id == "test-series"
        assert config.name == "Test Series"
        assert config.enabled is True
        assert config.auto_detected is False

    def test_full_config(self):
        """Test full configuration."""
        criteria = SeriesCriteria(terms=["ai", "tech"], min_similarity=0.7)
        config = SeriesConfig(
            id="ai-news",
            name="AI News",
            criteria=criteria,
            enabled=True,
            auto_detected=True,
        )
        assert config.id == "ai-news"
        assert config.name == "AI News"
        assert config.criteria.terms == ["ai", "tech"]
        assert config.criteria.min_similarity == 0.7
        assert config.enabled is True
        assert config.auto_detected is True

    def test_disabled_series(self):
        """Test disabled series configuration."""
        config = SeriesConfig(
            id="old-series",
            name="Old Series",
            criteria=SeriesCriteria(),
            enabled=False,
        )
        assert config.enabled is False


class TestSeriesMatcherConfig:
    """Tests for SeriesMatcherConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = SeriesMatcherConfig()
        assert config.enabled is True
        assert config.series == []
        assert config.boost_matched_topics == 0.2

    def test_with_series(self):
        """Test with series list."""
        series1 = SeriesConfig(
            id="series-1",
            name="Series 1",
            criteria=SeriesCriteria(terms=["term1"]),
        )
        series2 = SeriesConfig(
            id="series-2",
            name="Series 2",
            criteria=SeriesCriteria(terms=["term2"]),
        )
        config = SeriesMatcherConfig(series=[series1, series2])
        assert len(config.series) == 2
        assert config.series[0].id == "series-1"
        assert config.series[1].id == "series-2"

    def test_boost_range(self):
        """Test boost_matched_topics validation."""
        config = SeriesMatcherConfig(boost_matched_topics=0.0)
        assert config.boost_matched_topics == 0.0

        config = SeriesMatcherConfig(boost_matched_topics=1.0)
        assert config.boost_matched_topics == 1.0

        with pytest.raises(ValidationError):
            SeriesMatcherConfig(boost_matched_topics=-0.1)

        with pytest.raises(ValidationError):
            SeriesMatcherConfig(boost_matched_topics=1.1)

    def test_disabled_matcher(self):
        """Test disabled matcher configuration."""
        config = SeriesMatcherConfig(enabled=False)
        assert config.enabled is False
