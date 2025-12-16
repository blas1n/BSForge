"""Unit tests for ScriptGenerator."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config.rag import GenerationConfig, QualityCheckConfig
from app.infrastructure.llm import LLMResponse
from app.models.script import Script
from app.services.rag.context import GenerationContext, RetrievedContent
from app.services.rag.generator import QualityCheckFailedError, ScriptGenerator

from .conftest import create_retrieval_result


class TestScriptGenerator:
    """Test ScriptGenerator functionality."""

    @pytest.fixture
    def mock_context_builder(self) -> AsyncMock:
        """Create mock ContextBuilder."""
        builder = AsyncMock()
        return builder

    @pytest.fixture
    def mock_prompt_builder(self) -> AsyncMock:
        """Create mock PromptBuilder."""
        builder = AsyncMock()
        builder.build_prompt.return_value = "Generated prompt content"
        return builder

    @pytest.fixture
    def mock_chunker(self) -> AsyncMock:
        """Create mock ScriptChunker."""
        chunker = AsyncMock()
        chunker.chunk_script.return_value = []
        return chunker

    @pytest.fixture
    def mock_embedder(self) -> AsyncMock:
        """Create mock ContentEmbedder."""
        embedder = AsyncMock()
        embedder.embed_batch.return_value = [[0.1] * 1024]
        return embedder

    @pytest.fixture
    def mock_vector_db(self) -> AsyncMock:
        """Create mock PgVectorDB."""
        db = AsyncMock()
        db.upsert_chunks.return_value = None
        db.model_name = "BAAI/bge-m3"
        return db

    @pytest.fixture
    def mock_llm_client(self) -> AsyncMock:
        """Create mock LLM client."""
        client = AsyncMock()
        script_content = """Have you ever wondered why Python is so popular?

Python was created by Guido van Rossum. It emphasizes code readability.
Many companies use Python today including Google and Netflix.
Python is one of the most popular languages. It has great libraries.
The syntax is clean and easy to learn. Many beginners start with Python.

That's why Python remains one of the most loved languages!"""
        client.complete.return_value = LLMResponse(
            content=script_content,
            model="anthropic/claude-sonnet-4-20250514",
            usage={"prompt_tokens": 100, "completion_tokens": 80, "total_tokens": 180},
        )
        return client

    @pytest.fixture
    def mock_db_session_factory(self) -> MagicMock:
        """Create mock DB session factory."""
        factory = MagicMock()
        session = AsyncMock()
        session.add = MagicMock()
        session.add_all = MagicMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        factory.return_value.__aenter__ = AsyncMock(return_value=session)
        factory.return_value.__aexit__ = AsyncMock(return_value=None)
        return factory

    @pytest.fixture
    def generation_config(self) -> GenerationConfig:
        """Create generation config."""
        return GenerationConfig(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            temperature=0.7,
            format="shorts",
            target_duration=60,
        )

    @pytest.fixture
    def quality_config(self) -> QualityCheckConfig:
        """Create quality check config."""
        return QualityCheckConfig(
            min_style_score=0.5,  # Lower threshold for testing
            min_hook_score=0.3,
            max_forbidden_words=2,
            min_duration=15,  # Minimum allowed value
            max_duration=120,  # Higher for testing
        )

    @pytest.fixture
    def generator(
        self,
        mock_context_builder: AsyncMock,
        mock_prompt_builder: AsyncMock,
        mock_chunker: AsyncMock,
        mock_embedder: AsyncMock,
        mock_vector_db: AsyncMock,
        mock_llm_client: AsyncMock,
        mock_db_session_factory: MagicMock,
        generation_config: GenerationConfig,
        quality_config: QualityCheckConfig,
    ) -> ScriptGenerator:
        """Create ScriptGenerator with mocks."""
        return ScriptGenerator(
            context_builder=mock_context_builder,
            prompt_builder=mock_prompt_builder,
            chunker=mock_chunker,
            embedder=mock_embedder,
            vector_db=mock_vector_db,
            llm_client=mock_llm_client,
            db_session_factory=mock_db_session_factory,
            config=generation_config,
            quality_config=quality_config,
        )

    @pytest.fixture
    def mock_topic(self) -> MagicMock:
        """Create mock Topic."""
        topic = MagicMock()
        topic.id = uuid.uuid4()
        topic.channel_id = uuid.uuid4()
        topic.title_normalized = "Why Python is Popular"
        return topic

    @pytest.fixture
    def mock_persona(self) -> MagicMock:
        """Create mock Persona."""
        persona = MagicMock()
        persona.name = "TechExplainer"
        persona.communication_style = {
            "avoid_words": ["terrible", "hate"],
            "connectors": ["so", "actually"],
            "sentence_endings": ["!", "?"],
        }
        return persona

    @pytest.fixture
    def mock_generation_context(
        self,
        mock_topic: MagicMock,
        mock_persona: MagicMock,
    ) -> GenerationContext:
        """Create mock GenerationContext."""
        return GenerationContext(
            topic=mock_topic,
            persona=mock_persona,
            retrieved=RetrievedContent(
                similar=[create_retrieval_result(text="Similar", score=0.9)],
                opinions=[],
                examples=[],
                hooks=[],
            ),
            config=GenerationConfig(),
        )

    @pytest.mark.asyncio
    async def test_generate_script_basic(
        self,
        generator: ScriptGenerator,
        mock_topic: MagicMock,
        mock_context_builder: AsyncMock,
        mock_generation_context: GenerationContext,
    ) -> None:
        """Should generate script successfully."""
        mock_context_builder.build_context.return_value = mock_generation_context
        topic_id = mock_topic.id
        channel_id = mock_topic.channel_id

        # Mock the internal save method
        with patch.object(generator, "_save_script") as mock_save:
            mock_script = MagicMock(spec=Script)
            mock_script.id = uuid.uuid4()
            mock_script.quality_passed = True
            mock_script.word_count = 50
            mock_save.return_value = mock_script

            script = await generator.generate(topic_id, channel_id)

            assert script is not None
            mock_context_builder.build_context.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_calls_prompt_builder(
        self,
        generator: ScriptGenerator,
        mock_topic: MagicMock,
        mock_context_builder: AsyncMock,
        mock_prompt_builder: AsyncMock,
        mock_generation_context: GenerationContext,
    ) -> None:
        """Should call prompt builder with context."""
        mock_context_builder.build_context.return_value = mock_generation_context
        topic_id = mock_topic.id
        channel_id = mock_topic.channel_id

        with patch.object(generator, "_save_script") as mock_save:
            mock_script = MagicMock(spec=Script)
            mock_script.id = uuid.uuid4()
            mock_script.quality_passed = True
            mock_script.word_count = 50
            mock_save.return_value = mock_script

            await generator.generate(topic_id, channel_id)

            mock_prompt_builder.build_prompt.assert_called_once_with(mock_generation_context)

    @pytest.mark.asyncio
    async def test_generate_calls_llm(
        self,
        generator: ScriptGenerator,
        mock_topic: MagicMock,
        mock_context_builder: AsyncMock,
        mock_llm_client: AsyncMock,
        mock_generation_context: GenerationContext,
    ) -> None:
        """Should call LLM to generate script."""
        mock_context_builder.build_context.return_value = mock_generation_context
        topic_id = mock_topic.id
        channel_id = mock_topic.channel_id

        with patch.object(generator, "_save_script") as mock_save:
            mock_script = MagicMock(spec=Script)
            mock_script.id = uuid.uuid4()
            mock_script.quality_passed = True
            mock_script.word_count = 50
            mock_save.return_value = mock_script

            await generator.generate(topic_id, channel_id)

            mock_llm_client.complete.assert_called_once()

    def test_parse_script_basic(self, generator: ScriptGenerator) -> None:
        """Should parse script into sections."""
        script_text = """Opening hook text here.

Main body content here. More body content. Even more body.

Closing statement here."""

        result = generator._parse_script(script_text)

        assert "hook" in result
        assert "body" in result
        assert "conclusion" in result

    def test_parse_script_short(self, generator: ScriptGenerator) -> None:
        """Should handle short script."""
        script_text = "Just a short script."

        result = generator._parse_script(script_text)

        assert "hook" in result
        assert "body" in result
        assert "conclusion" in result

    def test_estimate_duration(self, generator: ScriptGenerator) -> None:
        """Should estimate duration from word count."""
        script_text = " ".join(["word"] * 150)  # 150 words

        duration = generator._estimate_duration(script_text)

        # At 150 words/minute, should be about 60 seconds
        assert duration == 60

    def test_estimate_duration_empty(self, generator: ScriptGenerator) -> None:
        """Should handle empty script."""
        duration = generator._estimate_duration("")

        assert duration == 0

    def test_calculate_style_score(
        self,
        generator: ScriptGenerator,
        mock_persona: MagicMock,
    ) -> None:
        """Should calculate style score."""
        script_text = "This is a great example of Python programming!"

        score = generator._calculate_style_score(script_text, mock_persona)

        assert 0.0 <= score <= 1.0

    def test_evaluate_hook(self, generator: ScriptGenerator) -> None:
        """Should evaluate hook quality."""
        hook = "Have you ever wondered why Python is so popular?"

        score = generator._evaluate_hook(hook)

        assert 0.0 <= score <= 1.0
        # Questions typically score higher
        assert score > 0.5

    def test_evaluate_hook_with_question(self, generator: ScriptGenerator) -> None:
        """Should give higher score for hooks with questions."""
        question_hook = "Did you know Python can do this?"
        statement_hook = "Python is a programming language."

        question_score = generator._evaluate_hook(question_hook)
        statement_score = generator._evaluate_hook(statement_hook)

        assert question_score > statement_score

    def test_find_forbidden_words(
        self,
        generator: ScriptGenerator,
        mock_persona: MagicMock,
    ) -> None:
        """Should find forbidden words in script."""
        script_text = "This is terrible and I hate it!"

        found = generator._find_forbidden_words(script_text, mock_persona)

        assert "terrible" in found
        assert "hate" in found

    def test_find_forbidden_words_empty(
        self,
        generator: ScriptGenerator,
        mock_persona: MagicMock,
    ) -> None:
        """Should return empty list when no forbidden words."""
        script_text = "This is a great example!"

        found = generator._find_forbidden_words(script_text, mock_persona)

        assert found == []

    def test_find_forbidden_words_no_style(self, generator: ScriptGenerator) -> None:
        """Should handle persona without communication_style."""
        persona = MagicMock()
        persona.communication_style = None
        script_text = "Any text"

        found = generator._find_forbidden_words(script_text, persona)

        assert found == []

    @pytest.mark.asyncio
    async def test_check_quality_passes(
        self,
        generator: ScriptGenerator,
        mock_persona: MagicMock,
    ) -> None:
        """Should pass quality check for good script."""
        # Script with enough words for duration check (at least 38 words for 15s at 150 wpm)
        script_text = " ".join(["word"] * 45) + " This is a great script about Python."

        result = await generator._check_quality(script_text, mock_persona)

        assert result["passed"] is True

    @pytest.mark.asyncio
    async def test_check_quality_fails_forbidden_words(
        self,
        generator: ScriptGenerator,
        mock_persona: MagicMock,
    ) -> None:
        """Should fail quality check for too many forbidden words."""
        generator.quality_config.max_forbidden_words = 0
        # Script with enough words for duration check (at least 38 words for 15s at 150 wpm)
        script_text = " ".join(["word"] * 45) + " This is terrible and I hate everything about it."

        result = await generator._check_quality(script_text, mock_persona)

        assert result["passed"] is False
        assert len(result["forbidden_words"]) > 0

    @pytest.mark.asyncio
    async def test_generate_raises_on_quality_failure(
        self,
        generator: ScriptGenerator,
        mock_topic: MagicMock,
        mock_context_builder: AsyncMock,
        mock_generation_context: GenerationContext,
    ) -> None:
        """Should raise QualityCheckFailedError when quality fails."""
        mock_context_builder.build_context.return_value = mock_generation_context
        topic_id = mock_topic.id
        channel_id = mock_topic.channel_id

        # Force quality check to fail
        with patch.object(generator, "_check_quality") as mock_check:
            mock_check.return_value = {
                "passed": False,
                "reasons": ["Low style score"],
                "duration": 60,
                "style_score": 0.3,
                "hook_score": 0.5,
                "forbidden_words": [],
            }

            with pytest.raises(QualityCheckFailedError):
                await generator.generate(topic_id, channel_id)


class TestQualityCheckFailedError:
    """Test QualityCheckFailedError exception."""

    def test_error_message(self) -> None:
        """Should store error message."""
        error = QualityCheckFailedError("Quality check failed: low score")

        assert "Quality check failed" in str(error)
        assert "low score" in str(error)

    def test_error_inheritance(self) -> None:
        """Should inherit from Exception."""
        error = QualityCheckFailedError("Test")

        assert isinstance(error, Exception)
