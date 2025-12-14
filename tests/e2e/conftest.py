"""E2E test fixtures and configuration."""

import hashlib
import shutil
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.services.collector.base import NormalizedTopic, RawTopic, ScoredTopic

# =============================================================================
# Directory Fixtures
# =============================================================================


@pytest.fixture
def temp_output_dir() -> Path:
    """Create a temporary directory for test outputs."""
    temp_dir = Path(tempfile.mkdtemp(prefix="bsforge_e2e_"))
    yield temp_dir
    # Cleanup after test
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def ffmpeg_available() -> bool:
    """Check if FFmpeg is available."""
    return shutil.which("ffmpeg") is not None


@pytest.fixture
def skip_without_ffmpeg(ffmpeg_available: bool) -> None:
    """Skip test if FFmpeg is not available."""
    if not ffmpeg_available:
        pytest.skip("FFmpeg not installed")


# =============================================================================
# DTO Factory Functions
# =============================================================================


def create_raw_topic(
    title: str = "Test Topic",
    source_id: str = "test_source",
    source_url: str = "https://example.com/topic/1",
    content: str | None = None,
    published_at: datetime | None = None,
    metrics: dict | None = None,
    metadata: dict | None = None,
) -> RawTopic:
    """Factory function to create RawTopic with defaults."""
    return RawTopic(
        source_id=source_id,
        source_url=source_url,  # type: ignore[arg-type]
        title=title,
        content=content,
        published_at=published_at or datetime.now(UTC),
        metrics=metrics or {},
        metadata=metadata or {},
    )


def create_normalized_topic(
    title: str = "Test Topic",
    source_id: uuid.UUID | None = None,
    source_url: str = "https://example.com/topic/1",
    title_translated: str | None = None,
    summary: str = "Test summary",
    categories: list[str] | None = None,
    keywords: list[str] | None = None,
    entities: dict[str, list[str]] | None = None,
    language: str = "ko",
    published_at: datetime | None = None,
    content_hash: str | None = None,
    metrics: dict | None = None,
    engagement_score: int = 50,
) -> NormalizedTopic:
    """Factory function to create NormalizedTopic with defaults."""
    if source_id is None:
        source_id = uuid.uuid4()
    if content_hash is None:
        content_hash = hashlib.sha256(title.encode()).hexdigest()

    # Include engagement_score in metrics if provided
    final_metrics = metrics or {}
    if "engagement_score" not in final_metrics:
        final_metrics["engagement_score"] = engagement_score

    return NormalizedTopic(
        source_id=source_id,
        source_url=source_url,  # type: ignore[arg-type]
        title_original=title,
        title_translated=title_translated,
        title_normalized=title,
        summary=summary,
        categories=categories or ["tech"],
        keywords=keywords or ["test"],
        entities=entities or {},
        language=language,
        published_at=published_at or datetime.now(UTC),
        content_hash=content_hash,
        metrics=final_metrics,
    )


def create_scored_topic(
    title: str = "Test Topic",
    source_id: uuid.UUID | None = None,
    source_url: str = "https://example.com/topic/1",
    title_translated: str | None = None,
    summary: str = "Test summary",
    categories: list[str] | None = None,
    keywords: list[str] | None = None,
    entities: dict[str, list[str]] | None = None,
    language: str = "ko",
    published_at: datetime | None = None,
    content_hash: str | None = None,
    metrics: dict | None = None,
    engagement_score: int = 50,
    score_source: float = 0.5,
    score_freshness: float = 0.5,
    score_trend: float = 0.5,
    score_relevance: float = 0.5,
    score_total: int = 50,
) -> ScoredTopic:
    """Factory function to create ScoredTopic with defaults."""
    if source_id is None:
        source_id = uuid.uuid4()
    if content_hash is None:
        content_hash = hashlib.sha256(title.encode()).hexdigest()

    # Include engagement_score in metrics if provided
    final_metrics = metrics or {}
    if "engagement_score" not in final_metrics:
        final_metrics["engagement_score"] = engagement_score

    return ScoredTopic(
        source_id=source_id,
        source_url=source_url,  # type: ignore[arg-type]
        title_original=title,
        title_translated=title_translated,
        title_normalized=title,
        summary=summary,
        categories=categories or ["tech"],
        keywords=keywords or ["test"],
        entities=entities or {},
        language=language,
        published_at=published_at or datetime.now(UTC),
        content_hash=content_hash,
        metrics=final_metrics,
        score_source=score_source,
        score_freshness=score_freshness,
        score_trend=score_trend,
        score_relevance=score_relevance,
        score_total=score_total,
    )


# Mark for E2E tests that need external services
e2e_marker = pytest.mark.e2e
slow_marker = pytest.mark.slow
