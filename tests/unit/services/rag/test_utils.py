"""Unit tests for RAG utility functions."""

from unittest.mock import MagicMock

import pytest

from app.services.rag.utils import build_template_vars_from_channel_config


class TestBuildTemplateVarsFromChannelConfig:
    """Tests for build_template_vars_from_channel_config function."""

    @pytest.fixture
    def minimal_channel_config(self):
        """Create minimal channel config."""
        return {}

    @pytest.fixture
    def full_channel_config(self):
        """Create full channel config."""
        return {
            "persona": {
                "name": "TechGuru",
                "tagline": "AI 전문가",
                "communication": {
                    "tone": "friendly",
                    "formality": "casual",
                    "speech_patterns": {
                        "sentence_endings": ["요", "죠", "네요"],
                        "connectors": ["그래서", "그런데", "하지만"],
                    },
                    "avoid_patterns": {
                        "words": ["음", "어", "저기"],
                    },
                },
                "perspective": {
                    "core_values": ["혁신", "실용성"],
                    "contrarian_views": ["AI는 만능이 아니다", "속도보다 정확성"],
                },
            },
            "content": {
                "format": "shorts",
                "target_duration": 45,
            },
        }

    @pytest.fixture
    def mock_topic(self):
        """Create mock topic."""
        topic = MagicMock()
        topic.title_normalized = "ai 기술의 미래"
        topic.summary = "AI 기술 발전에 대한 요약"
        topic.terms = ["ai", "technology", "future"]
        return topic

    @pytest.fixture
    def mock_cluster(self):
        """Create mock topic cluster."""
        cluster = MagicMock()
        cluster.source_count = 3
        cluster.sources = {"reddit", "hackernews", "rss"}
        cluster.combined_terms = ["ai", "ml", "tech"]
        cluster.total_engagement = 5000

        # Related topics
        related1 = MagicMock()
        related1.title_original = "Related Topic 1"
        related2 = MagicMock()
        related2.title_original = "Related Topic 2"
        cluster.related_topics = [related1, related2]

        return cluster

    def test_minimal_config(self, minimal_channel_config, mock_topic):
        """Test with minimal/empty config."""
        result = build_template_vars_from_channel_config(minimal_channel_config, mock_topic)

        assert result["persona_name"] is None
        assert result["persona_tagline"] is None
        assert result["topic_title"] == "ai 기술의 미래"
        assert result["multi_source"] is False
        assert result["source_count"] == 1

    def test_full_config(self, full_channel_config, mock_topic):
        """Test with full config."""
        result = build_template_vars_from_channel_config(full_channel_config, mock_topic)

        # Persona
        assert result["persona_name"] == "TechGuru"
        assert result["persona_tagline"] == "AI 전문가"
        assert "TechGuru" in result["persona_description"]

        # Communication
        assert result["communication_tone"] == "friendly"
        assert result["communication_formality"] == "casual"
        assert "요" in result["sentence_endings"]
        assert "그래서" in result["connectors"]
        assert "음" in result["avoid_words"]

        # Perspective
        assert "혁신" in result["perspective_values"]
        assert "AI는 만능이 아니다" in result["perspective_biases"]
        assert result["perspective_contrarian"] is True

        # Content
        assert result["video_format"] == "shorts"
        assert result["target_duration"] == 45

    def test_topic_extraction(self, minimal_channel_config, mock_topic):
        """Test topic fields extraction."""
        result = build_template_vars_from_channel_config(minimal_channel_config, mock_topic)

        assert result["topic_title"] == "ai 기술의 미래"
        assert result["topic_summary"] == "AI 기술 발전에 대한 요약"
        assert result["topic_terms"] == ["ai", "technology", "future"]

    def test_topic_without_attributes(self, minimal_channel_config):
        """Test with topic that doesn't have expected attributes."""
        simple_topic = "Simple string topic"

        result = build_template_vars_from_channel_config(minimal_channel_config, simple_topic)

        assert result["topic_title"] == "Simple string topic"
        assert result["topic_summary"] is None
        assert result["topic_terms"] == []

    def test_with_cluster(self, minimal_channel_config, mock_topic, mock_cluster):
        """Test with topic cluster."""
        result = build_template_vars_from_channel_config(
            minimal_channel_config, mock_topic, cluster=mock_cluster
        )

        assert result["multi_source"] is True
        assert result["source_count"] == 3
        assert "reddit" in result["source_names"]
        assert len(result["related_titles"]) == 2
        assert result["combined_terms"] == ["ai", "ml", "tech"]
        assert result["total_engagement"] == 5000

    def test_without_cluster(self, minimal_channel_config, mock_topic):
        """Test without cluster returns defaults."""
        result = build_template_vars_from_channel_config(
            minimal_channel_config, mock_topic, cluster=None
        )

        assert result["multi_source"] is False
        assert result["source_count"] == 1
        assert result["source_names"] == []
        assert result["related_titles"] == []
        assert result["combined_terms"] == []
        assert result["total_engagement"] == 0

    def test_perspective_contrarian_false(self, mock_topic):
        """Test perspective_contrarian is False when no contrarian views."""
        config = {
            "persona": {
                "perspective": {
                    "core_values": ["innovation"],
                    "contrarian_views": [],
                }
            }
        }

        result = build_template_vars_from_channel_config(config, mock_topic)

        assert result["perspective_contrarian"] is False
        assert result["perspective_biases"] == ""

    def test_default_content_values(self, mock_topic):
        """Test default content config values."""
        config = {}

        result = build_template_vars_from_channel_config(config, mock_topic)

        assert result["video_format"] == "shorts"
        assert result["target_duration"] == 55
        assert result["content_style"] == "opinion"

    def test_topic_with_none_terms(self, minimal_channel_config):
        """Test topic with None terms."""
        topic = MagicMock()
        topic.title_normalized = "test"
        topic.summary = "summary"
        topic.terms = None

        result = build_template_vars_from_channel_config(minimal_channel_config, topic)

        assert result["topic_terms"] == []

    def test_retrieved_content_is_none(self, minimal_channel_config, mock_topic):
        """Test that retrieved content fields are None (placeholder)."""
        result = build_template_vars_from_channel_config(minimal_channel_config, mock_topic)

        assert result["similar_content"] is None
        assert result["opinions"] is None
        assert result["examples"] is None
        assert result["hooks"] is None

    def test_cluster_with_empty_related_topics(self, minimal_channel_config, mock_topic):
        """Test cluster with empty related topics."""
        cluster = MagicMock()
        cluster.source_count = 2
        cluster.sources = {"reddit", "hn"}
        cluster.combined_terms = []
        cluster.total_engagement = 100
        cluster.related_topics = []

        result = build_template_vars_from_channel_config(
            minimal_channel_config, mock_topic, cluster=cluster
        )

        assert result["related_titles"] == []
