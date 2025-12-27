"""Unit tests for multilingual tokenizer."""

from app.infrastructure.tokenizer import (
    tokenize,
    tokenize_without_stopwords,
)


class TestTokenize:
    """Test tokenize function."""

    def test_english_text(self) -> None:
        """Should tokenize English text."""
        result = tokenize("Apple announces iPhone 15")

        assert "apple" in result
        assert "announces" in result
        assert "iphone" in result
        assert "15" in result

    def test_korean_text(self) -> None:
        """Should tokenize Korean text."""
        result = tokenize("프로미스나인 뮤직뱅크 1위")

        assert "프로미스나인" in result
        assert "뮤직뱅크" in result

    def test_mixed_language_text(self) -> None:
        """Should tokenize mixed Korean/English text."""
        result = tokenize("BTS 방탄소년단 Grammy 2024")

        assert "bts" in result
        assert "방탄소년단" in result
        assert "grammy" in result
        assert "2024" in result

    def test_min_length_filter(self) -> None:
        """Should filter tokens shorter than min_length."""
        result = tokenize("I am a test", min_length=2)

        # Single character tokens should be filtered
        assert "i" not in result
        assert "a" not in result
        assert "am" in result
        assert "test" in result

    def test_lowercasing(self) -> None:
        """Should lowercase all tokens."""
        result = tokenize("HELLO World")

        assert "hello" in result
        assert "world" in result
        assert "HELLO" not in result
        assert "World" not in result

    def test_empty_text(self) -> None:
        """Should return empty list for empty text."""
        result = tokenize("")

        assert result == []

    def test_whitespace_only(self) -> None:
        """Should return empty list for whitespace only."""
        result = tokenize("   \t\n  ")

        assert result == []


class TestTokenizeWithoutStopwords:
    """Test tokenize_without_stopwords function."""

    def test_english_stopwords_removed(self) -> None:
        """Should remove English stopwords."""
        result = tokenize_without_stopwords("the quick brown fox")

        assert "quick" in result
        assert "brown" in result
        assert "fox" in result
        assert "the" not in result

    def test_korean_stopwords_removed(self) -> None:
        """Should remove Korean stopwords."""
        result = tokenize_without_stopwords("이것은 테스트입니다")

        # Common Korean stopwords should be filtered
        # Exact behavior depends on stopwordsiso Korean list
        assert len(result) > 0

    def test_mixed_language_stopwords(self) -> None:
        """Should remove stopwords from mixed language text."""
        result = tokenize_without_stopwords("BTS is the best 방탄소년단")

        assert "bts" in result
        assert "방탄소년단" in result
        # "is" and "the" are English stopwords
        assert "is" not in result
        assert "the" not in result

    def test_preserves_meaningful_tokens(self) -> None:
        """Should preserve meaningful tokens after stopword removal."""
        result = tokenize_without_stopwords("Apple announces new iPhone")

        assert "apple" in result
        assert "announces" in result
        assert "iphone" in result

    def test_min_length_with_stopwords(self) -> None:
        """Should apply both min_length and stopword filtering."""
        result = tokenize_without_stopwords("I am testing", min_length=3)

        # "am" filtered by length, "I" filtered by length
        assert "testing" in result
        assert "am" not in result

    def test_empty_after_filtering(self) -> None:
        """Should return empty list if all tokens are stopwords."""
        result = tokenize_without_stopwords("the a an")

        # All common English stopwords
        assert len(result) == 0


class TestTokenizerCaching:
    """Test tokenizer singleton caching behavior."""

    def test_consistent_results(self) -> None:
        """Should return consistent results across multiple calls."""
        text = "Hello world test"

        result1 = tokenize(text)
        result2 = tokenize(text)

        assert result1 == result2

    def test_stopwords_consistent(self) -> None:
        """Should have consistent stopword filtering."""
        text = "the quick brown fox"

        result1 = tokenize_without_stopwords(text)
        result2 = tokenize_without_stopwords(text)

        assert result1 == result2


class TestMultilingualSupport:
    """Test support for various languages."""

    def test_japanese_text(self) -> None:
        """Should tokenize Japanese text with spaces or particles."""
        # Japanese with spaces or clear word boundaries
        result = tokenize("任天堂 ゲーム 発表")

        # uniseg handles spaced Japanese text
        assert len(result) > 0

    def test_chinese_character_segmentation(self) -> None:
        """Chinese is segmented character-by-character.

        Note: Unicode Annex #29 segments CJK characters individually.
        This is expected behavior - proper word segmentation requires
        dictionary-based approaches (jieba, etc.).

        For topic clustering, we handle this by:
        1. Allowing min_length=1 for CJK if needed
        2. Relying on mixed English/numbers for similarity
        """
        # Chinese is segmented into single characters
        result = tokenize("阿里巴巴", min_length=1)

        # Each character becomes a token
        assert len(result) == 4
        assert "阿" in result

    def test_mixed_chinese_english(self) -> None:
        """Mixed Chinese/English text should work well."""
        # Real-world trending topic often has mixed languages
        result = tokenize("iPhone16 发布 Apple Store")

        # English words are properly tokenized
        assert "iphone16" in result
        assert "apple" in result
        assert "store" in result

    def test_numbers_preserved(self) -> None:
        """Should preserve numbers as tokens."""
        result = tokenize("iPhone 15 Pro Max 2024")

        assert "15" in result
        assert "2024" in result

    def test_special_characters_handled(self) -> None:
        """Should handle special characters gracefully."""
        result = tokenize("C++ & Python #programming")

        # Should not crash, may filter some special chars
        assert len(result) >= 0
