"""Google Trends source collector.

Collects trending search topics from Google Trends using pytrends.
Supports multiple regions and real-time/daily trends.
"""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pycountry
from pydantic import HttpUrl
from pytrends.request import TrendReq

from app.config.sources import GoogleTrendsConfig
from app.core.logging import get_logger
from app.services.collector.base import BaseSource, RawTopic

if TYPE_CHECKING:
    import httpx

logger = get_logger(__name__)


class GoogleTrendsSource(BaseSource[GoogleTrendsConfig]):
    """Google Trends source collector.

    Fetches trending search topics from Google Trends.

    Config options:
        regions: List of region codes (e.g., 'KR', 'US')
        limit: Maximum trends per region (default: 20)
        timeframe: Timeframe for trends (default: 'now 1-d')
        category: Google Trends category ID (default: 0 = all)

    Params override (from channel config):
        regions: Override region list
        limit: Override limit per region
    """

    # Global source: collected once, shared across all channels
    is_global = True

    @classmethod
    def build_config(cls, overrides: dict[str, Any]) -> GoogleTrendsConfig:
        """Build GoogleTrendsConfig from channel overrides.

        Args:
            overrides: Configuration overrides with optional keys:
                - params.regions: List of region codes (optional)
                - params.timeframe: Timeframe for trends (optional)
                - params.category: Category ID (optional)
                - limit: Maximum trends per region (optional)

        Returns:
            GoogleTrendsConfig instance
        """
        params = overrides.get("params", {})
        return GoogleTrendsConfig(
            regions=params.get("regions", ["KR", "US"]),
            timeframe=params.get("timeframe", "now 1-d"),
            category=params.get("category", 0),
            limit=overrides.get("limit", 20),
        )

    def __init__(
        self,
        config: GoogleTrendsConfig,
        source_id: uuid.UUID,
        http_client: "httpx.AsyncClient | None" = None,
    ):
        """Initialize Google Trends source collector.

        Args:
            config: Typed configuration object
            source_id: UUID of the source
            http_client: Optional shared HTTP client (not used by pytrends)
        """
        # Note: GoogleTrends uses pytrends which manages its own HTTP session
        super().__init__(config, source_id, http_client)

    async def collect(self, params: dict[str, Any] | None = None) -> list[RawTopic]:
        """Collect trending topics from Google Trends.

        Args:
            params: Optional parameters to override defaults

        Returns:
            List of RawTopic from Google Trends
        """
        params = params or {}
        regions = params.get("regions", self._config.regions)
        limit = params.get("limit", self._config.limit)

        logger.info(
            "Collecting from Google Trends",
            regions=regions,
            limit=limit,
        )

        topics: list[RawTopic] = []

        for region in regions:
            try:
                region_topics = await self._fetch_trending_searches(region, limit)
                topics.extend(region_topics)
            except Exception as e:
                logger.error(
                    "Failed to fetch Google Trends",
                    region=region,
                    error=str(e),
                )
                continue

        logger.info("Google Trends collection complete", collected=len(topics))
        return topics

    async def _fetch_trending_searches(self, region: str, limit: int) -> list[RawTopic]:
        """Fetch trending searches for a specific region.

        Args:
            region: Region code (e.g., 'KR', 'US')
            limit: Maximum trends to fetch

        Returns:
            List of RawTopic
        """
        # pytrends is synchronous, but we wrap it for consistency
        pytrends = TrendReq(hl="en-US", tz=360)

        # Get daily trending searches
        try:
            trending_df = pytrends.trending_searches(pn=self._get_pn_code(region))
        except Exception as e:
            logger.warning(
                "Failed to get trending searches, trying realtime",
                region=region,
                error=str(e),
            )
            # Fallback to realtime trends
            trending_df = pytrends.realtime_trending_searches(pn=self._get_region_name(region))

        topics: list[RawTopic] = []

        # Process trending searches
        if trending_df is not None and not trending_df.empty:
            for _, row in trending_df.head(limit).iterrows():
                # Handle different DataFrame structures
                query = row if isinstance(row, str) else row.iloc[0] if len(row) > 0 else str(row)
                if not query or not isinstance(query, str):
                    continue

                topic = self._create_topic(query, region)
                if topic:
                    topics.append(topic)

        return topics

    def _create_topic(self, query: str, region: str) -> RawTopic | None:
        """Create RawTopic from trending search query.

        Args:
            query: Trending search query
            region: Region code

        Returns:
            RawTopic or None if creation failed
        """
        try:
            # Create Google search URL for the query
            search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"

            return RawTopic(
                source_id=str(self.source_id),
                source_url=HttpUrl(search_url),
                title=query,
                content=None,
                published_at=datetime.now(UTC),
                metrics={
                    "trend_type": "daily",
                    "region": region,
                },
                metadata={
                    "source_name": "GoogleTrends",
                    "google_query": query,
                    "region": region,
                    "trends_url": (
                        f"https://trends.google.com/trends/explore"
                        f"?q={query.replace(' ', '%20')}&geo={region}"
                    ),
                },
            )
        except Exception as e:
            logger.warning(
                "Failed to create topic from trend",
                query=query,
                error=str(e),
            )
            return None

    def _get_pn_code(self, region: str) -> str:
        """Convert ISO alpha-2 country code to pytrends pn format.

        Uses pycountry to dynamically convert ISO codes to pytrends format.

        Args:
            region: ISO 3166-1 alpha-2 country code (e.g., 'KR', 'US')

        Returns:
            pytrends pn format (e.g., 'south_korea', 'united_states')
        """
        country = pycountry.countries.get(alpha_2=region.upper())
        if not country:
            logger.warning(f"Unknown country code: {region}, using as-is")
            return region.lower()

        # Prefer common_name if available (e.g., 'South Korea' instead of 'Korea, Republic of')
        name: str = getattr(country, "common_name", None) or country.name

        # Convert to pytrends format: lowercase with underscores
        return name.lower().replace(" ", "_").replace("-", "_")

    def _get_region_name(self, region: str) -> str:
        """Get region name for realtime trends (uses ISO code directly).

        Args:
            region: ISO 3166-1 alpha-2 country code

        Returns:
            ISO code for pytrends realtime_trending_searches
        """
        # realtime_trending_searches uses ISO codes directly
        return region.upper()

    async def health_check(self) -> bool:
        """Check if Google Trends API is accessible.

        Returns:
            True if API responds successfully
        """
        try:
            pytrends = TrendReq(hl="en-US", tz=360)
            # Try a simple trending search
            df = pytrends.trending_searches(pn="united_states")
            return df is not None and not df.empty
        except Exception as e:
            logger.warning("Google Trends health check failed", error=str(e))
            return False


__all__ = ["GoogleTrendsSource"]
