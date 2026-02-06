"""RAG Facade for simplified dependency management.

This module provides a facade that groups related RAG dependencies together,
reducing the number of constructor parameters needed by services.

The facade is a simple data container that holds references to pre-configured
RAG components. Use the DI container to create instances.

Example:
    # Get from container (recommended)
    facade = container.services.rag_facade()

    # Access components
    facade.retriever.retrieve(...)
    facade.embedder.embed(...)
    facade.chunker.chunk_script(...)
"""

from dataclasses import dataclass

from app.infrastructure.llm import LLMClient
from app.prompts.manager import PromptManager
from app.services.rag.chunker import ScriptChunker
from app.services.rag.context import ContextBuilder
from app.services.rag.embedder import ContentEmbedder
from app.services.rag.prompt import PromptBuilder
from app.services.rag.quality import ScriptQualityChecker
from app.services.rag.retriever import SpecializedRetriever


@dataclass
class RAGFacade:
    """Facade for RAG-related services.

    Groups together the retrieval, embedding, and generation components
    used throughout the RAG pipeline. This is a data container - use
    the DI container to create properly configured instances.

    Attributes:
        retriever: Specialized retriever for hybrid search
        embedder: Content embedder for vector operations
        context_builder: Context builder for assembling prompts
        prompt_builder: Prompt builder for template rendering
        chunker: Script chunker for splitting content
        quality_checker: Quality checker for script validation
        llm_client: LLM client for generation
        prompt_manager: Prompt template manager
    """

    retriever: SpecializedRetriever
    embedder: ContentEmbedder
    context_builder: ContextBuilder
    prompt_builder: PromptBuilder
    chunker: ScriptChunker
    quality_checker: ScriptQualityChecker
    llm_client: LLMClient
    prompt_manager: PromptManager
