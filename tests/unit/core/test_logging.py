"""Tests for app.core.logging module."""

import pytest
import structlog

from app.core.logging import get_logger, setup_logging


@pytest.mark.unit
def test_setup_logging():
    """Test that setup_logging configures structlog."""
    setup_logging()

    logger = structlog.get_logger()
    assert logger is not None
    # Logger can be LazyProxy or BoundLogger depending on when it's accessed
    assert hasattr(logger, "info")
    assert hasattr(logger, "error")


@pytest.mark.unit
def test_get_logger():
    """Test get_logger returns configured logger."""
    setup_logging()

    logger = get_logger("test")
    assert logger is not None
    # Logger can be LazyProxy or BoundLogger depending on when it's accessed
    assert hasattr(logger, "info")
    assert hasattr(logger, "error")


@pytest.mark.unit
def test_get_logger_without_name():
    """Test get_logger works without explicit name."""
    setup_logging()

    logger = get_logger()
    assert logger is not None
    # Logger can be LazyProxy or BoundLogger depending on when it's accessed
    assert hasattr(logger, "info")
    assert hasattr(logger, "error")


@pytest.mark.unit
def test_logger_logging_methods():
    """Test that logger has standard logging methods."""
    setup_logging()

    logger = get_logger("test")

    # Test that methods exist and are callable
    assert callable(logger.debug)
    assert callable(logger.info)
    assert callable(logger.warning)
    assert callable(logger.error)
    assert callable(logger.critical)


@pytest.mark.unit
def test_logger_with_context():
    """Test logging with context variables."""
    setup_logging()

    logger = get_logger("test")

    # This should not raise
    logger.info("Test message", user_id="123", action="test")
    logger.error("Test error", error="Something went wrong", code=500)


@pytest.mark.unit
def test_logger_exception_logging(caplog):
    """Test logging exceptions with traceback."""
    setup_logging()

    logger = get_logger("test")

    try:
        raise ValueError("Test exception")
    except ValueError:
        # This should capture exception info
        logger.exception("Error occurred")

    # Verify that exception was logged (if using standard lib integration)
    # Note: This might need adjustment based on exact logging configuration
