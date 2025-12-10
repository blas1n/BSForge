"""Custom exceptions for BSForge application.

This module defines all custom exceptions used throughout the application.
All exceptions inherit from BSForgeError for easy catching.
"""


class BSForgeError(Exception):
    """Base exception for all BSForge errors.

    All custom exceptions in the application should inherit from this class.

    Example:
        >>> try:
        ...     raise BSForgeError("Something went wrong")
        ... except BSForgeError as e:
        ...     print(f"Caught error: {e}")
    """

    pass


# ============================================
# Database Errors
# ============================================


class DatabaseError(BSForgeError):
    """Base exception for database-related errors."""

    pass


class RecordNotFoundError(DatabaseError):
    """Raised when a database record is not found.

    Attributes:
        model: The model class that was queried
        id: The ID that was not found
    """

    def __init__(self, model: str, id: str) -> None:
        """Initialize RecordNotFoundError.

        Args:
            model: Name of the model class
            id: ID that was not found
        """
        self.model = model
        self.id = id
        super().__init__(f"{model} with id={id} not found")


class RecordAlreadyExistsError(DatabaseError):
    """Raised when attempting to create a duplicate record."""

    pass


# ============================================
# Configuration Errors
# ============================================


class ConfigError(BSForgeError):
    """Base exception for configuration-related errors."""

    pass


class ConfigValidationError(ConfigError):
    """Raised when configuration validation fails."""

    pass


class ConfigNotFoundError(ConfigError):
    """Raised when a required configuration is not found."""

    pass


# ============================================
# Service Errors
# ============================================


class ServiceError(BSForgeError):
    """Base exception for service-related errors."""

    pass


class ExternalAPIError(ServiceError):
    """Raised when an external API call fails.

    Attributes:
        service: Name of the external service
        status_code: HTTP status code (if applicable)
        message: Error message
    """

    def __init__(self, service: str, message: str, status_code: int | None = None) -> None:
        """Initialize ExternalAPIError.

        Args:
            service: Name of the external service
            message: Error message
            status_code: HTTP status code (optional)
        """
        self.service = service
        self.status_code = status_code
        self.message = message
        super().__init__(f"{service} API error: {message}")


class RateLimitError(ServiceError):
    """Raised when rate limit is exceeded."""

    pass


# ============================================
# Content Errors
# ============================================


class ContentError(BSForgeError):
    """Base exception for content-related errors."""

    pass


class ContentGenerationError(ContentError):
    """Raised when content generation fails."""

    pass


class ContentValidationError(ContentError):
    """Raised when content validation fails."""

    pass


class UnsafeContentError(ContentError):
    """Raised when content is flagged as unsafe.

    Attributes:
        reason: Reason why content is unsafe
        risk_score: Risk score (0-100)
    """

    def __init__(self, reason: str, risk_score: int) -> None:
        """Initialize UnsafeContentError.

        Args:
            reason: Reason why content is unsafe
            risk_score: Risk score (0-100)
        """
        self.reason = reason
        self.risk_score = risk_score
        super().__init__(f"Unsafe content detected: {reason} (risk={risk_score})")


# ============================================
# Video Generation Errors
# ============================================


class VideoError(BSForgeError):
    """Base exception for video generation errors."""

    pass


class TTSError(VideoError):
    """Raised when TTS generation fails."""

    pass


class VideoRenderError(VideoError):
    """Raised when video rendering fails."""

    pass


# ============================================
# Upload Errors
# ============================================


class UploadError(BSForgeError):
    """Base exception for upload-related errors."""

    pass


class YouTubeAPIError(UploadError):
    """Raised when YouTube API call fails."""

    pass


class QuotaExceededError(UploadError):
    """Raised when YouTube API quota is exceeded."""

    pass


# ============================================
# Authentication Errors
# ============================================


class AuthError(BSForgeError):
    """Base exception for authentication errors."""

    pass


class InvalidCredentialsError(AuthError):
    """Raised when credentials are invalid."""

    pass


class TokenExpiredError(AuthError):
    """Raised when authentication token has expired."""

    pass
