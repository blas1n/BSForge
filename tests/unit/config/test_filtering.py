"""Unit tests for filtering configuration models."""

from app.config.filtering import FilteringConfig


class TestFilteringConfig:
    """Tests for FilteringConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = FilteringConfig()
        assert config.include == []
        assert config.exclude == []

    def test_include_terms_lowercased(self):
        """Test include terms are automatically lowercased."""
        config = FilteringConfig(include=["AI", "MACHINE Learning", "TeSt"])
        assert config.include == ["ai", "machine learning", "test"]

    def test_exclude_terms_lowercased(self):
        """Test exclude terms are automatically lowercased."""
        config = FilteringConfig(exclude=["Politics", "RELIGION"])
        assert config.exclude == ["politics", "religion"]

    def test_both_include_and_exclude(self):
        """Test with both include and exclude terms."""
        config = FilteringConfig(
            include=["Tech", "AI"],
            exclude=["Politics", "Religion"],
        )
        assert config.include == ["tech", "ai"]
        assert config.exclude == ["politics", "religion"]

    def test_none_input_handled(self):
        """Test None input is converted to empty list."""
        # Pydantic handles None -> default factory
        config = FilteringConfig()
        assert config.include == []
        assert config.exclude == []

    def test_empty_list_preserved(self):
        """Test empty list is preserved."""
        config = FilteringConfig(include=[], exclude=[])
        assert config.include == []
        assert config.exclude == []

    def test_unicode_terms(self):
        """Test Korean/Unicode terms are handled."""
        config = FilteringConfig(
            include=["AI", "인공지능"],
            exclude=["정치", "종교"],
        )
        assert "ai" in config.include
        assert "인공지능" in config.include
        assert "정치" in config.exclude
        assert "종교" in config.exclude

    def test_mixed_case_preservation_after_lower(self):
        """Test that all terms end up lowercase."""
        config = FilteringConfig(include=["CamelCase", "UPPER", "lower", "MiXeD123"])
        for term in config.include:
            assert term == term.lower()

    def test_single_string_input(self):
        """Test single string input is converted to list."""
        # The validator handles single strings
        config = FilteringConfig(include="single")
        assert config.include == ["single"]
