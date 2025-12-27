"""Unit tests for ContentClassifier."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.infrastructure.llm import LLMResponse
from app.prompts.manager import PromptManager
from app.services.rag.classifier import ContentClassifier


class TestContentClassifier:
    """Test ContentClassifier functionality."""

    @pytest.fixture
    def mock_llm_client(self) -> AsyncMock:
        """Create mock LLM client."""
        client = AsyncMock()
        return client

    @pytest.fixture
    def mock_prompt_manager(self) -> MagicMock:
        """Create mock PromptManager."""
        manager = MagicMock(spec=PromptManager)
        manager.render.return_value = "Classify this content"
        return manager

    @pytest.fixture
    def classifier(
        self,
        mock_llm_client: AsyncMock,
        mock_prompt_manager: MagicMock,
    ) -> ContentClassifier:
        """Create ContentClassifier with mock client."""
        return ContentClassifier(
            llm_client=mock_llm_client,
            prompt_manager=mock_prompt_manager,
            model="anthropic/claude-3-5-haiku-20241022",
        )

    def _create_mock_response(self, text: str) -> LLMResponse:
        """Create mock LLM response."""
        return LLMResponse(
            content=text,
            model="anthropic/claude-3-5-haiku-20241022",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )

    @pytest.mark.asyncio
    async def test_classify_opinion(
        self, classifier: ContentClassifier, mock_llm_client: AsyncMock
    ) -> None:
        """Should classify opinion correctly."""
        mock_llm_client.complete.return_value = self._create_mock_response(
            "opinion: yes\nexample: no\nanalogy: no"
        )

        result = await classifier.classify_characteristics(
            "I think this approach is better because..."
        )

        assert result["is_opinion"] is True
        assert result["is_example"] is False
        assert result["is_analogy"] is False

    @pytest.mark.asyncio
    async def test_classify_example(
        self, classifier: ContentClassifier, mock_llm_client: AsyncMock
    ) -> None:
        """Should classify example correctly."""
        mock_llm_client.complete.return_value = self._create_mock_response(
            "opinion: no\nexample: yes\nanalogy: no"
        )

        result = await classifier.classify_characteristics(
            "For example, when you use Python for data analysis..."
        )

        assert result["is_opinion"] is False
        assert result["is_example"] is True
        assert result["is_analogy"] is False

    @pytest.mark.asyncio
    async def test_classify_analogy(
        self, classifier: ContentClassifier, mock_llm_client: AsyncMock
    ) -> None:
        """Should classify analogy correctly."""
        mock_llm_client.complete.return_value = self._create_mock_response(
            "opinion: no\nexample: no\nanalogy: yes"
        )

        result = await classifier.classify_characteristics("Think of it like a highway for data...")

        assert result["is_opinion"] is False
        assert result["is_example"] is False
        assert result["is_analogy"] is True

    @pytest.mark.asyncio
    async def test_classify_multiple_characteristics(
        self, classifier: ContentClassifier, mock_llm_client: AsyncMock
    ) -> None:
        """Should handle multiple characteristics."""
        mock_llm_client.complete.return_value = self._create_mock_response(
            "opinion: yes\nexample: yes\nanalogy: no"
        )

        result = await classifier.classify_characteristics(
            "I believe this is best, for example look at how..."
        )

        assert result["is_opinion"] is True
        assert result["is_example"] is True
        assert result["is_analogy"] is False

    @pytest.mark.asyncio
    async def test_classify_none(
        self, classifier: ContentClassifier, mock_llm_client: AsyncMock
    ) -> None:
        """Should handle text with no special characteristics."""
        mock_llm_client.complete.return_value = self._create_mock_response(
            "opinion: no\nexample: no\nanalogy: no"
        )

        result = await classifier.classify_characteristics("The function returns a list of items.")

        assert result["is_opinion"] is False
        assert result["is_example"] is False
        assert result["is_analogy"] is False

    @pytest.mark.asyncio
    async def test_classify_handles_llm_error(
        self, classifier: ContentClassifier, mock_llm_client: AsyncMock
    ) -> None:
        """Should return False for all on LLM error."""
        mock_llm_client.complete.side_effect = Exception("API Error")

        result = await classifier.classify_characteristics("Some text")

        assert result["is_opinion"] is False
        assert result["is_example"] is False
        assert result["is_analogy"] is False

    @pytest.mark.asyncio
    async def test_classify_handles_unexpected_response(
        self, classifier: ContentClassifier, mock_llm_client: AsyncMock
    ) -> None:
        """Should handle unexpected content gracefully."""
        mock_llm_client.complete.return_value = self._create_mock_response(
            "unexpected response format"
        )

        result = await classifier.classify_characteristics("Some text")

        # Should fall back to defaults on parse error
        assert result["is_opinion"] is False
        assert result["is_example"] is False
        assert result["is_analogy"] is False

    @pytest.mark.asyncio
    async def test_classify_batch(
        self, classifier: ContentClassifier, mock_llm_client: AsyncMock
    ) -> None:
        """Should classify multiple texts in batch."""
        responses = [
            self._create_mock_response("opinion: yes\nexample: no\nanalogy: no"),
            self._create_mock_response("opinion: no\nexample: yes\nanalogy: no"),
            self._create_mock_response("opinion: no\nexample: no\nanalogy: yes"),
        ]
        mock_llm_client.complete.side_effect = responses

        texts = [
            "I think this is better",
            "For example, consider this case",
            "It's like a highway for data",
        ]
        results = await classifier.classify_batch(texts)

        assert len(results) == 3
        assert results[0]["is_opinion"] is True
        assert results[1]["is_example"] is True
        assert results[2]["is_analogy"] is True

    @pytest.mark.asyncio
    async def test_uses_prompt_manager(
        self,
        mock_llm_client: AsyncMock,
        mock_prompt_manager: MagicMock,
    ) -> None:
        """Should use PromptManager for template rendering."""
        mock_llm_client.complete.return_value = LLMResponse(
            content="opinion: no\nexample: no\nanalogy: no",
            model="anthropic/claude-3-5-haiku-20241022",
            usage={},
        )

        classifier = ContentClassifier(
            llm_client=mock_llm_client,
            prompt_manager=mock_prompt_manager,
        )
        await classifier.classify_characteristics("Test text")

        mock_prompt_manager.render.assert_called_once()

    @pytest.mark.asyncio
    async def test_case_insensitive_parsing(
        self, classifier: ContentClassifier, mock_llm_client: AsyncMock
    ) -> None:
        """Should parse response case-insensitively."""
        mock_llm_client.complete.return_value = self._create_mock_response(
            "OPINION: YES\nEXAMPLE: NO\nANALOGY: NO"
        )

        result = await classifier.classify_characteristics("Some text")

        assert result["is_opinion"] is True
        assert result["is_example"] is False
        assert result["is_analogy"] is False
