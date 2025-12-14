"""RAG (Retrieval-Augmented Generation) services.

This package provides services for:
- Content embedding (BGE-M3)
- Hybrid retrieval (semantic + keyword)
- Reranking and MMR
- Script chunking with configurable patterns
- LLM-based content classification
- Context building
- Prompt construction
- Script generation with quality checks
"""

from app.services.rag.chunker import ScriptChunker
from app.services.rag.classifier import ContentClassifier
from app.services.rag.context import ContextBuilder
from app.services.rag.embedder import ContentEmbedder
from app.services.rag.generator import ScriptGenerator
from app.services.rag.prompt import PromptBuilder
from app.services.rag.reranker import RAGReranker
from app.services.rag.retriever import RAGRetriever, SpecializedRetriever

__all__ = [
    "ContentEmbedder",
    "RAGRetriever",
    "SpecializedRetriever",
    "RAGReranker",
    "ScriptChunker",
    "ContentClassifier",
    "ContextBuilder",
    "PromptBuilder",
    "ScriptGenerator",
]
