"""YouTube Data API and Analytics API client.

This module provides a high-level client for YouTube API operations including
video uploads (with resumable support), metadata management, and analytics retrieval.
"""

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from app.core.exceptions import QuotaExceededError, YouTubeAPIError
from app.core.logging import get_logger
from app.infrastructure.youtube_auth import YouTubeAuthClient

logger = get_logger(__name__)

# Resumable upload chunk size (1MB)
DEFAULT_CHUNK_SIZE = 1024 * 1024

# Retriable HTTP status codes
RETRIABLE_STATUS_CODES = [500, 502, 503, 504]

# Maximum retry attempts
MAX_RETRIES = 3


@dataclass
class UploadMetadata:
    """Metadata for YouTube video upload.

    Attributes:
        title: Video title (max 100 chars)
        description: Video description (max 5000 chars)
        tags: List of video tags
        category_id: YouTube category ID
        privacy_status: Privacy setting (public, private, unlisted)
        scheduled_start_time: Publish time for scheduled videos
        is_shorts: Whether video is a YouTube Short
        made_for_kids: Whether content is made for kids
        default_language: Default language code
    """

    title: str
    description: str = ""
    tags: list[str] | None = None
    category_id: str = "28"  # Science & Technology
    privacy_status: str = "private"
    scheduled_start_time: datetime | None = None
    is_shorts: bool = True
    made_for_kids: bool = False
    default_language: str = "ko"


@dataclass
class UploadResult:
    """Result of video upload operation.

    Attributes:
        video_id: YouTube video ID
        url: Full YouTube URL
        status: Upload status
        processing_status: YouTube processing status
        uploaded_at: Upload timestamp
    """

    video_id: str
    url: str
    status: str
    processing_status: str
    uploaded_at: datetime


@dataclass
class VideoAnalytics:
    """Analytics data for a video.

    Attributes:
        video_id: YouTube video ID
        views: Total view count
        likes: Total likes
        dislikes: Total dislikes
        comments: Total comments
        shares: Total shares
        watch_time_minutes: Total watch time in minutes
        avg_view_duration_seconds: Average view duration
        avg_view_percentage: Average percentage watched
        subscribers_gained: Subscribers gained
        subscribers_lost: Subscribers lost
        ctr: Click-through rate
        traffic_sources: Traffic source breakdown
        demographics: Viewer demographics
    """

    video_id: str
    views: int = 0
    likes: int = 0
    dislikes: int = 0
    comments: int = 0
    shares: int = 0
    watch_time_minutes: int = 0
    avg_view_duration_seconds: float = 0.0
    avg_view_percentage: float = 0.0
    subscribers_gained: int = 0
    subscribers_lost: int = 0
    ctr: float = 0.0
    traffic_sources: dict[str, Any] | None = None
    demographics: dict[str, Any] | None = None


class YouTubeAPIClient:
    """YouTube Data API and Analytics API client.

    Provides methods for uploading videos with resumable uploads,
    managing video metadata, and fetching analytics data.

    Example:
        >>> auth = YouTubeAuthClient(credentials_path, token_path)
        >>> client = YouTubeAPIClient(auth)
        >>> result = await client.upload_video(
        ...     video_path=Path("video.mp4"),
        ...     metadata=UploadMetadata(title="My Video"),
        ... )
        >>> print(f"Uploaded: {result.url}")
    """

    def __init__(
        self,
        auth_client: YouTubeAuthClient,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        max_retries: int = MAX_RETRIES,
    ) -> None:
        """Initialize YouTube API client.

        Args:
            auth_client: Authenticated YouTube auth client
            chunk_size: Upload chunk size in bytes
            max_retries: Maximum retry attempts for failed operations
        """
        self.auth_client = auth_client
        self.chunk_size = chunk_size
        self.max_retries = max_retries

        logger.info(
            "YouTubeAPIClient initialized",
            chunk_size=chunk_size,
            max_retries=max_retries,
        )

    def _build_video_body(self, metadata: UploadMetadata) -> dict[str, Any]:
        """Build request body for video insert/update.

        Args:
            metadata: Video metadata

        Returns:
            Request body dictionary
        """
        body: dict[str, Any] = {
            "snippet": {
                "title": metadata.title[:100],  # YouTube limit
                "description": metadata.description[:5000],  # YouTube limit
                "categoryId": metadata.category_id,
                "defaultLanguage": metadata.default_language,
            },
            "status": {
                "privacyStatus": metadata.privacy_status,
                "selfDeclaredMadeForKids": metadata.made_for_kids,
            },
        }

        if metadata.tags:
            body["snippet"]["tags"] = metadata.tags[:500]  # YouTube limit

        if metadata.scheduled_start_time:
            body["status"]["publishAt"] = metadata.scheduled_start_time.isoformat()
            body["status"]["privacyStatus"] = "private"

        return body

    async def upload_video(
        self,
        video_path: Path,
        metadata: UploadMetadata,
        thumbnail_path: Path | None = None,
    ) -> UploadResult:
        """Upload video to YouTube with resumable upload.

        Uses resumable upload for reliability with large files.
        Automatically retries on transient errors.

        Args:
            video_path: Path to video file
            metadata: Video metadata
            thumbnail_path: Optional custom thumbnail path

        Returns:
            UploadResult with video ID and URL

        Raises:
            YouTubeAPIError: If upload fails
            QuotaExceededError: If API quota is exceeded
        """
        youtube = await self.auth_client.get_youtube_service()

        if not video_path.exists():
            raise YouTubeAPIError(
                message=f"Video file not found: {video_path}",
                error_code="FILE_NOT_FOUND",
            )

        body = self._build_video_body(metadata)

        media = MediaFileUpload(
            str(video_path),
            chunksize=self.chunk_size,
            resumable=True,
            mimetype="video/*",
        )

        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

        logger.info(
            "Starting video upload",
            title=metadata.title,
            file_size=video_path.stat().st_size,
        )

        response = None
        retry_count = 0
        start_time = time.time()

        while response is None:
            try:
                status, response = await asyncio.to_thread(request.next_chunk)
                if status:
                    progress = int(status.progress() * 100)
                    logger.debug("Upload progress", progress=f"{progress}%")

            except HttpError as e:
                if e.resp.status == 403 and "quotaExceeded" in str(e):
                    raise QuotaExceededError(
                        message="YouTube API quota exceeded",
                    ) from e

                if e.resp.status in RETRIABLE_STATUS_CODES and retry_count < self.max_retries:
                    retry_count += 1
                    wait_time = 2**retry_count
                    logger.warning(
                        "Retrying upload",
                        status=e.resp.status,
                        retry=retry_count,
                        wait_seconds=wait_time,
                    )
                    await asyncio.sleep(wait_time)
                else:
                    raise YouTubeAPIError(
                        message=f"Upload failed: {e}",
                        error_code=str(e.resp.status),
                        error_reason=str(e.content),
                    ) from e

            except Exception as e:
                if retry_count < self.max_retries:
                    retry_count += 1
                    wait_time = 2**retry_count
                    logger.warning(
                        "Retrying upload on error",
                        error=str(e),
                        retry=retry_count,
                    )
                    await asyncio.sleep(wait_time)
                else:
                    raise YouTubeAPIError(
                        message=f"Upload failed: {e}",
                    ) from e

        video_id = response["id"]
        upload_time = time.time() - start_time

        logger.info(
            "Video uploaded successfully",
            video_id=video_id,
            upload_time_seconds=f"{upload_time:.1f}",
        )

        # Upload thumbnail if provided
        if thumbnail_path and thumbnail_path.exists():
            try:
                await self.set_thumbnail(video_id, thumbnail_path)
            except Exception as e:
                logger.warning("Thumbnail upload failed", error=str(e))

        return UploadResult(
            video_id=video_id,
            url=f"https://www.youtube.com/watch?v={video_id}",
            status=response.get("status", {}).get("uploadStatus", "unknown"),
            processing_status=response.get("status", {}).get("privacyStatus", "unknown"),
            uploaded_at=datetime.now(tz=UTC),
        )

    async def set_thumbnail(self, video_id: str, thumbnail_path: Path) -> bool:
        """Set custom thumbnail for video.

        Args:
            video_id: YouTube video ID
            thumbnail_path: Path to thumbnail image

        Returns:
            True if successful

        Raises:
            YouTubeAPIError: If thumbnail upload fails
        """
        youtube = await self.auth_client.get_youtube_service()

        media = MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg")

        try:
            await asyncio.to_thread(
                youtube.thumbnails().set(videoId=video_id, media_body=media).execute
            )
            logger.info("Thumbnail set successfully", video_id=video_id)
            return True
        except HttpError as e:
            raise YouTubeAPIError(
                message=f"Thumbnail upload failed: {e}",
                video_id=video_id,
            ) from e

    async def update_metadata(
        self,
        video_id: str,
        metadata: UploadMetadata,
    ) -> dict[str, Any]:
        """Update video metadata.

        Args:
            video_id: YouTube video ID
            metadata: Updated metadata

        Returns:
            Updated video resource

        Raises:
            YouTubeAPIError: If update fails
        """
        youtube = await self.auth_client.get_youtube_service()

        body = self._build_video_body(metadata)
        body["id"] = video_id

        try:
            response = await asyncio.to_thread(
                youtube.videos().update(part="snippet,status", body=body).execute
            )
            logger.info("Video metadata updated", video_id=video_id)
            return response
        except HttpError as e:
            raise YouTubeAPIError(
                message=f"Metadata update failed: {e}",
                video_id=video_id,
            ) from e

    async def get_video_status(self, video_id: str) -> dict[str, Any]:
        """Get video processing status.

        Args:
            video_id: YouTube video ID

        Returns:
            Video status information

        Raises:
            YouTubeAPIError: If status check fails
        """
        youtube = await self.auth_client.get_youtube_service()

        try:
            response = await asyncio.to_thread(
                youtube.videos().list(part="status,processingDetails", id=video_id).execute
            )

            if not response.get("items"):
                raise YouTubeAPIError(
                    message=f"Video not found: {video_id}",
                    video_id=video_id,
                    error_code="NOT_FOUND",
                )

            return response["items"][0]
        except HttpError as e:
            raise YouTubeAPIError(
                message=f"Status check failed: {e}",
                video_id=video_id,
            ) from e

    async def get_video_analytics(
        self,
        video_id: str,
        start_date: str,
        end_date: str,
    ) -> VideoAnalytics:
        """Get analytics for a specific video.

        Args:
            video_id: YouTube video ID
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            VideoAnalytics with metrics

        Raises:
            YouTubeAPIError: If analytics fetch fails
        """
        analytics = await self.auth_client.get_analytics_service()

        try:
            response = await asyncio.to_thread(
                analytics.reports()
                .query(
                    ids="channel==MINE",
                    startDate=start_date,
                    endDate=end_date,
                    metrics="views,likes,dislikes,comments,shares,estimatedMinutesWatched,"
                    "averageViewDuration,averageViewPercentage,subscribersGained,"
                    "subscribersLost",
                    filters=f"video=={video_id}",
                )
                .execute
            )

            rows = response.get("rows", [[]])
            row = rows[0] if rows else [0] * 10

            return VideoAnalytics(
                video_id=video_id,
                views=int(row[0]) if len(row) > 0 else 0,
                likes=int(row[1]) if len(row) > 1 else 0,
                dislikes=int(row[2]) if len(row) > 2 else 0,
                comments=int(row[3]) if len(row) > 3 else 0,
                shares=int(row[4]) if len(row) > 4 else 0,
                watch_time_minutes=int(row[5]) if len(row) > 5 else 0,
                avg_view_duration_seconds=float(row[6]) if len(row) > 6 else 0.0,
                avg_view_percentage=float(row[7]) if len(row) > 7 else 0.0,
                subscribers_gained=int(row[8]) if len(row) > 8 else 0,
                subscribers_lost=int(row[9]) if len(row) > 9 else 0,
            )

        except HttpError as e:
            raise YouTubeAPIError(
                message=f"Analytics fetch failed: {e}",
                video_id=video_id,
            ) from e

    async def get_channel_analytics(
        self,
        start_date: str,
        end_date: str,
    ) -> dict[str, Any]:
        """Get channel-level analytics.

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            Channel analytics data

        Raises:
            YouTubeAPIError: If analytics fetch fails
        """
        analytics = await self.auth_client.get_analytics_service()

        try:
            response = await asyncio.to_thread(
                analytics.reports()
                .query(
                    ids="channel==MINE",
                    startDate=start_date,
                    endDate=end_date,
                    metrics="views,likes,subscribersGained,subscribersLost,"
                    "estimatedMinutesWatched,averageViewDuration",
                    dimensions="day",
                    sort="day",
                )
                .execute
            )
            return response
        except HttpError as e:
            raise YouTubeAPIError(
                message=f"Channel analytics fetch failed: {e}",
            ) from e

    async def get_traffic_sources(
        self,
        video_id: str,
        start_date: str,
        end_date: str,
    ) -> dict[str, int]:
        """Get traffic sources for a video.

        Args:
            video_id: YouTube video ID
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            Dictionary of traffic source to view count

        Raises:
            YouTubeAPIError: If analytics fetch fails
        """
        analytics = await self.auth_client.get_analytics_service()

        try:
            response = await asyncio.to_thread(
                analytics.reports()
                .query(
                    ids="channel==MINE",
                    startDate=start_date,
                    endDate=end_date,
                    metrics="views",
                    dimensions="insightTrafficSourceType",
                    filters=f"video=={video_id}",
                )
                .execute
            )

            traffic_sources: dict[str, int] = {}
            for row in response.get("rows", []):
                if len(row) >= 2:
                    traffic_sources[row[0]] = int(row[1])

            return traffic_sources

        except HttpError as e:
            raise YouTubeAPIError(
                message=f"Traffic sources fetch failed: {e}",
                video_id=video_id,
            ) from e


__all__ = [
    "YouTubeAPIClient",
    "UploadMetadata",
    "UploadResult",
    "VideoAnalytics",
]
