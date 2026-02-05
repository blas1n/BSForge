"""Optimal upload time analysis service.

This module provides the OptimalTimeAnalyzer for analyzing historical data
to find the best times for uploading videos.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.config.youtube_upload import AnalyticsConfig
from app.core.logging import get_logger
from app.core.types import SessionFactory
from app.models.performance import Performance
from app.models.upload import Upload, UploadStatus

logger = get_logger(__name__)

# Default golden hours for Korean YouTube Shorts
KOREAN_GOLDEN_HOURS = {
    "weekday": [7, 12, 18, 21],  # Mon-Fri
    "weekend": [10, 14, 18, 21],  # Sat-Sun
}


@dataclass
class TimeSlot:
    """Performance data for a time slot.

    Attributes:
        hour: Hour of day (0-23)
        day_of_week: Day of week (0=Monday, 6=Sunday), None for hour-only
        avg_views: Average views for this slot
        avg_engagement: Average engagement rate
        sample_count: Number of videos in this slot
        score: Normalized score (0-1)
    """

    hour: int
    day_of_week: int | None = None
    avg_views: float = 0.0
    avg_engagement: float = 0.0
    sample_count: int = 0
    score: float = 0.0


@dataclass
class TimeSlotAnalysis:
    """Analysis of optimal upload time slots.

    Attributes:
        best_hours: Best hours by score
        best_days: Best days by score
        best_slots: Best (hour, day) combinations
        worst_slots: Worst performing slots
        confidence_scores: Confidence by slot
        sample_size: Total videos analyzed
        analysis_period_days: Days of data analyzed
    """

    best_hours: list[int] = field(default_factory=list)
    best_days: list[int] = field(default_factory=list)
    best_slots: list[TimeSlot] = field(default_factory=list)
    worst_slots: list[TimeSlot] = field(default_factory=list)
    confidence_scores: dict[str, float] = field(default_factory=dict)
    sample_size: int = 0
    analysis_period_days: int = 90


class OptimalTimeAnalyzer:
    """Analyze historical data to find optimal upload times.

    Uses video performance data to identify the best times for
    uploading based on views and engagement metrics.

    Example:
        >>> analyzer = OptimalTimeAnalyzer(db_session_factory)
        >>> analysis = await analyzer.analyze_channel(channel_id)
        >>> print(f"Best hours: {analysis.best_hours}")
    """

    def __init__(
        self,
        db_session_factory: SessionFactory,
        config: AnalyticsConfig | None = None,
    ) -> None:
        """Initialize optimal time analyzer.

        Args:
            db_session_factory: Database session factory
            config: Analytics configuration
        """
        self.db_session_factory = db_session_factory
        self.config = config or AnalyticsConfig()

        logger.info("OptimalTimeAnalyzer initialized")

    async def analyze_channel(
        self,
        channel_id: uuid.UUID,
        days_lookback: int | None = None,
    ) -> TimeSlotAnalysis:
        """Analyze channel's historical performance by upload time.

        Args:
            channel_id: Database channel ID
            days_lookback: Days of data to analyze (default from config)

        Returns:
            TimeSlotAnalysis with best/worst times
        """
        days = days_lookback or self.config.metrics_lookback_days
        cutoff = datetime.now(tz=UTC) - timedelta(days=days)

        logger.info(
            "Analyzing channel",
            channel_id=str(channel_id),
            days_lookback=days,
        )

        async with self.db_session_factory() as session:
            # Get uploads with performance data
            result = await session.execute(
                select(Upload, Performance)
                .join(Performance, Upload.id == Performance.upload_id)
                .join(Upload.video)
                .where(
                    Upload.upload_status == UploadStatus.COMPLETED,
                    Upload.uploaded_at >= cutoff,
                    Upload.uploaded_at.isnot(None),
                )
            )
            rows = result.all()

            if len(rows) < self.config.min_sample_size:
                logger.info(
                    "Insufficient data, using defaults",
                    sample_count=len(rows),
                    min_required=self.config.min_sample_size,
                )
                return self._get_default_analysis(len(rows), days)

            # Aggregate by time slot
            hour_data: dict[int, list[tuple[float, float]]] = {}
            day_data: dict[int, list[tuple[float, float]]] = {}
            slot_data: dict[tuple[int, int], list[tuple[float, float]]] = {}

            for upload, performance in rows:
                if not upload.uploaded_at:
                    continue

                hour = upload.uploaded_at.hour
                day = upload.uploaded_at.weekday()
                views = float(performance.views)
                engagement = performance.engagement_rate

                # Aggregate by hour
                if hour not in hour_data:
                    hour_data[hour] = []
                hour_data[hour].append((views, engagement))

                # Aggregate by day
                if day not in day_data:
                    day_data[day] = []
                day_data[day].append((views, engagement))

                # Aggregate by slot (hour, day)
                slot = (hour, day)
                if slot not in slot_data:
                    slot_data[slot] = []
                slot_data[slot].append((views, engagement))

            # Calculate scores
            analysis = self._calculate_scores(hour_data, day_data, slot_data, len(rows), days)

            logger.info(
                "Analysis complete",
                channel_id=str(channel_id),
                sample_size=len(rows),
                best_hours=analysis.best_hours[:3],
            )

            return analysis

    def _calculate_scores(
        self,
        hour_data: dict[int, list[tuple[float, float]]],
        day_data: dict[int, list[tuple[float, float]]],
        slot_data: dict[tuple[int, int], list[tuple[float, float]]],
        sample_size: int,
        days: int,
    ) -> TimeSlotAnalysis:
        """Calculate scores from aggregated data.

        Args:
            hour_data: Views/engagement by hour
            day_data: Views/engagement by day
            slot_data: Views/engagement by (hour, day) slot
            sample_size: Total samples
            days: Days of data

        Returns:
            TimeSlotAnalysis with calculated scores
        """
        # Calculate hour scores
        hour_slots: list[TimeSlot] = []
        max_views = 1.0
        max_engagement = 1.0

        for hour, data in hour_data.items():
            avg_views = sum(v for v, _ in data) / len(data)
            avg_engagement = sum(e for _, e in data) / len(data)
            max_views = max(max_views, avg_views)
            max_engagement = max(max_engagement, avg_engagement)
            hour_slots.append(
                TimeSlot(
                    hour=hour,
                    avg_views=avg_views,
                    avg_engagement=avg_engagement,
                    sample_count=len(data),
                )
            )

        # Normalize and score hour slots
        engagement_weight = self.config.engagement_weight
        views_weight = 1 - engagement_weight

        for slot in hour_slots:
            confidence = min(slot.sample_count / 10, 1.0)
            view_score = slot.avg_views / max_views if max_views > 0 else 0
            eng_score = slot.avg_engagement / max_engagement if max_engagement > 0 else 0
            slot.score = (views_weight * view_score + engagement_weight * eng_score) * confidence

        # Calculate day scores
        day_slots: list[TimeSlot] = []
        for day, data in day_data.items():
            avg_views = sum(v for v, _ in data) / len(data)
            avg_engagement = sum(e for _, e in data) / len(data)
            confidence = min(len(data) / 10, 1.0)
            view_score = avg_views / max_views if max_views > 0 else 0
            eng_score = avg_engagement / max_engagement if max_engagement > 0 else 0
            score = (views_weight * view_score + engagement_weight * eng_score) * confidence
            day_slots.append(
                TimeSlot(
                    hour=0,  # Not applicable
                    day_of_week=day,
                    avg_views=avg_views,
                    avg_engagement=avg_engagement,
                    sample_count=len(data),
                    score=score,
                )
            )

        # Calculate combined slot scores
        combined_slots: list[TimeSlot] = []
        for (hour, day), data in slot_data.items():
            avg_views = sum(v for v, _ in data) / len(data)
            avg_engagement = sum(e for _, e in data) / len(data)
            confidence = min(len(data) / 5, 1.0)
            view_score = avg_views / max_views if max_views > 0 else 0
            eng_score = avg_engagement / max_engagement if max_engagement > 0 else 0
            score = (views_weight * view_score + engagement_weight * eng_score) * confidence
            combined_slots.append(
                TimeSlot(
                    hour=hour,
                    day_of_week=day,
                    avg_views=avg_views,
                    avg_engagement=avg_engagement,
                    sample_count=len(data),
                    score=score,
                )
            )

        # Sort and select best/worst
        hour_slots.sort(key=lambda x: x.score, reverse=True)
        day_slots.sort(key=lambda x: x.score, reverse=True)
        combined_slots.sort(key=lambda x: x.score, reverse=True)

        best_hours = [s.hour for s in hour_slots[:5]]
        best_days = [s.day_of_week for s in day_slots[:3] if s.day_of_week is not None]

        # Build confidence scores
        confidence_scores = {}
        for slot in hour_slots:
            confidence_scores[f"hour_{slot.hour}"] = min(slot.sample_count / 10, 1.0)

        return TimeSlotAnalysis(
            best_hours=best_hours,
            best_days=best_days,
            best_slots=combined_slots[:10],
            worst_slots=combined_slots[-5:] if len(combined_slots) >= 5 else [],
            confidence_scores=confidence_scores,
            sample_size=sample_size,
            analysis_period_days=days,
        )

    def _get_default_analysis(self, sample_size: int, days: int) -> TimeSlotAnalysis:
        """Get default analysis when insufficient data.

        Args:
            sample_size: Actual samples available
            days: Days analyzed

        Returns:
            Default TimeSlotAnalysis based on Korean golden hours
        """
        # Use Korean golden hours as defaults
        best_hours = KOREAN_GOLDEN_HOURS["weekday"]
        best_days = [5, 6]  # Saturday, Sunday

        best_slots = [TimeSlot(hour=h, day_of_week=None, score=0.8) for h in best_hours]

        return TimeSlotAnalysis(
            best_hours=best_hours,
            best_days=best_days,
            best_slots=best_slots,
            worst_slots=[],
            confidence_scores={"default": 0.5},
            sample_size=sample_size,
            analysis_period_days=days,
        )

    def get_next_optimal_time(
        self,
        analysis: TimeSlotAnalysis,
        after: datetime | None = None,
        allowed_hours: list[int] | None = None,
        preferred_days: list[int] | None = None,
    ) -> datetime:
        """Get next optimal upload time based on analysis.

        Args:
            analysis: TimeSlotAnalysis from analyze_channel
            after: Earliest allowed time (default: now)
            allowed_hours: Hours when uploads are allowed (default: 9-21)
            preferred_days: Preferred days (default: all)

        Returns:
            Next optimal upload datetime
        """
        after = after or datetime.now(tz=UTC)
        allowed_hours = allowed_hours or list(range(9, 22))
        best_hours = [h for h in analysis.best_hours if h in allowed_hours] or allowed_hours

        # Try to find optimal slot in next 7 days
        for day_offset in range(7):
            candidate = after + timedelta(days=day_offset)

            # Check if preferred day
            if preferred_days and candidate.weekday() not in preferred_days:
                continue

            for hour in best_hours:
                optimal_time = candidate.replace(
                    hour=hour,
                    minute=0,
                    second=0,
                    microsecond=0,
                )

                if optimal_time > after:
                    return optimal_time

        # Fallback: tomorrow at first allowed hour
        tomorrow = after + timedelta(days=1)
        return tomorrow.replace(
            hour=allowed_hours[0],
            minute=0,
            second=0,
            microsecond=0,
        )


__all__ = [
    "OptimalTimeAnalyzer",
    "TimeSlotAnalysis",
    "TimeSlot",
]
