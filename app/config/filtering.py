"""Topic filtering configuration models."""

from pydantic import BaseModel, Field


class CategoryFilter(BaseModel):
    """Category filter with optional weight.

    Attributes:
        name: Category name (e.g., "tech", "ai", "gaming")
        weight: Weight multiplier for scoring (default 1.0)
        subcategories: Optional subcategories to include
    """

    name: str
    weight: float = Field(default=1.0, ge=0.0, le=3.0)
    subcategories: list[str] = Field(default_factory=list)


class KeywordFilter(BaseModel):
    """Keyword filter with synonyms and weight.

    Attributes:
        keyword: Main keyword to match
        weight: Weight multiplier for scoring (default 1.0)
        synonyms: Alternative forms of the keyword
    """

    keyword: str
    weight: float = Field(default=1.0, ge=0.0, le=3.0)
    synonyms: list[str] = Field(default_factory=list)


class IncludeFilters(BaseModel):
    """Filters for topics to include.

    Topics matching these filters get higher scores.

    Attributes:
        categories: Categories to prioritize
        keywords: Keywords to prioritize
    """

    categories: list[CategoryFilter] = Field(default_factory=list)
    keywords: list[KeywordFilter] = Field(default_factory=list)


class ExcludeFilters(BaseModel):
    """Filters for topics to exclude.

    Topics matching these filters are rejected.

    Attributes:
        categories: Categories to reject
        keywords: Keywords to reject
    """

    categories: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class TopicFilterConfig(BaseModel):
    """Complete topic filtering configuration.

    Defines what topics to include/prioritize and what to exclude.

    Attributes:
        include: Filters for topics to include/prioritize
        exclude: Filters for topics to reject
        require_category_match: If True, topic must match at least one include category
        require_keyword_match: If True, topic must match at least one include keyword
    """

    include: IncludeFilters = Field(default_factory=IncludeFilters)
    exclude: ExcludeFilters = Field(default_factory=ExcludeFilters)
    require_category_match: bool = Field(
        default=False, description="Require at least one category match"
    )
    require_keyword_match: bool = Field(
        default=False, description="Require at least one keyword match"
    )


__all__ = [
    "CategoryFilter",
    "KeywordFilter",
    "IncludeFilters",
    "ExcludeFilters",
    "TopicFilterConfig",
]
