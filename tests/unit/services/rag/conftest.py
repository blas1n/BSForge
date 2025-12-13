"""Pytest fixtures for RAG service tests."""

import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.models.content_chunk import ChunkPosition, ContentChunk


def create_mock_chunk(
    text: str = "Sample text",
    position: ChunkPosition = ChunkPosition.BODY,
    is_opinion: bool = False,
    is_example: bool = False,
    is_analogy: bool = False,
    performance_score: float | None = None,
) -> MagicMock:
    """Create a mock ContentChunk for testing.

    Args:
        text: Chunk text content
        position: Chunk position
        is_opinion: Opinion flag
        is_example: Example flag
        is_analogy: Analogy flag
        performance_score: Optional performance score

    Returns:
        Mock ContentChunk object
    """
    chunk = MagicMock(spec=ContentChunk)
    chunk.id = uuid.uuid4()
    chunk.text = text
    chunk.position = position
    chunk.is_opinion = is_opinion
    chunk.is_example = is_example
    chunk.is_analogy = is_analogy
    chunk.performance_score = performance_score
    return chunk


def create_retrieval_result(
    chunk_id: uuid.UUID | None = None,
    text: str = "Sample text",
    score: float = 0.9,
    position: ChunkPosition = ChunkPosition.BODY,
    is_opinion: bool = False,
    is_example: bool = False,
    is_analogy: bool = False,
    performance_score: float | None = None,
    embedding: list[float] | None = None,
) -> Any:
    """Create a mock RetrievalResult for testing.

    Since RetrievalResult requires a chunk object for properties,
    we create a mock that directly has the properties we need.

    Args:
        chunk_id: Optional chunk ID (generated if not provided)
        text: Chunk text content
        score: Similarity score
        position: Chunk position
        is_opinion: Opinion flag
        is_example: Example flag
        is_analogy: Analogy flag
        performance_score: Optional performance score
        embedding: Optional embedding vector

    Returns:
        Mock object with RetrievalResult-like interface
    """
    result = MagicMock()
    result.chunk_id = chunk_id or uuid.uuid4()
    result.text = text
    result.score = score
    result.position = position
    result.is_opinion = is_opinion
    result.is_example = is_example
    result.is_analogy = is_analogy
    result.performance_score = performance_score
    result.embedding = embedding
    return result


@pytest.fixture
def mock_chunk_factory():
    """Factory fixture for creating mock chunks."""
    return create_mock_chunk


@pytest.fixture
def retrieval_result_factory():
    """Factory fixture for creating mock retrieval results."""
    return create_retrieval_result
