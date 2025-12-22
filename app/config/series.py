"""Series configuration models.

All string values (terms) are automatically lowercased on load
for consistent matching with normalized topic data.
"""

from pydantic import BaseModel, Field, field_validator

from app.config.validators import normalize_string_list


class SeriesCriteria(BaseModel):
    """Criteria for matching topics to a series.

    Attributes:
        terms: Common terms for the series - lowercased on load
        min_similarity: Minimum similarity threshold for matching (0-1)
    """

    terms: list[str] = Field(default_factory=list)
    min_similarity: float = Field(default=0.6, ge=0.0, le=1.0)

    @field_validator("terms", mode="before")
    @classmethod
    def lowercase_terms(cls, v: list[str]) -> list[str]:
        """Normalize terms to lowercase."""
        return normalize_string_list(v)


class SeriesConfig(BaseModel):
    """Configuration for a content series.

    A series is a recurring content pattern that performs well,
    like "AI 뉴스", "주간 밈 정리", etc.

    Attributes:
        id: Unique series identifier
        name: Display name for the series
        criteria: Matching criteria for topics
        enabled: Whether the series is active
        auto_detected: Whether this series was auto-detected
    """

    id: str
    name: str
    criteria: SeriesCriteria
    enabled: bool = True
    auto_detected: bool = False


class SeriesMatcherConfig(BaseModel):
    """Configuration for series matching.

    Attributes:
        enabled: Whether series matching is enabled
        series: List of configured series
        boost_matched_topics: Score boost for topics matching a series (0-1)
    """

    enabled: bool = Field(default=True)
    series: list[SeriesConfig] = Field(default_factory=list)
    boost_matched_topics: float = Field(
        default=0.2, ge=0.0, le=1.0, description="Score boost for series matches"
    )


__all__ = [
    "SeriesCriteria",
    "SeriesConfig",
    "SeriesMatcherConfig",
]
