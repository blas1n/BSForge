"""Unit tests for ScriptChunker."""

import uuid
from unittest.mock import AsyncMock

import pytest

from app.config.rag import ChunkingConfig
from app.models.content_chunk import ChunkPosition, ContentType
from app.services.rag.chunker import ScriptChunker


class TestScriptChunker:
    """Test ScriptChunker functionality."""

    @pytest.fixture
    def config(self) -> ChunkingConfig:
        """Create default chunking config."""
        return ChunkingConfig(
            strategy="structure",
            max_chunk_tokens=200,
            overlap_tokens=20,
            preserve_structure=True,
            use_llm_classification=False,
        )

    @pytest.fixture
    def chunker(self, config: ChunkingConfig) -> ScriptChunker:
        """Create ScriptChunker with default config."""
        return ScriptChunker(config=config)

    @pytest.fixture
    def sample_script(self) -> str:
        """Sample script for testing."""
        return (
            "Have you ever wondered why Python is so popular? "
            "Let me tell you the secret.\n\n"
            "Python was created by Guido van Rossum in the late 1980s. "
            "It was designed to be easy to read and write. "
            "The philosophy behind Python is that code should be readable.\n\n"
            "Many companies use Python today. Google, Netflix, and Instagram "
            "all rely on Python for various services. "
            "For example, Instagram uses Python for their backend services.\n\n"
            "I personally think Python is the best language for beginners. "
            "It's like learning to drive with an automatic car instead of a manual.\n\n"
            "That's why I recommend Python to everyone starting their "
            "programming journey. Try it and you won't regret it!"
        )

    @pytest.mark.asyncio
    async def test_chunk_script_creates_chunks(
        self, chunker: ScriptChunker, sample_script: str
    ) -> None:
        """Should create chunks from script."""
        channel_id = uuid.uuid4()
        script_id = uuid.uuid4()

        chunks = await chunker.chunk_script(
            script_text=sample_script,
            channel_id=channel_id,
            script_id=script_id,
        )

        assert len(chunks) > 0
        assert all(chunk.channel_id == channel_id for chunk in chunks)
        assert all(chunk.script_id == script_id for chunk in chunks)

    @pytest.mark.asyncio
    async def test_chunk_positions(self, chunker: ScriptChunker, sample_script: str) -> None:
        """Should assign correct positions to chunks."""
        channel_id = uuid.uuid4()

        chunks = await chunker.chunk_script(
            script_text=sample_script,
            channel_id=channel_id,
        )

        positions = [chunk.position for chunk in chunks]

        # Should have hook at the beginning
        assert positions[0] == ChunkPosition.HOOK
        # Should have conclusion at the end
        assert positions[-1] == ChunkPosition.CONCLUSION
        # Should have body in the middle
        assert ChunkPosition.BODY in positions

    @pytest.mark.asyncio
    async def test_chunk_content_type(self, chunker: ScriptChunker, sample_script: str) -> None:
        """Should assign correct content type."""
        channel_id = uuid.uuid4()

        chunks = await chunker.chunk_script(
            script_text=sample_script,
            channel_id=channel_id,
            content_type=ContentType.SCRIPT,
        )

        assert all(chunk.content_type == ContentType.SCRIPT for chunk in chunks)

    @pytest.mark.asyncio
    async def test_pattern_based_classification(self, config: ChunkingConfig) -> None:
        """Should classify characteristics using patterns."""
        config.use_llm_classification = False
        chunker = ScriptChunker(config=config)

        # Text with opinion pattern
        opinion_script = "I think Python is the best language. That's my view."
        channel_id = uuid.uuid4()

        chunks = await chunker.chunk_script(
            script_text=opinion_script,
            channel_id=channel_id,
        )

        # At least one chunk should be marked as opinion
        has_opinion = any(chunk.is_opinion for chunk in chunks)
        assert has_opinion

    @pytest.mark.asyncio
    async def test_example_pattern_detection(self, config: ChunkingConfig) -> None:
        """Should detect example patterns."""
        config.use_llm_classification = False
        chunker = ScriptChunker(config=config)

        example_script = (
            "Let me explain with an example. For instance, when you use a list "
            "in Python, you can iterate over it easily."
        )
        channel_id = uuid.uuid4()

        chunks = await chunker.chunk_script(
            script_text=example_script,
            channel_id=channel_id,
        )

        has_example = any(chunk.is_example for chunk in chunks)
        assert has_example

    @pytest.mark.asyncio
    async def test_analogy_pattern_detection(self, config: ChunkingConfig) -> None:
        """Should detect analogy patterns."""
        config.use_llm_classification = False
        chunker = ScriptChunker(config=config)

        analogy_script = (
            "Think of a variable like a box that stores values. "
            "It's similar to a container in your kitchen."
        )
        channel_id = uuid.uuid4()

        chunks = await chunker.chunk_script(
            script_text=analogy_script,
            channel_id=channel_id,
        )

        has_analogy = any(chunk.is_analogy for chunk in chunks)
        assert has_analogy

    @pytest.mark.asyncio
    async def test_korean_pattern_detection(self, config: ChunkingConfig) -> None:
        """Should detect Korean patterns."""
        config.use_llm_classification = False
        chunker = ScriptChunker(config=config)

        korean_script = "제 생각에는 파이썬이 가장 좋은 언어입니다. 개인적으로 추천드립니다."
        channel_id = uuid.uuid4()

        chunks = await chunker.chunk_script(
            script_text=korean_script,
            channel_id=channel_id,
        )

        has_opinion = any(chunk.is_opinion for chunk in chunks)
        assert has_opinion

    @pytest.mark.asyncio
    async def test_llm_classification_enabled(self, config: ChunkingConfig) -> None:
        """Should still create chunks when LLM classification is enabled.

        Note: The current implementation uses synchronous pattern matching
        for backward compatibility. LLM classification is available but
        the code path needs to call the async version.
        """
        config.use_llm_classification = True

        mock_classifier = AsyncMock()
        mock_classifier.classify_characteristics.return_value = {
            "is_opinion": True,
            "is_example": False,
            "is_analogy": False,
        }

        chunker = ScriptChunker(config=config, llm_classifier=mock_classifier)

        script = "Some text that needs classification."
        channel_id = uuid.uuid4()

        chunks = await chunker.chunk_script(
            script_text=script,
            channel_id=channel_id,
        )

        # Should still create chunks even with LLM classification enabled
        assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_llm_fallback_on_error(self, config: ChunkingConfig) -> None:
        """Should fall back to patterns when LLM fails."""
        config.use_llm_classification = True

        mock_classifier = AsyncMock()
        mock_classifier.classify_characteristics.side_effect = Exception("LLM Error")

        chunker = ScriptChunker(config=config, llm_classifier=mock_classifier)

        script = "I think this is a good approach."
        channel_id = uuid.uuid4()

        # Should not raise, should fall back to pattern matching
        chunks = await chunker.chunk_script(
            script_text=script,
            channel_id=channel_id,
        )

        assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_chunk_embedding_model(self, chunker: ScriptChunker, sample_script: str) -> None:
        """Should assign embedding model to chunks."""
        channel_id = uuid.uuid4()

        chunks = await chunker.chunk_script(
            script_text=sample_script,
            channel_id=channel_id,
            embedding_model="BAAI/bge-m3",
        )

        assert all(chunk.embedding_model == "BAAI/bge-m3" for chunk in chunks)

    @pytest.mark.asyncio
    async def test_empty_script(self, chunker: ScriptChunker) -> None:
        """Should handle empty script."""
        channel_id = uuid.uuid4()

        chunks = await chunker.chunk_script(
            script_text="",
            channel_id=channel_id,
        )

        # Should return empty list or minimal chunks
        assert isinstance(chunks, list)

    @pytest.mark.asyncio
    async def test_short_script(self, chunker: ScriptChunker) -> None:
        """Should handle very short script."""
        channel_id = uuid.uuid4()
        short_script = "Hello world!"

        chunks = await chunker.chunk_script(
            script_text=short_script,
            channel_id=channel_id,
        )

        assert len(chunks) >= 1

    @pytest.mark.asyncio
    async def test_fixed_size_strategy(self) -> None:
        """Should chunk by fixed size when strategy is 'fixed'."""
        config = ChunkingConfig(
            strategy="fixed",
            max_chunk_tokens=50,
        )
        chunker = ScriptChunker(config=config)

        long_script = " ".join(["word"] * 200)  # Long script
        channel_id = uuid.uuid4()

        chunks = await chunker.chunk_script(
            script_text=long_script,
            channel_id=channel_id,
        )

        # Should have multiple chunks
        assert len(chunks) > 1

    @pytest.mark.asyncio
    async def test_invalid_strategy_raises_error(self) -> None:
        """Should raise error for invalid strategy."""
        config = ChunkingConfig(strategy="structure")
        # Override with invalid strategy using setattr to bypass type checking
        config.strategy = "invalid"
        chunker = ScriptChunker(config=config)

        with pytest.raises(ValueError, match="Unknown chunking strategy"):
            await chunker.chunk_script(
                script_text="Some text",
                channel_id=uuid.uuid4(),
            )

    def test_sentence_splitting(self, chunker: ScriptChunker) -> None:
        """Should split text into sentences correctly."""
        text = "First sentence. Second sentence! Third sentence? Fourth."
        sentences = chunker._split_sentences(text)

        assert len(sentences) >= 3  # At least 3 sentences
        assert any("First" in s for s in sentences)

    def test_sync_characteristic_extraction(self, chunker: ScriptChunker) -> None:
        """Should extract characteristics synchronously."""
        text = "I think this is a great example of how it works."

        result = chunker._extract_characteristics(text)

        assert "is_opinion" in result
        assert "is_example" in result
        assert "is_analogy" in result
        assert "keywords" in result
        assert isinstance(result["is_opinion"], bool)
