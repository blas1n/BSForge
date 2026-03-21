"""Tests for channel-driven demo pipeline helpers."""

from pathlib import Path

import pytest
import yaml

from app.config.persona import PersonaConfig
from app.services.collector.base import RawTopic


class TestLoadChannelConfig:
    """Test channel config loading."""

    def test_demo_tech_config_loads(self) -> None:
        """demo_tech.yaml loads and has required sections."""
        config_path = Path("config/channels/demo_tech.yaml")
        assert config_path.exists(), "demo_tech.yaml must exist"

        cfg = yaml.safe_load(config_path.read_text())
        assert "channel" in cfg
        assert "persona" in cfg
        assert "topic_collection" in cfg
        assert "content" in cfg

    def test_persona_config_from_yaml(self) -> None:
        """PersonaConfig can be constructed from channel YAML."""
        config_path = Path("config/channels/demo_tech.yaml")
        cfg = yaml.safe_load(config_path.read_text())

        persona = PersonaConfig(**cfg["persona"])
        assert persona.name == "테크브로"
        assert persona.voice.voice_id == "ko-KR-InJoonNeural"
        assert persona.communication.tone == "friendly"


class TestTopicSelection:
    """Test topic selection from collected raw topics."""

    def test_pick_best_topic_by_score(self) -> None:
        """pick_best_topic returns highest-scored topic."""
        from scripts.demo_pipeline import pick_best_topic

        topics = [
            RawTopic(
                source_id="1",
                source_url="https://example.com/a",
                title="Low score topic",
                metrics={"score": 10, "comments": 5},
            ),
            RawTopic(
                source_id="2",
                source_url="https://example.com/b",
                title="High score topic",
                metrics={"score": 500, "comments": 100},
            ),
            RawTopic(
                source_id="3",
                source_url="https://example.com/c",
                title="Medium score topic",
                metrics={"score": 100, "comments": 30},
            ),
        ]

        best = pick_best_topic(topics)
        assert best is not None
        assert best.title == "High score topic"

    def test_pick_best_topic_empty_returns_none(self) -> None:
        """pick_best_topic returns None for empty list."""
        from scripts.demo_pipeline import pick_best_topic

        assert pick_best_topic([]) is None

    def test_pick_best_topic_uses_comments_as_tiebreaker(self) -> None:
        """When scores tie, topic with more comments wins."""
        from scripts.demo_pipeline import pick_best_topic

        topics = [
            RawTopic(
                source_id="1",
                source_url="https://example.com/a",
                title="Less comments",
                metrics={"score": 100, "comments": 10},
            ),
            RawTopic(
                source_id="2",
                source_url="https://example.com/b",
                title="More comments",
                metrics={"score": 100, "comments": 50},
            ),
        ]

        best = pick_best_topic(topics)
        assert best is not None
        assert best.title == "More comments"

    def test_pick_best_topic_missing_metrics(self) -> None:
        """Topics with missing metrics treated as zero."""
        from scripts.demo_pipeline import pick_best_topic

        topics = [
            RawTopic(
                source_id="1",
                source_url="https://example.com/a",
                title="No metrics",
                metrics={},
            ),
            RawTopic(
                source_id="2",
                source_url="https://example.com/b",
                title="Has metrics",
                metrics={"score": 10},
            ),
        ]

        best = pick_best_topic(topics)
        assert best is not None
        assert best.title == "Has metrics"


class TestLoadChannelConfigFunction:
    """Test load_channel_config helper."""

    def test_load_channel_config_returns_dict(self) -> None:
        """load_channel_config returns parsed YAML dict."""
        from scripts.demo_pipeline import load_channel_config

        cfg = load_channel_config(Path("config/channels/demo_tech.yaml"))
        assert isinstance(cfg, dict)
        assert cfg["channel"]["id"] == "demo-tech"

    def test_load_channel_config_missing_file_raises(self) -> None:
        """load_channel_config raises FileNotFoundError for missing file."""
        from scripts.demo_pipeline import load_channel_config

        with pytest.raises(FileNotFoundError):
            load_channel_config(Path("config/channels/nonexistent.yaml"))
