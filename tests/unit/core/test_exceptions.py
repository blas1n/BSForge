"""Tests for app.core.exceptions module."""

import pytest

from app.core.exceptions import (
    BSForgeError,
    ConfigError,
    ConfigNotFoundError,
    ConfigValidationError,
    ContentError,
    ContentGenerationError,
    ContentValidationError,
    DatabaseError,
    ExternalAPIError,
    RateLimitError,
    RecordAlreadyExistsError,
    RecordNotFoundError,
    ServiceError,
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
