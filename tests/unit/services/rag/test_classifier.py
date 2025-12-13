"""Unit tests for ContentClassifier."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.rag.classifier import ContentClassifier


class TestContentClassifier:
    """Test ContentClassifier functionality."""

    @pytest.fixture
    def mock_llm_client(self) -> AsyncMock:
        """Create mock Anthropic client."""
        client = AsyncMock()
        return client

    @pytest.fixture
    def classifier(self, mock_llm_client: AsyncMock) -> ContentClassifier:
        """Create ContentClassifier with mock client."""
        return ContentClassifier(
            llm_client=mock_llm_client,
            model="claude-3-5-haiku-20241022",
        )

    def _create_mock_response(self, text: str) -> MagicMock:
        """Create mock LLM response."""
        content_block = MagicMock()
        content_block.text = text
        response = MagicMock()
        response.content = [content_block]
        return response

    @pytest.mark.asyncio
    async def test_classify_opinion(
        self, classifier: ContentClassifier, mock_llm_client: AsyncMock
    ) -> None:
        """Should classify opinion correctly."""
        mock_llm_client.messages.create.return_value = self._create_mock_response(
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
        mock_llm_client.messages.create.return_value = self._create_mock_response(
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
        mock_llm_client.messages.create.return_value = self._create_mock_response(
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
        mock_llm_client.messages.create.return_value = self._create_mock_response(
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
        mock_llm_client.messages.create.return_value = self._create_mock_response(
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
        mock_llm_client.messages.create.side_effect = Exception("API Error")

        result = await classifier.classify_characteristics("Some text")

        assert result["is_opinion"] is False
        assert result["is_example"] is False
        assert result["is_analogy"] is False

    @pytest.mark.asyncio
    async def test_classify_handles_unexpected_response_type(
        self, classifier: ContentClassifier, mock_llm_client: AsyncMock
    ) -> None:
        """Should handle unexpected content type gracefully."""
        # Create response without text attribute
        content_block = MagicMock(spec=[])  # No attributes
        response = MagicMock()
        response.content = [content_block]
        mock_llm_client.messages.create.return_value = response

        result = await classifier.classify_characteristics("Some text")

        # Should fall back to defaults on error
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
        mock_llm_client.messages.create.side_effect = responses

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
    async def test_uses_prompt_manager(self, mock_llm_client: AsyncMock) -> None:
        """Should use PromptManager for template rendering."""
        with patch("app.services.rag.classifier.get_prompt_manager") as mock_get_pm:
            mock_pm = MagicMock()
            mock_pm.render.return_value = "Rendered prompt"
            mock_get_pm.return_value = mock_pm

            mock_llm_client.messages.create.return_value = self._create_mock_response(
                "opinion: no\nexample: no\nanalogy: no"
            )

            classifier = ContentClassifier(llm_client=mock_llm_client)
            await classifier.classify_characteristics("Test text")

            mock_pm.render.assert_called_once()

    @pytest.mark.asyncio
    async def test_case_insensitive_parsing(
        self, classifier: ContentClassifier, mock_llm_client: AsyncMock
    ) -> None:
        """Should parse response case-insensitively."""
        mock_llm_client.messages.create.return_value = self._create_mock_response(
            "OPINION: YES\nEXAMPLE: NO\nANALOGY: NO"
        )

        result = await classifier.classify_characteristics("Some text")

        assert result["is_opinion"] is True
        assert result["is_example"] is False
        assert result["is_analogy"] is False
