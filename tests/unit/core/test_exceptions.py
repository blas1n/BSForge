"""Tests for app.core.exceptions module."""

import pytest

from app.core.exceptions import (
    AuthError,
    BGMDownloadError,
    BGMError,
    BGMNotFoundError,
    BSForgeError,
    ConfigError,
    ConfigNotFoundError,
    ConfigValidationError,
    ContentError,
    ContentGenerationError,
    ContentValidationError,
    DatabaseError,
    ExternalAPIError,
    InvalidCredentialsError,
    QuotaExceededError,
    RateLimitError,
    RecordAlreadyExistsError,
    RecordNotFoundError,
    ServiceError,
    TokenExpiredError,
    TTSError,
    UnsafeContentError,
    UploadError,
    VideoError,
    VideoRenderError,
    YouTubeAPIError,
)


@pytest.mark.unit
def test_bsforge_error():
    """Test base BSForgeError exception."""
    error = BSForgeError("Test error")
    assert str(error) == "Test error"
    assert isinstance(error, Exception)


@pytest.mark.unit
def test_record_not_found_error():
    """Test RecordNotFoundError with model and record_id."""
    error = RecordNotFoundError(model="User", record_id="123")

    assert error.model == "User"
    assert error.record_id == "123"
    assert "User" in str(error)
    assert "123" in str(error)
    assert isinstance(error, DatabaseError)
    assert isinstance(error, BSForgeError)


@pytest.mark.unit
def test_record_already_exists_error():
    """Test RecordAlreadyExistsError with model, field, and value."""
    error = RecordAlreadyExistsError(model="User", field="email", value="test@example.com")

    assert error.model == "User"
    assert error.field == "email"
    assert error.value == "test@example.com"
    assert "User" in str(error)
    assert "email" in str(error)
    assert isinstance(error, DatabaseError)
    assert isinstance(error, BSForgeError)


@pytest.mark.unit
def test_config_errors():
    """Test configuration-related errors."""
    error = ConfigError("Config error")
    assert isinstance(error, BSForgeError)

    error = ConfigValidationError("Validation failed")
    assert isinstance(error, ConfigError)

    error = ConfigNotFoundError("Config not found")
    assert isinstance(error, ConfigError)


@pytest.mark.unit
def test_external_api_error():
    """Test ExternalAPIError with service and status code."""
    error = ExternalAPIError(service="YouTube", message="API request failed", status_code=429)

    assert error.service == "YouTube"
    assert error.status_code == 429
    assert "YouTube" in str(error)
    assert "API request failed" in str(error)
    assert isinstance(error, ServiceError)
    assert isinstance(error, BSForgeError)


@pytest.mark.unit
def test_external_api_error_without_status():
    """Test ExternalAPIError without status code."""
    error = ExternalAPIError(service="Anthropic", message="Connection failed")

    assert error.service == "Anthropic"
    assert error.status_code is None
    assert isinstance(error, ServiceError)


@pytest.mark.unit
def test_rate_limit_error():
    """Test RateLimitError."""
    error = RateLimitError("Rate limit exceeded")
    assert isinstance(error, ServiceError)
    assert isinstance(error, BSForgeError)


@pytest.mark.unit
def test_content_errors():
    """Test content-related errors."""
    error = ContentError("Content error")
    assert isinstance(error, BSForgeError)

    error = ContentGenerationError("Generation failed")
    assert isinstance(error, ContentError)

    error = ContentValidationError("Validation failed")
    assert isinstance(error, ContentError)


@pytest.mark.unit
def test_unsafe_content_error():
    """Test UnsafeContentError with reason and risk score."""
    error = UnsafeContentError(reason="Contains profanity", risk_score=85)

    assert error.reason == "Contains profanity"
    assert error.risk_score == 85
    assert "Contains profanity" in str(error)
    assert "85" in str(error)
    assert isinstance(error, ContentError)
    assert isinstance(error, BSForgeError)


@pytest.mark.unit
def test_video_errors():
    """Test video generation errors."""
    error = VideoError("Video error")
    assert isinstance(error, BSForgeError)

    error = TTSError("TTS failed")
    assert isinstance(error, VideoError)

    error = VideoRenderError("Render failed")
    assert isinstance(error, VideoError)


@pytest.mark.unit
def test_upload_errors():
    """Test upload-related errors."""
    error = UploadError("Upload error")
    assert isinstance(error, BSForgeError)

    error = YouTubeAPIError("YouTube API failed")
    assert isinstance(error, UploadError)


@pytest.mark.unit
def test_exception_hierarchy():
    """Test exception inheritance hierarchy."""
    # All custom exceptions should inherit from BSForgeError
    exceptions = [
        DatabaseError("test"),
        RecordNotFoundError(model="Model", record_id="id"),
        RecordAlreadyExistsError(model="Model", field="field", value="value"),
        ConfigError("test"),
        ConfigValidationError("test"),
        ConfigNotFoundError("test"),
        ServiceError("test"),
        ExternalAPIError(service="service", message="msg"),
        RateLimitError("test"),
        ContentError("test"),
        ContentGenerationError("test"),
        ContentValidationError("test"),
        UnsafeContentError("reason", 50),
        VideoError("test"),
        TTSError("test"),
        VideoRenderError("test"),
        UploadError("test"),
        YouTubeAPIError("test"),
    ]

    for exc in exceptions:
        assert isinstance(exc, BSForgeError)
        assert isinstance(exc, Exception)


# ============================================
# Extended exception tests for full coverage
# ============================================


@pytest.mark.unit
def test_bsforge_error_with_context():
    """Test BSForgeError with context dict."""
    error = BSForgeError("Test error", context={"key": "value"})
    assert error.context == {"key": "value"}


@pytest.mark.unit
def test_bsforge_error_with_context_method():
    """Test with_context method."""
    error = BSForgeError("Test error")
    result = error.with_context(user_id="123", action="test")

    assert result is error  # Method chaining
    assert error.context["user_id"] == "123"
    assert error.context["action"] == "test"


@pytest.mark.unit
def test_bsforge_error_to_dict():
    """Test to_dict serialization."""
    error = BSForgeError("Test error", context={"key": "value"})
    result = error.to_dict()

    assert result["error_type"] == "BSForgeError"
    assert result["message"] == "Test error"
    assert result["context"] == {"key": "value"}


@pytest.mark.unit
def test_database_error_with_operation():
    """Test DatabaseError with operation context."""
    error = DatabaseError("DB failed", operation="insert")

    assert error.context["operation"] == "insert"
    assert "DB failed" in str(error)


@pytest.mark.unit
def test_config_error_with_path():
    """Test ConfigError with config_path."""
    error = ConfigError("Config error", config_path="/path/to/config.yaml")

    assert error.context["config_path"] == "/path/to/config.yaml"


@pytest.mark.unit
def test_config_validation_error_structured():
    """Test ConfigValidationError with structured parameters."""
    error = ConfigValidationError(
        field="port",
        value=99999,
        reason="Port must be between 1-65535",
        config_path="/app/config.yaml",
    )

    assert error.field == "port"
    assert error.value == 99999
    assert error.reason == "Port must be between 1-65535"
    assert "port" in str(error)
    assert error.context["field"] == "port"


@pytest.mark.unit
def test_config_validation_error_simple():
    """Test ConfigValidationError with simple message."""
    error = ConfigValidationError("Simple validation error")

    assert "Simple validation error" in str(error)


@pytest.mark.unit
def test_config_validation_error_default():
    """Test ConfigValidationError with no parameters."""
    error = ConfigValidationError()

    assert "Configuration validation failed" in str(error)


@pytest.mark.unit
def test_config_not_found_error():
    """Test ConfigNotFoundError attributes."""
    error = ConfigNotFoundError("database_url", config_path="/app/config.yaml")

    assert error.config_key == "database_url"
    assert "database_url" in str(error)
    assert error.context["config_key"] == "database_url"


@pytest.mark.unit
def test_service_error_with_name():
    """Test ServiceError with service_name."""
    error = ServiceError("Service failed", service_name="youtube")

    assert error.context["service_name"] == "youtube"


@pytest.mark.unit
def test_external_api_error_full():
    """Test ExternalAPIError with all parameters."""
    error = ExternalAPIError(
        service="YouTube",
        message="API failed",
        status_code=500,
        endpoint="/videos/upload",
        response_body="Error response body" * 100,  # Long body
    )

    assert error.service == "YouTube"
    assert error.status_code == 500
    assert error.endpoint == "/videos/upload"
    assert len(error.context["response_body"]) <= 500  # Truncated


@pytest.mark.unit
def test_rate_limit_error_with_retry():
    """Test RateLimitError with retry_after."""
    error = RateLimitError(service="api", retry_after=60)

    assert error.service == "api"
    assert error.retry_after == 60
    assert "60" in str(error)
    assert "retry after" in str(error).lower()


@pytest.mark.unit
def test_content_error_with_type():
    """Test ContentError with content_type."""
    error = ContentError("Content failed", content_type="script")

    assert error.context["content_type"] == "script"


@pytest.mark.unit
def test_content_generation_error_full():
    """Test ContentGenerationError with all parameters."""
    error = ContentGenerationError(
        message="Generation failed",
        stage="inference",
        model="gpt-4",
        content_type="script",
    )

    assert error.stage == "inference"
    assert error.model == "gpt-4"
    assert error.context["stage"] == "inference"
    assert error.context["model"] == "gpt-4"


@pytest.mark.unit
def test_content_validation_error_with_errors():
    """Test ContentValidationError with validation_errors list."""
    error = ContentValidationError(
        message="Validation failed",
        validation_errors=["Error 1", "Error 2"],
        content_type="video",
    )

    assert error.validation_errors == ["Error 1", "Error 2"]
    assert error.context["validation_errors"] == ["Error 1", "Error 2"]


@pytest.mark.unit
def test_unsafe_content_error_with_words():
    """Test UnsafeContentError with flagged_words."""
    error = UnsafeContentError(
        reason="Profanity detected",
        risk_score=90,
        flagged_words=["word1", "word2"],
    )

    assert error.reason == "Profanity detected"
    assert error.risk_score == 90
    assert error.flagged_words == ["word1", "word2"]
    assert error.context["flagged_words"] == ["word1", "word2"]


@pytest.mark.unit
def test_video_error_with_ids():
    """Test VideoError with video_id and script_id."""
    error = VideoError("Video error", video_id="vid-123", script_id="scr-456")

    assert error.context["video_id"] == "vid-123"
    assert error.context["script_id"] == "scr-456"


@pytest.mark.unit
def test_tts_error_full():
    """Test TTSError with all parameters."""
    error = TTSError(
        message="TTS failed",
        engine="edge-tts",
        voice_id="ko-KR-SunHiNeural",
        video_id="vid-123",
    )

    assert error.engine == "edge-tts"
    assert error.voice_id == "ko-KR-SunHiNeural"
    assert error.context["engine"] == "edge-tts"


@pytest.mark.unit
def test_video_render_error_full():
    """Test VideoRenderError with all parameters."""
    error = VideoRenderError(
        message="Render failed",
        stage="compose",
        ffmpeg_error="FFmpeg stderr output" * 100,  # Long error
        video_id="vid-123",
    )

    assert error.stage == "compose"
    assert error.ffmpeg_error is not None
    assert len(error.context["ffmpeg_error"]) <= 500  # Truncated


@pytest.mark.unit
def test_bgm_error():
    """Test BGMError base class."""
    error = BGMError("BGM error", track_name="lofi-beats")

    assert error.context["track_name"] == "lofi-beats"
    assert isinstance(error, VideoError)


@pytest.mark.unit
def test_bgm_download_error():
    """Test BGMDownloadError with all attributes."""
    error = BGMDownloadError(
        message="Download failed",
        track_name="lofi-beats",
        youtube_url="https://youtube.com/watch?v=abc123",
    )

    assert error.track_name == "lofi-beats"
    assert error.youtube_url == "https://youtube.com/watch?v=abc123"
    assert isinstance(error, BGMError)


@pytest.mark.unit
def test_bgm_not_found_error():
    """Test BGMNotFoundError default message."""
    error = BGMNotFoundError()

    assert "No BGM tracks available" in str(error)
    assert isinstance(error, BGMError)


@pytest.mark.unit
def test_upload_error_with_platform():
    """Test UploadError with platform."""
    error = UploadError("Upload failed", video_id="vid-123", platform="youtube")

    assert error.context["video_id"] == "vid-123"
    assert error.context["platform"] == "youtube"


@pytest.mark.unit
def test_youtube_api_error_full():
    """Test YouTubeAPIError with all parameters."""
    error = YouTubeAPIError(
        message="API error",
        error_code="quotaExceeded",
        error_reason="The request cannot be completed because you have exceeded your quota.",
        video_id="vid-123",
    )

    assert error.error_code == "quotaExceeded"
    assert error.error_reason is not None
    assert error.context["error_code"] == "quotaExceeded"


@pytest.mark.unit
def test_quota_exceeded_error():
    """Test QuotaExceededError with quota info."""
    error = QuotaExceededError(
        quota_limit=10000,
        quota_used=10001,
        reset_time="2025-01-15T00:00:00Z",
    )

    assert error.quota_limit == 10000
    assert error.quota_used == 10001
    assert error.reset_time == "2025-01-15T00:00:00Z"
    assert isinstance(error, UploadError)


@pytest.mark.unit
def test_auth_error():
    """Test AuthError base class."""
    error = AuthError("Auth failed", user_id="user-123")

    assert error.context["user_id"] == "user-123"
    assert isinstance(error, BSForgeError)


@pytest.mark.unit
def test_invalid_credentials_error():
    """Test InvalidCredentialsError."""
    error = InvalidCredentialsError(
        credential_type="api_key",
        user_id="user-123",
    )

    assert error.credential_type == "api_key"
    assert "Invalid credentials" in str(error)
    assert isinstance(error, AuthError)


@pytest.mark.unit
def test_token_expired_error():
    """Test TokenExpiredError."""
    error = TokenExpiredError(
        token_type="access",
        expired_at="2025-01-15T12:00:00Z",
        user_id="user-123",
    )

    assert error.token_type == "access"
    assert error.expired_at == "2025-01-15T12:00:00Z"
    assert isinstance(error, AuthError)
