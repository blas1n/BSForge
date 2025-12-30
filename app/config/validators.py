"""Shared validators for Pydantic config models.

This module provides common validation utilities that reduce code
duplication across configuration models:
- Weight sum validation
- Range list validation
- String list normalization
"""

from typing import Any


def validate_weights_sum(
    values: dict[str, float],
    tolerance: float = 0.01,
    expected_sum: float = 1.0,
) -> None:
    """Validate that numeric values sum to expected value.

    Args:
        values: Dictionary of field names to weight values
        tolerance: Allowed deviation from expected_sum
        expected_sum: Expected sum of all weights

    Raises:
        ValueError: If sum deviates from expected by more than tolerance
    """
    total = sum(values.values())
    if abs(total - expected_sum) > tolerance:
        raise ValueError(
            f"Weights must sum to {expected_sum} (got {total:.2f}). " f"Values: {values}"
        )


def validate_range_list(
    values: list[int],
    min_val: int,
    max_val: int,
    field_name: str = "Values",
) -> list[int]:
    """Validate list of integers are within range, dedupe and sort.

    Args:
        values: List of integers to validate
        min_val: Minimum allowed value (inclusive)
        max_val: Maximum allowed value (inclusive)
        field_name: Name for error messages

    Returns:
        Sorted, deduplicated list

    Raises:
        ValueError: If any value is out of range
    """
    out_of_range = [v for v in values if v < min_val or v > max_val]
    if out_of_range:
        raise ValueError(
            f"{field_name} must be between {min_val} and {max_val}. "
            f"Invalid values: {out_of_range}"
        )
    return sorted(set(values))


def normalize_string_list(value: Any) -> list[str]:
    """Normalize string list to lowercase.

    Handles None, single strings, and lists.

    Args:
        value: Input value (None, str, or list[str])

    Returns:
        List of lowercased strings
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [value.lower()]
    if isinstance(value, list):
        return [s.lower() for s in value if isinstance(s, str)]
    return []


__all__ = [
    "validate_weights_sum",
    "validate_range_list",
    "normalize_string_list",
]
