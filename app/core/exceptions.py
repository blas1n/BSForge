"""Custom exceptions for BSForge application.

This module defines all custom exceptions used throughout the application.
All exceptions inherit from BSForgeError for easy catching.

Exception classes include context dictionaries for structured logging
and debugging. Use the `context` property to access additional details.
"""

from typing import Any


class BSForgeError(Exception):
    """Base exception for all BSForge errors.

    All custom exceptions in the application should inherit from this class.
    Provides a context dictionary for structured error information.

    Attributes:
        context: Dictionary with additional error context

    Example:
        >>> try:
        ...     raise BSForgeError("Something went wrong", context={"user_id": "123"})
        ... except BSForgeError as e:
        ...     print(f"Error: {e}, Context: {e.context}")
    """

    def __init__(self, message: str, context: dict[str, Any] | None = None) -> None:
        """Initialize BSForgeError.

        Args:
            message: Error message
            context: Optional dictionary with additional context
        """
        self.context = context or {}
        super().__init__(message)

    def with_context(self, **kwargs: Any) -> "BSForgeError":
        """Add additional context to the exception.

        Args:
            **kwargs: Key-value pairs to add to context

        Returns:
            Self for method chaining
        """
        self.context.update(kwargs)
        return self

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to dictionary for logging/serialization.

        Returns:
            Dictionary with error type, message, and context
        """
        return {
            "error_type": self.__class__.__name__,
            "message": str(self),
            "context": self.context,
        }


# ============================================
# Database Errors
# ============================================


class DatabaseError(BSForgeError):
    """Base exception for database-related errors."""

    def __init__(
        self,
        message: str,
        context: dict[str, Any] | None = None,
        operation: str | None = None,
    ) -> None:
        """Initialize DatabaseError.

        Args:
            message: Error message
            context: Additional context
            operation: Database operation that failed (e.g., "insert", "update")
        """
        ctx = context or {}
        if operation:
            ctx["operation"] = operation
        super().__init__(message, context=ctx)


class RecordNotFoundError(DatabaseError):
    """Raised when a database record is not found.

    Attributes:
        model: The model class that was queried
        record_id: The ID that was not found
    """

    def __init__(
        self,
        model: str,
        record_id: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Initialize RecordNotFoundError.

        Args:
            model: Name of the model class
            record_id: ID that was not found
            context: Additional context
        """
        ctx = context or {}
        ctx.update({"model": model, "record_id": record_id})
        super().__init__(f"{model} with id={record_id} not found", context=ctx)
        self.model = model
        self.record_id = record_id


class RecordAlreadyExistsError(DatabaseError):
    """Raised when attempting to create a duplicate record.

    Attributes:
        model: The model class
        field: Field that caused the conflict
        value: Value that already exists
    """

    def __init__(
        self,
        model: str,
        field: str,
        value: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Initialize RecordAlreadyExistsError.

        Args:
            model: Name of the model class
            field: Field that caused the conflict
            value: Value that already exists
            context: Additional context
        """
        ctx = context or {}
        ctx.update({"model": model, "field": field, "value": value})
        super().__init__(
            f"{model} with {field}={value} already exists",
            context=ctx,
        )
        self.model = model
        self.field = field
        self.value = value


# ============================================
# Configuration Errors
# ============================================


class ConfigError(BSForgeError):
    """Base exception for configuration-related errors."""

    def __init__(
        self,
        message: str,
        config_path: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Initialize ConfigError.

        Args:
            message: Error message
            config_path: Path to the config file/key
            context: Additional context
        """
        ctx = context or {}
        if config_path:
            ctx["config_path"] = config_path
        super().__init__(message, context=ctx)


class ConfigValidationError(ConfigError):
    """Raised when configuration validation fails.

    Supports two usage patterns:
    1. Simple: ConfigValidationError("error message")
    2. Structured: ConfigValidationError(field="name", value="x", reason="invalid")

    Attributes:
        field: Field that failed validation (optional)
        value: Invalid value (optional)
        reason: Validation failure reason (optional)
    """

    def __init__(
        self,
        message: str | None = None,
        *,
        field: str | None = None,
        value: Any = None,
        reason: str | None = None,
        config_path: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Initialize ConfigValidationError.

        Args:
            message: Error message (for simple usage)
            field: Field that failed validation
            value: Invalid value
            reason: Validation failure reason
            config_path: Path to config file
            context: Additional context
        """
        ctx = context or {}

        # Store attributes
        self.field = field
        self.value = value
        self.reason = reason

        # Build message based on provided parameters
        if field and reason:
            ctx.update({"field": field, "reason": reason})
            if value is not None:
                ctx["value"] = str(value)
            final_message = f"Config validation failed for '{field}': {reason}"
        elif message:
            final_message = message
        else:
            final_message = "Configuration validation failed"

        super().__init__(final_message, config_path=config_path, context=ctx)


class ConfigNotFoundError(ConfigError):
    """Raised when a required configuration is not found.

    Attributes:
        config_key: The configuration key that was not found
    """

    def __init__(
        self,
        config_key: str,
        config_path: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Initialize ConfigNotFoundError.

        Args:
            config_key: Configuration key that was not found
            config_path: Path to config file
            context: Additional context
        """
        ctx = context or {}
        ctx["config_key"] = config_key
        super().__init__(
            f"Configuration '{config_key}' not found",
            config_path=config_path,
            context=ctx,
        )
        self.config_key = config_key


# ============================================
# Service Errors
# ============================================


class ServiceError(BSForgeError):
    """Base exception for service-related errors."""

    def __init__(
        self,
        message: str,
        service_name: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Initialize ServiceError.

        Args:
            message: Error message
            service_name: Name of the service
            context: Additional context
        """
        ctx = context or {}
        if service_name:
            ctx["service_name"] = service_name
        super().__init__(message, context=ctx)


class ExternalAPIError(ServiceError):
    """Raised when an external API call fails.

    Attributes:
        service: Name of the external service
        status_code: HTTP status code (if applicable)
        endpoint: API endpoint that was called
    """

    def __init__(
        self,
        service: str,
        message: str,
        status_code: int | None = None,
        endpoint: str | None = None,
        response_body: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Initialize ExternalAPIError.

        Args:
            service: Name of the external service
            message: Error message
            status_code: HTTP status code (optional)
            endpoint: API endpoint (optional)
            response_body: Response body for debugging (optional)
            context: Additional context
        """
        ctx = context or {}
        ctx["service"] = service
        if status_code is not None:
            ctx["status_code"] = status_code
        if endpoint:
            ctx["endpoint"] = endpoint
        if response_body:
            ctx["response_body"] = response_body[:500]  # Truncate long responses

        self.service = service
        self.status_code = status_code
        self.endpoint = endpoint

        super().__init__(f"{service} API error: {message}", service_name=service, context=ctx)


class RateLimitError(ServiceError):
    """Raised when rate limit is exceeded.

    Attributes:
        service: Service that rate limited
        retry_after: Seconds to wait before retrying
    """

    def __init__(
        self,
        service: str,
        retry_after: int | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Initialize RateLimitError.

        Args:
            service: Service that rate limited
            retry_after: Seconds to wait before retrying
            context: Additional context
        """
        ctx = context or {}
        ctx["service"] = service
        if retry_after is not None:
            ctx["retry_after"] = retry_after

        self.service = service
        self.retry_after = retry_after

        message = f"Rate limit exceeded for {service}"
        if retry_after:
            message += f" (retry after {retry_after}s)"

        super().__init__(message, service_name=service, context=ctx)


# ============================================
# Content Errors
# ============================================


class ContentError(BSForgeError):
    """Base exception for content-related errors."""

    def __init__(
        self,
        message: str,
        content_type: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Initialize ContentError.

        Args:
            message: Error message
            content_type: Type of content (e.g., "script", "video", "topic")
            context: Additional context
        """
        ctx = context or {}
        if content_type:
            ctx["content_type"] = content_type
        super().__init__(message, context=ctx)


class ContentGenerationError(ContentError):
    """Raised when content generation fails.

    Attributes:
        stage: Generation stage that failed
        model: Model used for generation
    """

    def __init__(
        self,
        message: str,
        stage: str | None = None,
        model: str | None = None,
        content_type: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Initialize ContentGenerationError.

        Args:
            message: Error message
            stage: Generation stage (e.g., "prompt", "inference", "parsing")
            model: Model used
            content_type: Type of content
            context: Additional context
        """
        ctx = context or {}
        if stage:
            ctx["stage"] = stage
        if model:
            ctx["model"] = model

        self.stage = stage
        self.model = model

        super().__init__(message, content_type=content_type, context=ctx)


class ContentValidationError(ContentError):
    """Raised when content validation fails.

    Attributes:
        validation_errors: List of validation error details
    """

    def __init__(
        self,
        message: str,
        validation_errors: list[str] | None = None,
        content_type: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Initialize ContentValidationError.

        Args:
            message: Error message
            validation_errors: List of validation error details
            content_type: Type of content
            context: Additional context
        """
        ctx = context or {}
        if validation_errors:
            ctx["validation_errors"] = validation_errors

        self.validation_errors = validation_errors or []

        super().__init__(message, content_type=content_type, context=ctx)


class UnsafeContentError(ContentError):
    """Raised when content is flagged as unsafe.

    Attributes:
        reason: Reason why content is unsafe
        risk_score: Risk score (0-100)
        flagged_words: Words that triggered the flag
    """

    def __init__(
        self,
        reason: str,
        risk_score: int,
        flagged_words: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Initialize UnsafeContentError.

        Args:
            reason: Reason why content is unsafe
            risk_score: Risk score (0-100)
            flagged_words: Words that triggered the flag
            context: Additional context
        """
        ctx = context or {}
        ctx.update({"reason": reason, "risk_score": risk_score})
        if flagged_words:
            ctx["flagged_words"] = flagged_words

        self.reason = reason
        self.risk_score = risk_score
        self.flagged_words = flagged_words or []

        super().__init__(
            f"Unsafe content detected: {reason} (risk={risk_score})",
            content_type="unsafe",
            context=ctx,
        )


# ============================================
# Video Generation Errors
# ============================================


class VideoError(BSForgeError):
    """Base exception for video generation errors."""

    def __init__(
        self,
        message: str,
        video_id: str | None = None,
        script_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Initialize VideoError.

        Args:
            message: Error message
            video_id: Video ID being processed
            script_id: Script ID being used
            context: Additional context
        """
        ctx = context or {}
        if video_id:
            ctx["video_id"] = video_id
        if script_id:
            ctx["script_id"] = script_id
        super().__init__(message, context=ctx)


class TTSError(VideoError):
    """Raised when TTS generation fails.

    Attributes:
        engine: TTS engine that failed
        voice_id: Voice ID being used
    """

    def __init__(
        self,
        message: str,
        engine: str | None = None,
        voice_id: str | None = None,
        video_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Initialize TTSError.

        Args:
            message: Error message
            engine: TTS engine name
            voice_id: Voice ID
            video_id: Video ID
            context: Additional context
        """
        ctx = context or {}
        if engine:
            ctx["engine"] = engine
        if voice_id:
            ctx["voice_id"] = voice_id

        self.engine = engine
        self.voice_id = voice_id

        super().__init__(message, video_id=video_id, context=ctx)


class VideoRenderError(VideoError):
    """Raised when video rendering fails.

    Attributes:
        stage: Render stage that failed
        ffmpeg_error: FFmpeg error message if applicable
    """

    def __init__(
        self,
        message: str,
        stage: str | None = None,
        ffmpeg_error: str | None = None,
        video_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Initialize VideoRenderError.

        Args:
            message: Error message
            stage: Render stage (e.g., "compose", "concat", "subtitle")
            ffmpeg_error: FFmpeg stderr output
            video_id: Video ID
            context: Additional context
        """
        ctx = context or {}
        if stage:
            ctx["stage"] = stage
        if ffmpeg_error:
            ctx["ffmpeg_error"] = ffmpeg_error[:500]  # Truncate

        self.stage = stage
        self.ffmpeg_error = ffmpeg_error

        super().__init__(message, video_id=video_id, context=ctx)


class BGMError(VideoError):
    """Base exception for BGM-related errors."""

    def __init__(
        self,
        message: str,
        track_name: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Initialize BGMError.

        Args:
            message: Error message
            track_name: Name of the BGM track
            context: Additional context
        """
        ctx = context or {}
        if track_name:
            ctx["track_name"] = track_name
        super().__init__(message, context=ctx)


class BGMDownloadError(BGMError):
    """Raised when BGM download fails.

    Attributes:
        track_name: Name of the track
        youtube_url: URL that failed
    """

    def __init__(
        self,
        message: str,
        track_name: str,
        youtube_url: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Initialize BGMDownloadError.

        Args:
            message: Error message
            track_name: Name of the track
            youtube_url: URL that failed
            context: Additional context
        """
        ctx = context or {}
        ctx["youtube_url"] = youtube_url

        self.track_name = track_name
        self.youtube_url = youtube_url

        super().__init__(message, track_name=track_name, context=ctx)


class BGMNotFoundError(BGMError):
    """Raised when no BGM tracks are available."""

    def __init__(
        self,
        message: str = "No BGM tracks available",
        context: dict[str, Any] | None = None,
    ) -> None:
        """Initialize BGMNotFoundError.

        Args:
            message: Error message
            context: Additional context
        """
        super().__init__(message, context=context)


# ============================================
# Upload Errors
# ============================================


class UploadError(BSForgeError):
    """Base exception for upload-related errors."""

    def __init__(
        self,
        message: str,
        video_id: str | None = None,
        platform: str = "youtube",
        context: dict[str, Any] | None = None,
    ) -> None:
        """Initialize UploadError.

        Args:
            message: Error message
            video_id: Video ID being uploaded
            platform: Upload platform
            context: Additional context
        """
        ctx = context or {}
        if video_id:
            ctx["video_id"] = video_id
        ctx["platform"] = platform
        super().__init__(message, context=ctx)


class YouTubeAPIError(UploadError):
    """Raised when YouTube API call fails.

    Attributes:
        error_code: YouTube API error code
        error_reason: Error reason from API
    """

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        error_reason: str | None = None,
        video_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Initialize YouTubeAPIError.

        Args:
            message: Error message
            error_code: YouTube error code
            error_reason: Error reason
            video_id: Video ID
            context: Additional context
        """
        ctx = context or {}
        if error_code:
            ctx["error_code"] = error_code
        if error_reason:
            ctx["error_reason"] = error_reason

        self.error_code = error_code
        self.error_reason = error_reason

        super().__init__(message, video_id=video_id, platform="youtube", context=ctx)


class QuotaExceededError(UploadError):
    """Raised when YouTube API quota is exceeded.

    Attributes:
        quota_limit: Quota limit
        quota_used: Quota already used
        reset_time: When quota resets
    """

    def __init__(
        self,
        message: str = "YouTube API quota exceeded",
        quota_limit: int | None = None,
        quota_used: int | None = None,
        reset_time: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Initialize QuotaExceededError.

        Args:
            message: Error message
            quota_limit: Quota limit
            quota_used: Quota already used
            reset_time: When quota resets (ISO format)
            context: Additional context
        """
        ctx = context or {}
        if quota_limit is not None:
            ctx["quota_limit"] = quota_limit
        if quota_used is not None:
            ctx["quota_used"] = quota_used
        if reset_time:
            ctx["reset_time"] = reset_time

        self.quota_limit = quota_limit
        self.quota_used = quota_used
        self.reset_time = reset_time

        super().__init__(message, platform="youtube", context=ctx)


# ============================================
# Authentication Errors
# ============================================


class AuthError(BSForgeError):
    """Base exception for authentication errors."""

    def __init__(
        self,
        message: str,
        user_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Initialize AuthError.

        Args:
            message: Error message
            user_id: User ID if available
            context: Additional context
        """
        ctx = context or {}
        if user_id:
            ctx["user_id"] = user_id
        super().__init__(message, context=ctx)


class InvalidCredentialsError(AuthError):
    """Raised when credentials are invalid.

    Attributes:
        credential_type: Type of credential (password, api_key, etc.)
    """

    def __init__(
        self,
        message: str = "Invalid credentials",
        credential_type: str | None = None,
        user_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Initialize InvalidCredentialsError.

        Args:
            message: Error message
            credential_type: Type of credential
            user_id: User ID
            context: Additional context
        """
        ctx = context or {}
        if credential_type:
            ctx["credential_type"] = credential_type

        self.credential_type = credential_type

        super().__init__(message, user_id=user_id, context=ctx)


class TokenExpiredError(AuthError):
    """Raised when authentication token has expired.

    Attributes:
        token_type: Type of token (access, refresh, etc.)
        expired_at: When the token expired
    """

    def __init__(
        self,
        message: str = "Token has expired",
        token_type: str | None = None,
        expired_at: str | None = None,
        user_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Initialize TokenExpiredError.

        Args:
            message: Error message
            token_type: Type of token
            expired_at: Expiration time (ISO format)
            user_id: User ID
            context: Additional context
        """
        ctx = context or {}
        if token_type:
            ctx["token_type"] = token_type
        if expired_at:
            ctx["expired_at"] = expired_at

        self.token_type = token_type
        self.expired_at = expired_at

        super().__init__(message, user_id=user_id, context=ctx)
