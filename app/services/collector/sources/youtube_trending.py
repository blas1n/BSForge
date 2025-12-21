"""YouTube Trending source collector.

Collects trending videos from YouTube using the YouTube Data API v3.
Requires YOUTUBE_API_KEY environment variable.
"""

import contextlib
from datetime import datetime
from typing import Any

from pydantic import HttpUrl

from app.config.sources import YouTubeTrendingConfig

# TODO: This module is legacy and should be migrated to DI container.
from app.core.config import get_config
from app.core.logging import get_logger
from app.services.collector.base import BaseSource, RawTopic

logger = get_logger(__name__)

# YouTube Data API v3 endpoint
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"


class YouTubeTrendingSource(BaseSource[YouTubeTrendingConfig]):
    """YouTube Trending source collector.

    Fetches trending videos from YouTube using the Data API v3.

    Config options:
        regions: List of region codes (ISO 3166-1 alpha-2)
        limit: Maximum videos per region (default: 20)
        category_id: YouTube video category ID (default: 0 = all)

    Params override (from channel config):
        regions: Override region list
        limit: Override limit per region

    Environment:
        YOUTUBE_API_KEY: Required YouTube Data API v3 key
    """

    # Global source: collected once, shared across all channels
    is_global = True

    @classmethod
    def build_config(cls, overrides: dict[str, Any]) -> YouTubeTrendingConfig:
        """Build YouTubeTrendingConfig from channel overrides.

        Args:
            overrides: Configuration overrides with optional keys:
                - params.regions: List of region codes (optional)
                - params.category_id: Video category ID (optional)
                - limit: Maximum videos per region (optional)

        Returns:
            YouTubeTrendingConfig instance
        """
        params = overrides.get("params", {})
        return YouTubeTrendingConfig(
            regions=params.get("regions", ["KR", "US"]),
            category_id=params.get("category_id", 0),
            limit=overrides.get("limit", 20),
        )

    def _get_api_key(self) -> str | None:
        """Get YouTube API key from settings or config.

        Returns:
            API key or None if not configured
        """
        # Try config first, then global config
        if self._config.api_key:
            return self._config.api_key
        return getattr(get_config(), "youtube_api_key", None)

    async def collect(self, params: dict[str, Any] | None = None) -> list[RawTopic]:
        """Collect trending videos from YouTube.

        Args:
            params: Optional parameters to override defaults

        Returns:
            List of RawTopic from YouTube Trending
        """
        api_key = self._get_api_key()
        if not api_key:
            logger.error("YouTube API key not configured")
            return []

        params = params or {}
        regions = params.get("regions", self._config.regions)
        limit = params.get("limit", self._config.limit)
        category_id = params.get("category_id", self._config.category_id)

        logger.info(
            "Collecting from YouTube Trending",
            regions=regions,
            limit=limit,
        )

        topics: list[RawTopic] = []
        for region in regions:
            try:
                region_topics = await self._fetch_trending(api_key, region, limit, category_id)
                topics.extend(region_topics)
            except Exception as e:
                logger.error(
                    "Failed to fetch YouTube Trending",
                    region=region,
                    error=str(e),
                )
                continue

        logger.info("YouTube Trending collection complete", collected=len(topics))
        return topics

    async def _fetch_trending(
        self,
        api_key: str,
        region: str,
        limit: int,
        category_id: int,
    ) -> list[RawTopic]:
        """Fetch trending videos for a specific region.

        Args:
            api_key: YouTube API key
            region: Region code (ISO 3166-1 alpha-2)
            limit: Maximum videos to fetch
            category_id: Video category ID (0 = all)

        Returns:
            List of RawTopic
        """
        url = f"{YOUTUBE_API_BASE}/videos"
        params: dict[str, Any] = {
            "part": "snippet,statistics",
            "chart": "mostPopular",
            "regionCode": region,
            "maxResults": min(limit, 50),  # API max is 50
            "key": api_key,
        }

        if category_id > 0:
            params["videoCategoryId"] = str(category_id)

        response = await self._http_client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        topics: list[RawTopic] = []
        for item in data.get("items", []):
            topic = self._to_raw_topic(item, region)
            if topic:
                topics.append(topic)

        return topics

    def _to_raw_topic(self, video: dict[str, Any], region: str) -> RawTopic | None:
        """Convert YouTube video to RawTopic.

        Args:
            video: YouTube video data from API
            region: Region code

        Returns:
            RawTopic or None if conversion failed
        """
        try:
            snippet = video.get("snippet", {})
            statistics = video.get("statistics", {})
            video_id = video.get("id", "")

            if not video_id or not snippet.get("title"):
                return None

            # Parse publish time
            published_at = None
            if snippet.get("publishedAt"):
                with contextlib.suppress(ValueError):
                    published_at = datetime.fromisoformat(
                        snippet["publishedAt"].replace("Z", "+00:00")
                    )

            # Get thumbnail URL (prefer high quality)
            thumbnails = snippet.get("thumbnails", {})
            thumbnail_url = (
                thumbnails.get("high", {}).get("url")
                or thumbnails.get("medium", {}).get("url")
                or thumbnails.get("default", {}).get("url")
            )

            return RawTopic(
                source_id=str(self.source_id),
                source_url=HttpUrl(f"https://www.youtube.com/watch?v={video_id}"),
                title=snippet["title"],
                content=snippet.get("description"),
                published_at=published_at,
                metrics={
                    "views": int(statistics.get("viewCount", 0)),
                    "likes": int(statistics.get("likeCount", 0)),
                    "comments": int(statistics.get("commentCount", 0)),
                },
                metadata={
                    "source_name": "YouTube",
                    "video_id": video_id,
                    "channel_id": snippet.get("channelId"),
                    "channel_title": snippet.get("channelTitle"),
                    "category_id": snippet.get("categoryId"),
                    "tags": snippet.get("tags", []),
                    "thumbnail_url": thumbnail_url,
                    "region": region,
                    "default_language": snippet.get("defaultLanguage"),
                    "default_audio_language": snippet.get("defaultAudioLanguage"),
                },
            )
        except Exception as e:
            logger.warning(
                "Failed to convert YouTube video",
                video_id=video.get("id"),
                error=str(e),
            )
            return None

    async def health_check(self) -> bool:
        """Check if YouTube API is accessible.

        Returns:
            True if API responds successfully
        """
        api_key = self._get_api_key()
        if not api_key:
            logger.warning("YouTube API key not configured for health check")
            return False

        try:
            url = f"{YOUTUBE_API_BASE}/videos"
            params: dict[str, str | int] = {
                "part": "snippet",
                "chart": "mostPopular",
                "regionCode": "US",
                "maxResults": 1,
                "key": api_key,
            }

            response = await self._http_client.get(url, params=params)
            return response.status_code == 200
        except Exception as e:
            logger.warning("YouTube API health check failed", error=str(e))
            return False


__all__ = ["YouTubeTrendingSource"]
