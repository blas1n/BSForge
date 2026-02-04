"""Unit tests for font discovery module."""

from unittest.mock import patch

from app.infrastructure.fonts import (
    clear_font_cache,
    find_font,
    find_font_by_name,
    find_font_path,
)


class TestFindFont:
    """Tests for find_font function."""

    @patch("app.infrastructure.fonts.fontconfig")
    def test_find_font_success(self, mock_fontconfig):
        """Test successful font lookup."""
        mock_fontconfig.match.return_value = {
            "family": "Noto Sans CJK KR",
            "file": "/usr/share/fonts/noto/NotoSansCJK-Bold.otf",
            "style": "Bold",
        }

        # Clear cache before test
        find_font.cache_clear()

        result = find_font(":lang=ko:weight=bold")

        assert result is not None
        assert result["family"] == "Noto Sans CJK KR"
        assert result["file"] == "/usr/share/fonts/noto/NotoSansCJK-Bold.otf"
        mock_fontconfig.match.assert_called_with(":lang=ko:weight=bold")

    @patch("app.infrastructure.fonts.fontconfig")
    def test_find_font_not_found(self, mock_fontconfig):
        """Test font not found returns None."""
        mock_fontconfig.match.return_value = None

        find_font.cache_clear()
        result = find_font("nonexistent-font")

        assert result is None

    @patch("app.infrastructure.fonts.fontconfig")
    def test_find_font_empty_file(self, mock_fontconfig):
        """Test font result with empty file returns None."""
        mock_fontconfig.match.return_value = {"family": "Test", "file": ""}

        find_font.cache_clear()
        result = find_font("test-font")

        assert result is None

    @patch("app.infrastructure.fonts.fontconfig")
    def test_find_font_exception(self, mock_fontconfig):
        """Test font lookup handles exception."""
        mock_fontconfig.match.side_effect = Exception("fontconfig error")

        find_font.cache_clear()
        result = find_font("error-font")

        assert result is None

    @patch("app.infrastructure.fonts.fontconfig")
    def test_find_font_cached(self, mock_fontconfig):
        """Test that results are cached."""
        mock_fontconfig.match.return_value = {
            "family": "Test",
            "file": "/test/path.otf",
            "style": "Regular",
        }

        find_font.cache_clear()

        # First call
        result1 = find_font("cached-font")
        # Second call should use cache
        result2 = find_font("cached-font")

        assert result1 == result2
        # Should only be called once due to caching
        assert mock_fontconfig.match.call_count == 1


class TestFindFontPath:
    """Tests for find_font_path function."""

    @patch("app.infrastructure.fonts.fontconfig")
    def test_find_font_path_success(self, mock_fontconfig):
        """Test successful path lookup."""
        mock_fontconfig.match.return_value = {
            "family": "Test",
            "file": "/test/font.otf",
            "style": "Bold",
        }

        find_font.cache_clear()
        result = find_font_path("test-font")

        assert result == "/test/font.otf"

    @patch("app.infrastructure.fonts.fontconfig")
    def test_find_font_path_not_found(self, mock_fontconfig):
        """Test path lookup returns None when not found."""
        mock_fontconfig.match.return_value = None

        find_font.cache_clear()
        result = find_font_path("missing-font")

        assert result is None


class TestFindFontByName:
    """Tests for find_font_by_name function."""

    @patch("app.infrastructure.fonts.fontconfig")
    def test_find_bold_suffix(self, mock_fontconfig):
        """Test parsing Bold suffix."""
        mock_fontconfig.match.return_value = {
            "family": "Pretendard",
            "file": "/fonts/Pretendard-Bold.otf",
            "style": "Bold",
        }

        find_font.cache_clear()
        result = find_font_by_name("Pretendard-Bold")

        assert result == "/fonts/Pretendard-Bold.otf"
        # First call should be with parsed weight
        mock_fontconfig.match.assert_called_with("Pretendard:weight=bold")

    @patch("app.infrastructure.fonts.fontconfig")
    def test_find_regular_suffix(self, mock_fontconfig):
        """Test parsing Regular suffix."""
        mock_fontconfig.match.return_value = {
            "family": "Noto Sans",
            "file": "/fonts/NotoSans-Regular.otf",
            "style": "Regular",
        }

        find_font.cache_clear()
        result = find_font_by_name("Noto Sans-Regular")

        assert result == "/fonts/NotoSans-Regular.otf"

    @patch("app.infrastructure.fonts.fontconfig")
    def test_find_light_suffix(self, mock_fontconfig):
        """Test parsing Light suffix."""
        mock_fontconfig.match.return_value = {
            "family": "Open Sans",
            "file": "/fonts/OpenSans-Light.otf",
            "style": "Light",
        }

        find_font.cache_clear()
        find_font_by_name("Open Sans-Light")

        mock_fontconfig.match.assert_called_with("Open Sans:weight=light")

    @patch("app.infrastructure.fonts.fontconfig")
    def test_find_medium_suffix(self, mock_fontconfig):
        """Test parsing Medium suffix."""
        mock_fontconfig.match.return_value = {
            "family": "Roboto",
            "file": "/fonts/Roboto-Medium.otf",
            "style": "Medium",
        }

        find_font.cache_clear()
        find_font_by_name("Roboto-Medium")

        mock_fontconfig.match.assert_called_with("Roboto:weight=medium")

    @patch("app.infrastructure.fonts.fontconfig")
    def test_find_black_suffix(self, mock_fontconfig):
        """Test parsing Black suffix."""
        mock_fontconfig.match.return_value = {
            "family": "Inter",
            "file": "/fonts/Inter-Black.otf",
            "style": "Black",
        }

        find_font.cache_clear()
        find_font_by_name("Inter-Black")

        mock_fontconfig.match.assert_called_with("Inter:weight=black")

    @patch("app.infrastructure.fonts.fontconfig")
    def test_find_no_suffix(self, mock_fontconfig):
        """Test font without weight suffix."""
        mock_fontconfig.match.return_value = {
            "family": "Arial",
            "file": "/fonts/Arial.ttf",
            "style": "Regular",
        }

        find_font.cache_clear()
        find_font_by_name("Arial")

        # Should try with regular weight first
        mock_fontconfig.match.assert_called_with("Arial:weight=regular")

    @patch("app.infrastructure.fonts.fontconfig")
    def test_fallback_to_original_name(self, mock_fontconfig):
        """Test fallback to original name when weight query fails."""

        def side_effect(query):
            if ":weight=" in query:
                return None
            if query == "CustomFont":
                return {"family": "Custom", "file": "/fonts/custom.otf", "style": "Regular"}
            return None

        mock_fontconfig.match.side_effect = side_effect

        find_font.cache_clear()
        result = find_font_by_name("CustomFont")

        assert result == "/fonts/custom.otf"

    @patch("app.infrastructure.fonts.fontconfig")
    def test_fallback_to_default(self, mock_fontconfig):
        """Test fallback to default font when not found."""

        def side_effect(query):
            if query == "sans-serif:weight=bold":
                return {"family": "Sans", "file": "/fallback/sans.otf", "style": "Bold"}
            return None

        mock_fontconfig.match.side_effect = side_effect

        find_font.cache_clear()
        result = find_font_by_name("NonExistentFont")

        assert result == "/fallback/sans.otf"

    @patch("app.infrastructure.fonts.fontconfig")
    def test_hardcoded_fallback(self, mock_fontconfig):
        """Test hardcoded fallback when even default fails."""
        mock_fontconfig.match.return_value = None

        find_font.cache_clear()
        result = find_font_by_name("TotallyMissing")

        assert result == "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

    @patch("app.infrastructure.fonts.fontconfig")
    def test_custom_fallback(self, mock_fontconfig):
        """Test custom fallback query."""

        def side_effect(query):
            if query == "monospace:weight=regular":
                return {"family": "Mono", "file": "/fonts/mono.otf", "style": "Regular"}
            return None

        mock_fontconfig.match.side_effect = side_effect

        find_font.cache_clear()
        result = find_font_by_name("Missing", fallback="monospace:weight=regular")

        assert result == "/fonts/mono.otf"


class TestClearFontCache:
    """Tests for clear_font_cache function."""

    @patch("app.infrastructure.fonts.fontconfig")
    def test_clear_cache(self, mock_fontconfig):
        """Test clearing font cache."""
        mock_fontconfig.match.return_value = {
            "family": "Test",
            "file": "/test.otf",
            "style": "Regular",
        }

        # Populate cache
        find_font.cache_clear()
        find_font("test-query")

        # Clear cache
        clear_font_cache()

        # Call again - should hit fontconfig again
        find_font("test-query")

        # Should be called twice (before and after cache clear)
        assert mock_fontconfig.match.call_count == 2
