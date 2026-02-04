"""Unit tests for topic normalizer."""

import json
from unittest.mock import MagicMock

import pytest

from app.services.collector.normalizer import ClassificationResult, TopicNormalizer


class TestClassificationResult:
    """Tests for ClassificationResult model."""

    def test_basic_result(self):
        """Test creating basic classification result."""
        result = ClassificationResult(
            terms=["ai", "technology"],
            entities={"companies": ["OpenAI"]},
            summary="A summary of the topic",
        )

        assert result.terms == ["ai", "technology"]
        assert result.entities == {"companies": ["OpenAI"]}
        assert result.summary == "A summary of the topic"

    def test_empty_entities(self):
        """Test classification with empty entities."""
        result = ClassificationResult(
            terms=["general"],
            entities={},
            summary="General summary",
        )

        assert result.entities == {}


class TestTopicNormalizerInit:
    """Tests for TopicNormalizer initialization."""

    def test_init(self):
        """Test normalizer initialization."""
        mock_llm = MagicMock()
        mock_prompt_manager = MagicMock()

        normalizer = TopicNormalizer(
            llm_client=mock_llm,
            prompt_manager=mock_prompt_manager,
        )

        assert normalizer.llm_client == mock_llm
        assert normalizer.prompt_manager == mock_prompt_manager
        assert normalizer.supported_languages == {"en", "ko"}


class TestTopicNormalizerLanguageDetection:
    """Tests for language detection."""

    @pytest.fixture
    def normalizer(self):
        """Create normalizer with mocks."""
        mock_llm = MagicMock()
        mock_prompt_manager = MagicMock()
        return TopicNormalizer(
            llm_client=mock_llm,
            prompt_manager=mock_prompt_manager,
        )

    @pytest.mark.asyncio
    async def test_detect_korean(self, normalizer):
        """Test detecting Korean text."""
        result = await normalizer._detect_language("클로드 3.5 소넷 발표")
        assert result == "ko"

    @pytest.mark.asyncio
    async def test_detect_english(self, normalizer):
        """Test detecting English text."""
        result = await normalizer._detect_language("Claude 3.5 Sonnet Released")
        assert result == "en"

    @pytest.mark.asyncio
    async def test_detect_mixed_defaults_to_korean(self, normalizer):
        """Test mixed text with Korean characters detects as Korean."""
        result = await normalizer._detect_language("AI 기술의 미래 Future")
        assert result == "ko"

    @pytest.mark.asyncio
    async def test_detect_numbers_only_defaults_to_english(self, normalizer):
        """Test text without Hangul defaults to English."""
        result = await normalizer._detect_language("2024 AI Summit")
        assert result == "en"


class TestTopicNormalizerCleanTitle:
    """Tests for title cleaning."""

    @pytest.fixture
    def normalizer(self):
        """Create normalizer with mocks."""
        mock_llm = MagicMock()
        mock_prompt_manager = MagicMock()
        return TopicNormalizer(
            llm_client=mock_llm,
            prompt_manager=mock_prompt_manager,
        )

    def test_removes_urls(self, normalizer):
        """Test URL removal."""
        result = normalizer._clean_title("Check this out https://example.com cool!")
        assert "https" not in result
        assert "example.com" not in result

    def test_removes_extra_whitespace(self, normalizer):
        """Test whitespace normalization."""
        result = normalizer._clean_title("Too    many   spaces")
        assert result == "too many spaces"

    def test_strips_leading_trailing_whitespace(self, normalizer):
        """Test stripping whitespace."""
        result = normalizer._clean_title("  padded title  ")
        assert result == "padded title"

    def test_removes_show_hn_prefix(self, normalizer):
        """Test HN prefix removal."""
        result = normalizer._clean_title("Show HN: My cool project")
        assert result == "my cool project"

    def test_removes_ask_hn_prefix(self, normalizer):
        """Test Ask HN prefix removal."""
        result = normalizer._clean_title("Ask HN: What's your favorite editor?")
        assert result == "what's your favorite editor?"

    def test_removes_tell_hn_prefix(self, normalizer):
        """Test Tell HN prefix removal."""
        result = normalizer._clean_title("Tell HN: I built something")
        assert result == "i built something"

    def test_converts_to_lowercase(self, normalizer):
        """Test lowercase conversion."""
        result = normalizer._clean_title("UPPERCASE Title Here")
        assert result == "uppercase title here"


class TestTopicNormalizerHashGeneration:
    """Tests for hash generation."""

    @pytest.fixture
    def normalizer(self):
        """Create normalizer with mocks."""
        mock_llm = MagicMock()
        mock_prompt_manager = MagicMock()
        return TopicNormalizer(
            llm_client=mock_llm,
            prompt_manager=mock_prompt_manager,
        )

    def test_generates_64_char_hash(self, normalizer):
        """Test hash is 64 characters (SHA-256 hex)."""
        result = normalizer._generate_hash("test title", ["ai", "tech"])
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_same_input_same_hash(self, normalizer):
        """Test deterministic hash generation."""
        hash1 = normalizer._generate_hash("test title", ["ai", "tech"])
        hash2 = normalizer._generate_hash("test title", ["ai", "tech"])
        assert hash1 == hash2

    def test_different_title_different_hash(self, normalizer):
        """Test different titles produce different hashes."""
        hash1 = normalizer._generate_hash("title one", ["ai"])
        hash2 = normalizer._generate_hash("title two", ["ai"])
        assert hash1 != hash2

    def test_different_terms_different_hash(self, normalizer):
        """Test different terms produce different hashes."""
        hash1 = normalizer._generate_hash("same title", ["ai"])
        hash2 = normalizer._generate_hash("same title", ["ml"])
        assert hash1 != hash2

    def test_term_order_independent(self, normalizer):
        """Test hash is independent of term order (sorted)."""
        hash1 = normalizer._generate_hash("title", ["ai", "ml", "tech"])
        hash2 = normalizer._generate_hash("title", ["tech", "ai", "ml"])
        assert hash1 == hash2


class TestTopicNormalizerExtractJson:
    """Tests for JSON extraction from LLM responses."""

    @pytest.fixture
    def normalizer(self):
        """Create normalizer with mocks."""
        mock_llm = MagicMock()
        mock_prompt_manager = MagicMock()
        return TopicNormalizer(
            llm_client=mock_llm,
            prompt_manager=mock_prompt_manager,
        )

    def test_extracts_clean_json(self, normalizer):
        """Test extracting clean JSON."""
        text = '{"terms": ["ai"], "entities": {}, "summary": "test"}'
        result = normalizer._extract_first_json_object(text)

        assert result["terms"] == ["ai"]
        assert result["summary"] == "test"

    def test_extracts_json_with_trailing_text(self, normalizer):
        """Test extracting JSON with extra text after."""
        text = '{"terms": ["ai"], "entities": {}, "summary": "test"}\n\nSome extra explanation'
        result = normalizer._extract_first_json_object(text)

        assert result["terms"] == ["ai"]

    def test_extracts_json_with_leading_text(self, normalizer):
        """Test extracting JSON with text before."""
        text = 'Here is the result: {"terms": ["ai"], "entities": {}, "summary": "test"}'
        result = normalizer._extract_first_json_object(text)

        assert result["terms"] == ["ai"]

    def test_handles_nested_json(self, normalizer):
        """Test handling nested JSON objects."""
        text = '{"terms": ["ai"], "entities": {"companies": ["OpenAI"]}, "summary": "test"}'
        result = normalizer._extract_first_json_object(text)

        assert result["entities"]["companies"] == ["OpenAI"]

    def test_raises_on_no_json(self, normalizer):
        """Test error on text without JSON."""
        with pytest.raises(json.JSONDecodeError):
            normalizer._extract_first_json_object("No JSON here at all")

    def test_handles_escaped_quotes_in_strings(self, normalizer):
        """Test handling escaped quotes inside JSON strings."""
        text = '{"terms": ["ai"], "entities": {}, "summary": "Test \\"quoted\\" text"}'
        result = normalizer._extract_first_json_object(text)

        assert "quoted" in result["summary"]
