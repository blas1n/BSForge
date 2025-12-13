"""Topic filtering configuration models.

All string values (categories, keywords, synonyms) are automatically
lowercased on load for consistent matching with normalized topic data.
"""

from pydantic import BaseModel, Field, field_validator


class CategoryFilter(BaseModel):
    """Category filter with optional weight.

    Attributes:
        name: Category name (e.g., "tech", "ai", "gaming") - lowercased on load
        weight: Weight multiplier for scoring (default 1.0)
        subcategories: Optional subcategories to include - lowercased on load
    """

    name: str
    weight: float = Field(default=1.0, ge=0.0, le=3.0)
    subcategories: list[str] = Field(default_factory=list)

    @field_validator("name", mode="before")
    @classmethod
    def lowercase_name(cls, v: str) -> str:
        return v.lower() if isinstance(v, str) else v

    @field_validator("subcategories", mode="before")
    @classmethod
    def lowercase_subcategories(cls, v: list[str]) -> list[str]:
        return [s.lower() for s in v] if v else []


class KeywordFilter(BaseModel):
    """Keyword filter with synonyms and weight.

    Attributes:
        keyword: Main keyword to match - lowercased on load
        weight: Weight multiplier for scoring (default 1.0)
        synonyms: Alternative forms of the keyword - lowercased on load
    """

    keyword: str
    weight: float = Field(default=1.0, ge=0.0, le=3.0)
    synonyms: list[str] = Field(default_factory=list)

    @field_validator("keyword", mode="before")
    @classmethod
    def lowercase_keyword(cls, v: str) -> str:
        return v.lower() if isinstance(v, str) else v

    @field_validator("synonyms", mode="before")
    @classmethod
    def lowercase_synonyms(cls, v: list[str]) -> list[str]:
        return [s.lower() for s in v] if v else []


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
        categories: Categories to reject - lowercased on load
        keywords: Keywords to reject - lowercased on load
    """

    categories: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)

    @field_validator("categories", mode="before")
    @classmethod
    def lowercase_categories(cls, v: list[str]) -> list[str]:
        return [c.lower() for c in v] if v else []

    @field_validator("keywords", mode="before")
    @classmethod
    def lowercase_keywords(cls, v: list[str]) -> list[str]:
        return [k.lower() for k in v] if v else []


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
