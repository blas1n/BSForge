"""Unit tests for VectorDB protocol interface."""

from datetime import datetime
from typing import Any

import pytest

from app.core.vectordb import VectorDB


class MockVectorDB:
    """Mock implementation of VectorDB protocol for testing."""

    def __init__(self):
        self.storage: dict[str, dict[str, Any]] = {}
        self.embed_calls: list[str] = []
        self.embed_batch_calls: list[list[str]] = []

    async def embed(self, text: str) -> list[float]:
        """Generate mock embedding."""
        self.embed_calls.append(text)
        # Simple mock: hash-based embedding
        return [float(hash(text) % 100) / 100 for _ in range(3)]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate mock embeddings for batch."""
        self.embed_batch_calls.append(texts)
        return [await self.embed(text) for text in texts]

    async def query(
        self,
        vector: list[float],
        top_k: int = 5,
        filter_after: datetime | None = None,
        namespace: str | None = None,
    ) -> list[tuple[str, float]]:
        """Query mock storage."""
        results = []
        ns_prefix = f"{namespace}:" if namespace else ""

        for doc_id, data in self.storage.items():
            if namespace and not doc_id.startswith(ns_prefix):
                continue

            # Simple similarity: inverse of vector distance
            stored_vector = data["vector"]
            distance = sum((a - b) ** 2 for a, b in zip(vector, stored_vector, strict=True)) ** 0.5
            similarity = 1 / (1 + distance)

            # Apply filter
            if filter_after and data.get("metadata", {}).get("indexed_at"):
                indexed_at = data["metadata"]["indexed_at"]
                if indexed_at < filter_after:
                    continue

            results.append((doc_id, similarity))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    async def upsert(
        self,
        doc_id: str,
        vector: list[float],
        metadata: dict[str, Any] | None = None,
        namespace: str | None = None,
    ) -> None:
        """Upsert to mock storage."""
        key = f"{namespace}:{doc_id}" if namespace else doc_id
        self.storage[key] = {"vector": vector, "metadata": metadata or {}}

    async def upsert_batch(
        self,
        items: list[tuple[str, list[float], dict[str, Any] | None]],
        namespace: str | None = None,
    ) -> None:
        """Upsert batch to mock storage."""
        for doc_id, vector, metadata in items:
            await self.upsert(doc_id, vector, metadata, namespace)

    async def delete(
        self,
        doc_ids: list[str],
        namespace: str | None = None,
    ) -> None:
        """Delete from mock storage."""
        for doc_id in doc_ids:
            key = f"{namespace}:{doc_id}" if namespace else doc_id
            self.storage.pop(key, None)


class TestVectorDBProtocol:
    """Tests for VectorDB protocol interface."""

    def test_protocol_is_runtime_checkable(self):
        """Test that VectorDB is a runtime checkable protocol."""
        mock_db = MockVectorDB()
        assert isinstance(mock_db, VectorDB)

    def test_incomplete_implementation_not_instance(self):
        """Test that incomplete implementation is not an instance."""

        class IncompleteDB:
            async def embed(self, text: str) -> list[float]:
                return []

        incomplete = IncompleteDB()
        assert not isinstance(incomplete, VectorDB)


class TestMockVectorDBEmbed:
    """Tests for VectorDB embed operation."""

    @pytest.fixture
    def vector_db(self):
        return MockVectorDB()

    @pytest.mark.asyncio
    async def test_embed_returns_list_of_floats(self, vector_db):
        """Test that embed returns a list of floats."""
        result = await vector_db.embed("hello world")

        assert isinstance(result, list)
        assert all(isinstance(x, float) for x in result)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_embed_tracks_calls(self, vector_db):
        """Test that embed calls are tracked."""
        await vector_db.embed("text1")
        await vector_db.embed("text2")

        assert vector_db.embed_calls == ["text1", "text2"]

    @pytest.mark.asyncio
    async def test_embed_same_text_returns_same_vector(self, vector_db):
        """Test that same text returns consistent embeddings."""
        result1 = await vector_db.embed("test text")
        result2 = await vector_db.embed("test text")

        assert result1 == result2

    @pytest.mark.asyncio
    async def test_embed_different_text_returns_different_vector(self, vector_db):
        """Test that different texts return different embeddings."""
        result1 = await vector_db.embed("text one")
        result2 = await vector_db.embed("text two")

        assert result1 != result2


class TestMockVectorDBEmbedBatch:
    """Tests for VectorDB embed_batch operation."""

    @pytest.fixture
    def vector_db(self):
        return MockVectorDB()

    @pytest.mark.asyncio
    async def test_embed_batch_returns_list_of_vectors(self, vector_db):
        """Test that embed_batch returns multiple vectors."""
        texts = ["text1", "text2", "text3"]
        results = await vector_db.embed_batch(texts)

        assert isinstance(results, list)
        assert len(results) == 3
        assert all(isinstance(v, list) for v in results)

    @pytest.mark.asyncio
    async def test_embed_batch_tracks_calls(self, vector_db):
        """Test that batch calls are tracked."""
        texts = ["a", "b"]
        await vector_db.embed_batch(texts)

        assert vector_db.embed_batch_calls == [["a", "b"]]

    @pytest.mark.asyncio
    async def test_embed_batch_empty_list(self, vector_db):
        """Test embed_batch with empty list."""
        results = await vector_db.embed_batch([])

        assert results == []


class TestMockVectorDBUpsertAndQuery:
    """Tests for VectorDB upsert and query operations."""

    @pytest.fixture
    def vector_db(self):
        return MockVectorDB()

    @pytest.mark.asyncio
    async def test_upsert_stores_vector(self, vector_db):
        """Test that upsert stores vector correctly."""
        await vector_db.upsert("doc1", [0.1, 0.2, 0.3])

        assert "doc1" in vector_db.storage
        assert vector_db.storage["doc1"]["vector"] == [0.1, 0.2, 0.3]

    @pytest.mark.asyncio
    async def test_upsert_with_metadata(self, vector_db):
        """Test that upsert stores metadata."""
        metadata = {"title": "Test Doc", "source": "test"}
        await vector_db.upsert("doc1", [0.1, 0.2], metadata=metadata)

        assert vector_db.storage["doc1"]["metadata"] == metadata

    @pytest.mark.asyncio
    async def test_upsert_with_namespace(self, vector_db):
        """Test that upsert uses namespace prefix."""
        await vector_db.upsert("doc1", [0.1, 0.2], namespace="channel1")

        assert "channel1:doc1" in vector_db.storage

    @pytest.mark.asyncio
    async def test_upsert_updates_existing(self, vector_db):
        """Test that upsert updates existing document."""
        await vector_db.upsert("doc1", [0.1, 0.2])
        await vector_db.upsert("doc1", [0.3, 0.4])

        assert vector_db.storage["doc1"]["vector"] == [0.3, 0.4]

    @pytest.mark.asyncio
    async def test_query_returns_similar_vectors(self, vector_db):
        """Test that query returns similar vectors."""
        await vector_db.upsert("doc1", [0.1, 0.2, 0.3])
        await vector_db.upsert("doc2", [0.1, 0.2, 0.35])
        await vector_db.upsert("doc3", [0.9, 0.8, 0.7])

        results = await vector_db.query([0.1, 0.2, 0.3], top_k=2)

        assert len(results) == 2
        # doc1 should be most similar (exact match)
        assert results[0][0] == "doc1"
        assert results[0][1] > results[1][1]  # Higher similarity

    @pytest.mark.asyncio
    async def test_query_respects_top_k(self, vector_db):
        """Test that query respects top_k limit."""
        for i in range(10):
            await vector_db.upsert(f"doc{i}", [float(i) / 10, 0.5, 0.5])

        results = await vector_db.query([0.5, 0.5, 0.5], top_k=3)

        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_query_with_namespace_filters(self, vector_db):
        """Test that query filters by namespace."""
        await vector_db.upsert("doc1", [0.1, 0.2, 0.3], namespace="ns1")
        await vector_db.upsert("doc2", [0.1, 0.2, 0.3], namespace="ns2")

        results = await vector_db.query([0.1, 0.2, 0.3], namespace="ns1")

        assert len(results) == 1
        assert results[0][0] == "ns1:doc1"

    @pytest.mark.asyncio
    async def test_query_empty_storage(self, vector_db):
        """Test query on empty storage."""
        results = await vector_db.query([0.1, 0.2, 0.3])

        assert results == []


class TestMockVectorDBUpsertBatch:
    """Tests for VectorDB upsert_batch operation."""

    @pytest.fixture
    def vector_db(self):
        return MockVectorDB()

    @pytest.mark.asyncio
    async def test_upsert_batch_stores_multiple(self, vector_db):
        """Test that upsert_batch stores multiple vectors."""
        items = [
            ("doc1", [0.1, 0.2], {"title": "Doc 1"}),
            ("doc2", [0.3, 0.4], {"title": "Doc 2"}),
            ("doc3", [0.5, 0.6], None),
        ]

        await vector_db.upsert_batch(items)

        assert len(vector_db.storage) == 3
        assert vector_db.storage["doc1"]["vector"] == [0.1, 0.2]
        assert vector_db.storage["doc2"]["metadata"]["title"] == "Doc 2"

    @pytest.mark.asyncio
    async def test_upsert_batch_with_namespace(self, vector_db):
        """Test upsert_batch with namespace."""
        items = [
            ("doc1", [0.1], None),
            ("doc2", [0.2], None),
        ]

        await vector_db.upsert_batch(items, namespace="test")

        assert "test:doc1" in vector_db.storage
        assert "test:doc2" in vector_db.storage

    @pytest.mark.asyncio
    async def test_upsert_batch_empty_list(self, vector_db):
        """Test upsert_batch with empty list."""
        await vector_db.upsert_batch([])

        assert len(vector_db.storage) == 0


class TestMockVectorDBDelete:
    """Tests for VectorDB delete operation."""

    @pytest.fixture
    def vector_db(self):
        return MockVectorDB()

    @pytest.mark.asyncio
    async def test_delete_removes_vectors(self, vector_db):
        """Test that delete removes vectors."""
        await vector_db.upsert("doc1", [0.1, 0.2])
        await vector_db.upsert("doc2", [0.3, 0.4])

        await vector_db.delete(["doc1"])

        assert "doc1" not in vector_db.storage
        assert "doc2" in vector_db.storage

    @pytest.mark.asyncio
    async def test_delete_multiple(self, vector_db):
        """Test deleting multiple vectors."""
        await vector_db.upsert("doc1", [0.1])
        await vector_db.upsert("doc2", [0.2])
        await vector_db.upsert("doc3", [0.3])

        await vector_db.delete(["doc1", "doc3"])

        assert len(vector_db.storage) == 1
        assert "doc2" in vector_db.storage

    @pytest.mark.asyncio
    async def test_delete_with_namespace(self, vector_db):
        """Test delete with namespace prefix."""
        await vector_db.upsert("doc1", [0.1], namespace="ns1")
        await vector_db.upsert("doc1", [0.2], namespace="ns2")

        await vector_db.delete(["doc1"], namespace="ns1")

        assert "ns1:doc1" not in vector_db.storage
        assert "ns2:doc1" in vector_db.storage

    @pytest.mark.asyncio
    async def test_delete_nonexistent_key(self, vector_db):
        """Test deleting non-existent key doesn't raise."""
        await vector_db.upsert("doc1", [0.1])

        # Should not raise
        await vector_db.delete(["nonexistent"])

        assert "doc1" in vector_db.storage

    @pytest.mark.asyncio
    async def test_delete_empty_list(self, vector_db):
        """Test delete with empty list."""
        await vector_db.upsert("doc1", [0.1])

        await vector_db.delete([])

        assert "doc1" in vector_db.storage
