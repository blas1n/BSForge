"""Unit tests for config validators."""

import pytest

from app.config.validators import (
    normalize_string_list,
    validate_range_list,
    validate_weights_sum,
)


class TestValidateWeightsSum:
    """Tests for validate_weights_sum function."""

    def test_valid_sum_exact(self):
        """Test weights that sum to exactly 1.0."""
        values = {"a": 0.3, "b": 0.3, "c": 0.4}
        # Should not raise
        validate_weights_sum(values)

    def test_valid_sum_within_tolerance(self):
        """Test weights within tolerance."""
        values = {"a": 0.333, "b": 0.333, "c": 0.333}  # Sum = 0.999
        # Should not raise with default tolerance
        validate_weights_sum(values)

    def test_invalid_sum_too_high(self):
        """Test weights that sum to more than 1.0."""
        values = {"a": 0.5, "b": 0.6}
        with pytest.raises(ValueError, match="must sum to 1.0"):
            validate_weights_sum(values)

    def test_invalid_sum_too_low(self):
        """Test weights that sum to less than 1.0."""
        values = {"a": 0.2, "b": 0.3}
        with pytest.raises(ValueError, match="must sum to 1.0"):
            validate_weights_sum(values)

    def test_custom_expected_sum(self):
        """Test with custom expected sum."""
        values = {"a": 0.5, "b": 0.5}
        validate_weights_sum(values, expected_sum=1.0)

        values2 = {"a": 1.0, "b": 1.0}
        validate_weights_sum(values2, expected_sum=2.0)

    def test_custom_tolerance(self):
        """Test with custom tolerance."""
        values = {"a": 0.4, "b": 0.5}  # Sum = 0.9
        # Fails with default tolerance
        with pytest.raises(ValueError):
            validate_weights_sum(values)
        # Passes with larger tolerance
        validate_weights_sum(values, tolerance=0.15)

    def test_empty_values(self):
        """Test with empty values dict."""
        values: dict[str, float] = {}
        with pytest.raises(ValueError, match="must sum to 1.0"):
            validate_weights_sum(values)


class TestValidateRangeList:
    """Tests for validate_range_list function."""

    def test_valid_range(self):
        """Test values within valid range."""
        result = validate_range_list([1, 2, 3], 0, 10)
        assert result == [1, 2, 3]

    def test_deduplication(self):
        """Test duplicate values are removed."""
        result = validate_range_list([1, 1, 2, 2, 3], 0, 10)
        assert result == [1, 2, 3]

    def test_sorting(self):
        """Test values are sorted."""
        result = validate_range_list([3, 1, 2], 0, 10)
        assert result == [1, 2, 3]

    def test_out_of_range_above(self):
        """Test value above max raises error."""
        with pytest.raises(ValueError, match="must be between"):
            validate_range_list([1, 2, 15], 0, 10)

    def test_out_of_range_below(self):
        """Test value below min raises error."""
        with pytest.raises(ValueError, match="must be between"):
            validate_range_list([-1, 2, 3], 0, 10)

    def test_custom_field_name(self):
        """Test custom field name in error message."""
        with pytest.raises(ValueError, match="Hours must be between"):
            validate_range_list([25], 0, 23, field_name="Hours")

    def test_empty_list(self):
        """Test empty list returns empty list."""
        result = validate_range_list([], 0, 10)
        assert result == []

    def test_boundary_values(self):
        """Test boundary values are accepted."""
        result = validate_range_list([0, 10], 0, 10)
        assert result == [0, 10]


class TestNormalizeStringList:
    """Tests for normalize_string_list function."""

    def test_list_input(self):
        """Test list of strings is lowercased."""
        result = normalize_string_list(["Hello", "WORLD", "TeSt"])
        assert result == ["hello", "world", "test"]

    def test_single_string(self):
        """Test single string is converted to list."""
        result = normalize_string_list("Hello")
        assert result == ["hello"]

    def test_none_input(self):
        """Test None returns empty list."""
        result = normalize_string_list(None)
        assert result == []

    def test_empty_list(self):
        """Test empty list returns empty list."""
        result = normalize_string_list([])
        assert result == []

    def test_mixed_types_in_list(self):
        """Test non-string items in list are ignored."""
        result = normalize_string_list(["hello", 123, "world", None])
        assert result == ["hello", "world"]

    def test_non_list_non_string(self):
        """Test non-list, non-string returns empty list."""
        result = normalize_string_list(123)
        assert result == []
