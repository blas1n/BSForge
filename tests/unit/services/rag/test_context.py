"""Unit tests for ContextBuilder."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config.rag import GenerationConfig
from app.services.rag.context import (
    ContextBuilder,
    GenerationContext,
    RetrievedContent,
)

from .conftest import create_retrieval_result


class TestRetrievedContent:
    """Test RetrievedContent dataclass."""

    def test_create_retrieved_content(self) -> None:
        """Should create RetrievedContent instance."""
        content = RetrievedContent(
            similar=[],
            opinions=[],
            examples=[],
            hooks=[],
        )

        assert content.similar == []
        assert content.opinions == []
        assert content.examples == []
        assert content.hooks == []

    def test_retrieved_content_with_results(self) -> None:
        """Should store retrieval results."""
        result = create_retrieval_result(
            text="Sample text",
            score=0.9,
        )

        content = RetrievedContent(
            similar=[result],
            opinions=[],
            examples=[],
            hooks=[],
        )

        assert len(content.similar) == 1
        assert content.similar[0].text == "Sample text"


class TestGenerationContext:
    """Test GenerationContext dataclass."""

    def test_create_generation_context(self) -> None:
        """Should create GenerationContext instance."""
        mock_topic = MagicMock()
        mock_persona = MagicMock()
        mock_retrieved = RetrievedContent(similar=[], opinions=[], examples=[], hooks=[])
        mock_config = GenerationConfig()

        context = GenerationContext(
            topic=mock_topic,
            persona=mock_persona,
            retrieved=mock_retrieved,
            config=mock_config,
        )

        assert context.topic is mock_topic
        assert context.persona is mock_persona
        assert context.retrieved is mock_retrieved
        assert context.config is mock_config


class TestContextBuilder:
    """Test ContextBuilder functionality."""

    @pytest.fixture
    def mock_retriever(self) -> AsyncMock:
        """Create mock SpecializedRetriever."""
        retriever = AsyncMock()
        retriever.retrieve.return_value = [
            create_retrieval_result(text="Similar 1", score=0.9),
            create_retrieval_result(text="Similar 2", score=0.85),
        ]
        retriever.retrieve_opinions.return_value = [
            create_retrieval_result(text="Opinion 1", score=0.8, is_opinion=True),
        ]
        retriever.retrieve_examples.return_value = [
            create_retrieval_result(text="Example 1", score=0.75, is_example=True),
        ]
        retriever.retrieve_hooks.return_value = [
            create_retrieval_result(
                text="Hook 1",
                score=0.7,
                performance_score=0.85,
            ),
        ]
        return retriever

    @pytest.fixture
    def mock_db_session_factory(self) -> MagicMock:
        """Create mock DB session factory."""
        factory = MagicMock()
        session = AsyncMock()
        factory.return_value.__aenter__ = AsyncMock(return_value=session)
        factory.return_value.__aexit__ = AsyncMock(return_value=None)
        return factory

    @pytest.fixture
    def context_builder(
        self,
        mock_retriever: AsyncMock,
        mock_db_session_factory: MagicMock,
    ) -> ContextBuilder:
        """Create ContextBuilder with mocks."""
        return ContextBuilder(
            retriever=mock_retriever,
            db_session_factory=mock_db_session_factory,
        )

    @pytest.fixture
    def mock_topic(self) -> MagicMock:
        """Create mock Topic."""
        topic = MagicMock()
        topic.id = uuid.uuid4()
        topic.channel_id = uuid.uuid4()
        topic.title_normalized = "Test Topic"
        topic.summary = "Topic summary"
        topic.keywords = ["python", "programming"]
        return topic

    @pytest.fixture
    def mock_persona(self) -> MagicMock:
        """Create mock Persona."""
        persona = MagicMock()
        persona.id = uuid.uuid4()
        persona.name = "TestPersona"
        persona.tagline = "Learning made fun"
        persona.expertise = ["Python", "Programming"]
        persona.communication_style = {
            "tone": "friendly",
            "formality": "casual",
        }
        return persona

    @pytest.mark.asyncio
    async def test_build_context_basic(
        self,
        context_builder: ContextBuilder,
        mock_topic: MagicMock,
        mock_persona: MagicMock,
    ) -> None:
        """Should build generation context."""
        config = GenerationConfig()
        topic_id = mock_topic.id
        channel_id = mock_topic.channel_id

        # Mock DB query to return topic and persona
        with (
            patch.object(context_builder, "_fetch_topic", return_value=mock_topic),
            patch.object(context_builder, "_fetch_persona", return_value=mock_persona),
        ):
            context = await context_builder.build_context(
                topic_id=topic_id,
                channel_id=channel_id,
                config=config,
            )

        assert isinstance(context, GenerationContext)
        assert context.topic is mock_topic
        assert context.persona is mock_persona
        assert context.config is config

    @pytest.mark.asyncio
    async def test_build_context_retrieves_content(
        self,
        context_builder: ContextBuilder,
        mock_topic: MagicMock,
        mock_persona: MagicMock,
        mock_retriever: AsyncMock,
    ) -> None:
        """Should retrieve all content types."""
        config = GenerationConfig()
        topic_id = mock_topic.id
        channel_id = mock_topic.channel_id

        with (
            patch.object(context_builder, "_fetch_topic", return_value=mock_topic),
            patch.object(context_builder, "_fetch_persona", return_value=mock_persona),
        ):
            context = await context_builder.build_context(
                topic_id=topic_id,
                channel_id=channel_id,
                config=config,
            )

        # Verify retrieval calls
        mock_retriever.retrieve.assert_called_once()
        mock_retriever.retrieve_opinions.assert_called_once()
        mock_retriever.retrieve_examples.assert_called_once()
        mock_retriever.retrieve_hooks.assert_called_once()

        # Verify retrieved content
        assert len(context.retrieved.similar) == 2
        assert len(context.retrieved.opinions) == 1
        assert len(context.retrieved.examples) == 1
        assert len(context.retrieved.hooks) == 1

    @pytest.mark.asyncio
    async def test_build_context_uses_channel_id(
        self,
        context_builder: ContextBuilder,
        mock_topic: MagicMock,
        mock_persona: MagicMock,
        mock_retriever: AsyncMock,
    ) -> None:
        """Should filter by channel_id."""
        config = GenerationConfig()
        channel_id = uuid.uuid4()
        mock_topic.channel_id = channel_id

        with (
            patch.object(context_builder, "_fetch_topic", return_value=mock_topic),
            patch.object(context_builder, "_fetch_persona", return_value=mock_persona),
        ):
            await context_builder.build_context(
                topic_id=mock_topic.id,
                channel_id=channel_id,
                config=config,
            )

        # Check channel_id filter
        call_kwargs = mock_retriever.retrieve.call_args[1]
        assert call_kwargs.get("channel_id") == channel_id

    @pytest.mark.asyncio
    async def test_build_context_parallel_retrieval(
        self,
        context_builder: ContextBuilder,
        mock_topic: MagicMock,
        mock_persona: MagicMock,
        mock_retriever: AsyncMock,
    ) -> None:
        """Should perform retrieval calls (can be parallel)."""
        config = GenerationConfig()

        with (
            patch.object(context_builder, "_fetch_topic", return_value=mock_topic),
            patch.object(context_builder, "_fetch_persona", return_value=mock_persona),
        ):
            await context_builder.build_context(
                topic_id=mock_topic.id,
                channel_id=mock_topic.channel_id,
                config=config,
            )

        # All retrieval methods should be called
        assert mock_retriever.retrieve.call_count == 1
        assert mock_retriever.retrieve_opinions.call_count == 1
        assert mock_retriever.retrieve_examples.call_count == 1
        assert mock_retriever.retrieve_hooks.call_count == 1

    @pytest.mark.asyncio
    async def test_build_context_handles_empty_retrieval(
        self,
        context_builder: ContextBuilder,
        mock_topic: MagicMock,
        mock_persona: MagicMock,
        mock_retriever: AsyncMock,
    ) -> None:
        """Should handle empty retrieval results."""
        config = GenerationConfig()

        # Return empty results
        mock_retriever.retrieve.return_value = []
        mock_retriever.retrieve_opinions.return_value = []
        mock_retriever.retrieve_examples.return_value = []
        mock_retriever.retrieve_hooks.return_value = []

        with (
            patch.object(context_builder, "_fetch_topic", return_value=mock_topic),
            patch.object(context_builder, "_fetch_persona", return_value=mock_persona),
        ):
            context = await context_builder.build_context(
                topic_id=mock_topic.id,
                channel_id=mock_topic.channel_id,
                config=config,
            )

        assert context.retrieved.similar == []
        assert context.retrieved.opinions == []
        assert context.retrieved.examples == []
        assert context.retrieved.hooks == []

    @pytest.mark.asyncio
    async def test_build_context_topic_not_found(
        self,
        context_builder: ContextBuilder,
        mock_persona: MagicMock,
    ) -> None:
        """Should raise error when topic not found."""
        config = GenerationConfig()
        topic_id = uuid.uuid4()
        channel_id = uuid.uuid4()

        with (
            patch.object(context_builder, "_fetch_topic", return_value=None),
            patch.object(context_builder, "_fetch_persona", return_value=mock_persona),
            pytest.raises(ValueError, match="Topic.*not found"),
        ):
            await context_builder.build_context(
                topic_id=topic_id,
                channel_id=channel_id,
                config=config,
            )

    @pytest.mark.asyncio
    async def test_build_context_persona_not_found(
        self,
        context_builder: ContextBuilder,
        mock_topic: MagicMock,
    ) -> None:
        """Should raise error when persona not found."""
        config = GenerationConfig()

        with (
            patch.object(context_builder, "_fetch_topic", return_value=mock_topic),
            patch.object(context_builder, "_fetch_persona", return_value=None),
            pytest.raises(ValueError, match="Persona not found"),
        ):
            await context_builder.build_context(
                topic_id=mock_topic.id,
                channel_id=mock_topic.channel_id,
                config=config,
            )

    def test_build_query_with_title(
        self,
        context_builder: ContextBuilder,
        mock_topic: MagicMock,
    ) -> None:
        """Should build query from topic title."""
        mock_topic.title_normalized = "Python Programming"
        mock_topic.summary = None
        mock_topic.keywords = None

        query = context_builder._build_query(mock_topic)

        assert "Python Programming" in query

    def test_build_query_with_all_fields(
        self,
        context_builder: ContextBuilder,
        mock_topic: MagicMock,
    ) -> None:
        """Should build query from all topic fields."""
        mock_topic.title_normalized = "Python Basics"
        mock_topic.summary = "Introduction to Python"
        mock_topic.keywords = ["python", "programming", "tutorial"]

        query = context_builder._build_query(mock_topic)

        assert "Python Basics" in query
        assert "Introduction to Python" in query
        assert "python" in query
