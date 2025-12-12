"""Tests for config schemas."""

import pytest
from pydantic import ValidationError

from app.config import (
    AutoApproveConfig,
    AvoidPatterns,
    ChannelConfig,
    ChannelInfo,
    CommunicationStyle,
    ContentConfig,
    NotificationConfig,
    OperationConfig,
    PersonaConfig,
    Perspective,
    RegionWeights,
    ReviewGates,
    ScheduleConfig,
    ScoringConfig,
    ScoringWeights,
    SourceOverride,
    SpeechPatterns,
    SubtitleConfig,
    TopicCollectionConfig,
    TrendConfig,
    UploadConfig,
    VisualConfig,
    VoiceConfig,
    VoiceSettings,
    YouTubeConfig,
)


@pytest.mark.unit
def test_youtube_config_valid():
    """Test valid YouTube configuration."""
    config = YouTubeConfig(channel_id="UC_TEST123", handle="@testchannel")
    assert config.channel_id == "UC_TEST123"
    assert config.handle == "@testchannel"


@pytest.mark.unit
def test_youtube_config_invalid_handle():
    """Test YouTube config with invalid handle."""
    with pytest.raises(ValidationError):
        YouTubeConfig(channel_id="UC_TEST123", handle="testchannel")


@pytest.mark.unit
def test_region_weights_valid():
    """Test valid region weights."""
    weights = RegionWeights(domestic=0.3, foreign=0.7)
    assert weights.domestic == 0.3
    assert weights.foreign == 0.7


@pytest.mark.unit
def test_region_weights_invalid_sum():
    """Test region weights with invalid sum."""
    with pytest.raises(ValidationError, match="must sum to 1.0"):
        RegionWeights(domestic=0.5, foreign=0.6)


@pytest.mark.unit
def test_scoring_weights_valid():
    """Test valid scoring weights with defaults."""
    weights = ScoringWeights()
    assert weights.source_credibility == 0.15
    assert weights.source_score == 0.15
    assert weights.freshness == 0.20
    assert weights.trend_momentum == 0.10
    assert weights.category_relevance == 0.15
    assert weights.keyword_relevance == 0.10
    assert weights.entity_relevance == 0.05
    assert weights.novelty == 0.10


@pytest.mark.unit
def test_scoring_weights_custom():
    """Test scoring weights with custom values that sum to 1.0."""
    weights = ScoringWeights(
        source_credibility=0.20,  # +0.05 from default
        source_score=0.10,  # -0.05 from default (to balance)
        freshness=0.30,  # +0.10 from default
        trend_momentum=0.05,  # -0.05 from default
        category_relevance=0.10,  # -0.05 from default (to balance)
        keyword_relevance=0.10,
        entity_relevance=0.05,
        novelty=0.10,
    )
    assert weights.source_credibility == 0.20
    assert weights.freshness == 0.30
    assert weights.source_score == 0.10


@pytest.mark.unit
def test_scoring_weights_invalid_sum():
    """Test that scoring weights must sum to 1.0."""
    with pytest.raises(ValidationError) as exc_info:
        ScoringWeights(
            source_credibility=0.50,
            freshness=0.50,
        )
    assert "must sum to 1.0" in str(exc_info.value)


@pytest.mark.unit
def test_voice_settings_valid():
    """Test valid voice settings."""
    settings = VoiceSettings(speed=1.2, pitch=5)
    assert settings.speed == 1.2
    assert settings.pitch == 5


@pytest.mark.unit
def test_voice_settings_invalid_speed():
    """Test voice settings with invalid speed."""
    with pytest.raises(ValidationError):
        VoiceSettings(speed=3.0)


@pytest.mark.unit
def test_voice_settings_invalid_pitch():
    """Test voice settings with invalid pitch."""
    with pytest.raises(ValidationError):
        VoiceSettings(pitch=25)


@pytest.mark.unit
def test_schedule_config_valid():
    """Test valid schedule configuration."""
    schedule = ScheduleConfig(
        allowed_hours=[7, 8, 9, 18, 19, 20], preferred_days=[0, 1, 2, 3, 4], min_interval_hours=6
    )
    assert schedule.allowed_hours == [7, 8, 9, 18, 19, 20]
    assert schedule.preferred_days == [0, 1, 2, 3, 4]


@pytest.mark.unit
def test_schedule_config_invalid_hours():
    """Test schedule with invalid hours."""
    with pytest.raises(ValidationError, match="Hours must be between 0 and 23"):
        ScheduleConfig(allowed_hours=[7, 8, 25], min_interval_hours=6)


@pytest.mark.unit
def test_schedule_config_invalid_days():
    """Test schedule with invalid days."""
    with pytest.raises(ValidationError, match="Days must be between 0"):
        ScheduleConfig(allowed_hours=[7, 8], preferred_days=[0, 1, 7], min_interval_hours=6)


@pytest.mark.unit
def test_upload_config_valid():
    """Test valid upload configuration."""
    schedule = ScheduleConfig(allowed_hours=[7, 8, 9], min_interval_hours=6)
    upload = UploadConfig(
        daily_target=2,
        max_daily=3,
        schedule=schedule,
        default_hashtags=["tech", "dev"],
        default_category="28",
    )
    assert upload.daily_target == 2
    assert upload.max_daily == 3


@pytest.mark.unit
def test_upload_config_max_less_than_target():
    """Test upload config with max_daily < daily_target."""
    schedule = ScheduleConfig(allowed_hours=[7, 8, 9], min_interval_hours=6)
    with pytest.raises(ValidationError, match="max_daily must be >= daily_target"):
        UploadConfig(daily_target=5, max_daily=3, schedule=schedule)


@pytest.mark.unit
def test_visual_config_valid():
    """Test valid visual configuration."""
    visual = VisualConfig(
        source_priority=["stock_video", "ai_image", "solid_color"], fallback_color="#1a1a2e"
    )
    assert visual.source_priority == ["stock_video", "ai_image", "solid_color"]
    assert visual.fallback_color == "#1a1a2e"


@pytest.mark.unit
def test_visual_config_invalid_color():
    """Test visual config with invalid color."""
    with pytest.raises(ValidationError):
        VisualConfig(source_priority=["stock_video"], fallback_color="invalid")


@pytest.mark.unit
def test_subtitle_config_defaults():
    """Test subtitle config default values."""
    subtitle = SubtitleConfig()
    assert subtitle.font_name == "Pretendard"
    assert subtitle.font_size == 48
    assert subtitle.position == "bottom"
    assert subtitle.highlight_current_word is True


@pytest.mark.unit
def test_channel_info_valid():
    """Test valid channel info."""
    channel = ChannelInfo(
        id="test-channel",
        name="Test Channel",
        description="A test channel",
        youtube=YouTubeConfig(channel_id="UC_TEST", handle="@test"),
    )
    assert channel.id == "test-channel"
    assert channel.name == "Test Channel"
    assert channel.youtube.channel_id == "UC_TEST"


@pytest.mark.unit
def test_channel_info_invalid_id():
    """Test channel info with invalid ID."""
    with pytest.raises(ValidationError):
        ChannelInfo(
            id="Invalid_ID",  # Uppercase not allowed
            name="Test",
            description="Test",
            youtube=YouTubeConfig(channel_id="UC_TEST", handle="@test"),
        )


@pytest.mark.unit
def test_voice_config_valid():
    """Test valid voice configuration."""
    voice = VoiceConfig(
        gender="male",
        service="edge-tts",
        voice_id="ko-KR-InJoonNeural",
        settings=VoiceSettings(speed=1.2, pitch=5),
    )
    assert voice.gender == "male"
    assert voice.service == "edge-tts"
    assert voice.settings.speed == 1.2


@pytest.mark.unit
def test_speech_patterns_valid():
    """Test valid speech patterns."""
    patterns = SpeechPatterns(
        sentence_endings=["~해요", "~거든요"],
        connectors=["근데", "사실"],
        emphasis_words=["진짜", "솔직히"],
    )
    assert len(patterns.sentence_endings) == 2
    assert "근데" in patterns.connectors


@pytest.mark.unit
def test_avoid_patterns_valid():
    """Test valid avoid patterns."""
    avoid = AvoidPatterns(words=["혁신적인", "패러다임"], styles=["클릭베이트"])
    assert len(avoid.words) == 2
    assert "클릭베이트" in avoid.styles


@pytest.mark.unit
def test_communication_style_valid():
    """Test valid communication style."""
    comm = CommunicationStyle(
        tone="friendly",
        formality="casual",
        speech_patterns=SpeechPatterns(),
        avoid_patterns=AvoidPatterns(),
    )
    assert comm.tone == "friendly"
    assert comm.formality == "casual"


@pytest.mark.unit
def test_perspective_valid():
    """Test valid perspective."""
    perspective = Perspective(
        approach="practical", core_values=["실용성"], contrarian_views=["AI 만능론 반대"]
    )
    assert perspective.approach == "practical"
    assert len(perspective.core_values) == 1


@pytest.mark.unit
def test_persona_config_valid():
    """Test valid persona configuration."""
    persona = PersonaConfig(
        name="TestBot",
        tagline="Testing",
        voice=VoiceConfig(gender="male", service="edge-tts", voice_id="test"),
        communication=CommunicationStyle(tone="friendly", formality="casual"),
        perspective=Perspective(approach="practical"),
    )
    assert persona.name == "TestBot"
    assert persona.voice.service == "edge-tts"


@pytest.mark.unit
def test_source_override_valid():
    """Test valid source override."""
    override = SourceOverride(
        weight=1.5, params={"subreddits": ["programming"]}, filters={"min_score": 100}
    )
    assert override.weight == 1.5
    assert "subreddits" in override.params


@pytest.mark.unit
def test_trend_config_valid():
    """Test valid trend configuration."""
    trend = TrendConfig(
        enabled=True, sources=["google_trends"], regions=["KR", "US"], min_growth_rate=50
    )
    assert trend.enabled is True
    assert len(trend.regions) == 2


@pytest.mark.unit
def test_topic_collection_config_valid():
    """Test valid topic collection configuration."""
    topic_config = TopicCollectionConfig(
        region_weights=RegionWeights(domestic=0.3, foreign=0.7),
        enabled_sources=["reddit", "hackernews"],
        source_overrides={},
        trend_config=TrendConfig(),
    )
    assert len(topic_config.enabled_sources) == 2
    assert topic_config.region_weights.domestic == 0.3


@pytest.mark.unit
def test_scoring_config_valid():
    """Test valid scoring configuration with defaults."""
    scoring = ScoringConfig()
    assert scoring.weights.source_credibility == 0.15
    assert scoring.freshness_half_life_hours == 24
    assert scoring.freshness_min == 0.1
    assert scoring.min_score_threshold == 30


@pytest.mark.unit
def test_scoring_config_custom():
    """Test scoring configuration with custom values."""
    scoring = ScoringConfig(
        weights=ScoringWeights(
            source_credibility=0.15,
            source_score=0.05,  # -0.10 from default
            freshness=0.30,  # +0.10 from default (to balance)
            trend_momentum=0.10,
            category_relevance=0.15,
            keyword_relevance=0.10,
            entity_relevance=0.05,
            novelty=0.10,
        ),
        freshness_half_life_hours=12,
        target_categories=["tech", "ai"],
    )
    assert scoring.weights.freshness == 0.30
    assert scoring.freshness_half_life_hours == 12
    assert scoring.target_categories == ["tech", "ai"]


@pytest.mark.unit
def test_content_config_valid():
    """Test valid content configuration."""
    content = ContentConfig(
        format="shorts",
        target_duration=55,
        visual=VisualConfig(source_priority=["stock_video"], fallback_color="#1a1a2e"),
        subtitle=SubtitleConfig(),
    )
    assert content.format == "shorts"
    assert content.target_duration == 55


@pytest.mark.unit
def test_review_gates_defaults():
    """Test review gates default values."""
    gates = ReviewGates()
    assert gates.topic == "auto"
    assert gates.script == "manual"
    assert gates.video == "manual"
    assert gates.upload == "auto"


@pytest.mark.unit
def test_auto_approve_config_defaults():
    """Test auto-approve config defaults."""
    config = AutoApproveConfig()
    assert config.max_risk_score == 20
    assert config.require_series_match is False


@pytest.mark.unit
def test_notification_config_defaults():
    """Test notification config defaults."""
    config = NotificationConfig()
    assert config.telegram is True
    assert config.new_review is True
    assert config.daily_summary is True


@pytest.mark.unit
def test_operation_config_defaults():
    """Test operation config with defaults."""
    config = OperationConfig()
    assert isinstance(config.review_gates, ReviewGates)
    assert isinstance(config.auto_approve, AutoApproveConfig)
    assert isinstance(config.notifications, NotificationConfig)


@pytest.mark.unit
def test_full_channel_config(tmp_path):
    """Test complete channel configuration."""
    config_data = {
        "channel": {
            "id": "test-channel",
            "name": "Test Channel",
            "description": "A test channel",
            "youtube": {"channel_id": "UC_TEST", "handle": "@test"},
        },
        "persona": {
            "name": "TestBot",
            "tagline": "Testing is cool",
            "voice": {
                "gender": "male",
                "service": "edge-tts",
                "voice_id": "ko-KR-InJoonNeural",
                "settings": {"speed": 1.0, "pitch": 0},
            },
            "communication": {
                "tone": "friendly",
                "formality": "casual",
                "speech_patterns": {
                    "sentence_endings": ["~해요"],
                    "connectors": ["근데"],
                    "emphasis_words": ["진짜"],
                },
                "avoid_patterns": {"words": ["혁신적인"], "styles": ["클릭베이트"]},
            },
            "perspective": {
                "approach": "practical",
                "core_values": ["실용성"],
                "contrarian_views": ["AI 만능론 반대"],
            },
        },
        "topic_collection": {
            "region_weights": {"domestic": 0.3, "foreign": 0.7},
            "enabled_sources": ["reddit", "hackernews"],
            "source_overrides": {},
            "trend_config": {"enabled": True, "sources": [], "regions": [], "min_growth_rate": 50},
        },
        "scoring": {
            "weights": {
                "source_credibility": 0.15,
                "source_score": 0.15,
                "freshness": 0.20,
                "trend_momentum": 0.10,
                "category_relevance": 0.15,
                "keyword_relevance": 0.10,
                "entity_relevance": 0.05,
                "novelty": 0.10,
            },
            "freshness_half_life_hours": 24,
            "min_score_threshold": 30,
        },
        "content": {
            "format": "shorts",
            "target_duration": 55,
            "visual": {"source_priority": ["stock_video"], "fallback_color": "#1a1a2e"},
            "subtitle": {},
        },
        "upload": {
            "daily_target": 2,
            "max_daily": 3,
            "schedule": {"allowed_hours": [7, 8, 9], "min_interval_hours": 6},
            "default_hashtags": ["tech"],
            "default_category": "28",
        },
        "operation": {},
    }

    config = ChannelConfig(**config_data)

    assert config.channel.id == "test-channel"
    assert config.persona.name == "TestBot"
    assert config.topic_collection.region_weights.domestic == 0.3
    assert config.scoring.freshness_half_life_hours == 24
    assert config.scoring.min_score_threshold == 30
    assert config.content.target_duration == 55
    assert config.upload.daily_target == 2
    assert config.operation.review_gates.topic == "auto"
