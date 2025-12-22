"""Topic filtering configuration models.

All terms are automatically lowercased on load.
"""

from pydantic import BaseModel, Field, field_validator

from app.config.validators import normalize_string_list


class FilteringConfig(BaseModel):
    """Topic filtering configuration.

    Attributes:
        include: Terms that must be matched (at least one)
        exclude: Terms that must NOT be matched (any)
    """

    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)

    @field_validator("include", mode="before")
    @classmethod
    def lowercase_include(cls, v: list[str]) -> list[str]:
        """Normalize include terms to lowercase."""
        return normalize_string_list(v)

    @field_validator("exclude", mode="before")
    @classmethod
    def lowercase_exclude(cls, v: list[str]) -> list[str]:
        """Normalize exclude terms to lowercase."""
        return normalize_string_list(v)


__all__ = ["FilteringConfig"]
