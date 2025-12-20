"""Script chunking services.

This module provides structure-based content chunking for scripts,
splitting by hook/body/conclusion sections.
"""

import re
import uuid
from typing import TYPE_CHECKING

from app.config.rag import ChunkingConfig
from app.core.logging import get_logger
from app.models.content_chunk import ChunkPosition, ContentChunk, ContentType

if TYPE_CHECKING:
    from app.services.rag.classifier import ContentClassifier

logger = get_logger(__name__)


class ScriptChunker:
    """Structure-based script chunker.

    Splits scripts into chunks following narrative structure:
    - Hook: First 2-3 sentences (attention grabber)
    - Body: Main content (split if too long)
    - Conclusion: Last 1-2 sentences (wrap-up)

    Supports both pattern-based (fast) and LLM-based (accurate)
    characteristic classification.

    Attributes:
        config: Chunking configuration
        llm_classifier: Optional LLM classifier for accurate classification
    """

    def __init__(
        self,
        config: ChunkingConfig,
        llm_classifier: "ContentClassifier | None" = None,
    ):
        """Initialize ScriptChunker.

        Args:
            config: Chunking configuration
            llm_classifier: Optional LLM classifier
        """
        self.config = config
        self.llm_classifier = llm_classifier

    async def chunk_script(
        self,
        script_text: str,
        channel_id: uuid.UUID,
        script_id: uuid.UUID | None = None,
        content_type: ContentType = ContentType.SCRIPT,
        embedding_model: str = "BAAI/bge-m3",
    ) -> list[ContentChunk]:
        """Chunk script into structural sections.

        Args:
            script_text: Full script text
            channel_id: Channel UUID
            script_id: Script UUID (nullable for non-script content)
            content_type: Type of content
            embedding_model: Embedding model name

        Returns:
            List of ContentChunk objects (not yet persisted to DB)
        """
        logger.info(
            f"Chunking script (strategy={self.config.strategy})",
            extra={"content_type": content_type.value, "length": len(script_text)},
        )

        if self.config.strategy == "structure":
            return await self._chunk_by_structure(
                script_text, channel_id, script_id, content_type, embedding_model
            )
        elif self.config.strategy == "fixed":
            return await self._chunk_by_fixed_size(
                script_text, channel_id, script_id, content_type, embedding_model
            )
        else:
            raise ValueError(f"Unknown chunking strategy: {self.config.strategy}")

    async def _chunk_by_structure(
        self,
        script_text: str,
        channel_id: uuid.UUID,
        script_id: uuid.UUID | None,
        content_type: ContentType,
        embedding_model: str,
    ) -> list[ContentChunk]:
        """Chunk by narrative structure (hook/body/conclusion).

        Args:
            script_text: Full script text
            channel_id: Channel UUID
            script_id: Script UUID
            content_type: Type of content
            embedding_model: Embedding model name

        Returns:
            List of ContentChunk objects
        """
        # Identify sections
        hook, body, conclusion = self._identify_sections(script_text)

        chunks: list[ContentChunk] = []
        chunk_index = 0

        # Create hook chunk
        if hook:
            hook_chars = self._extract_characteristics(hook)
            chunks.append(
                ContentChunk(
                    channel_id=channel_id,
                    script_id=script_id,
                    content_type=content_type,
                    text=hook,
                    chunk_index=chunk_index,
                    position=ChunkPosition.HOOK,
                    context_before=None,
                    context_after=self._summarize_text(body[:200]) if body else None,
                    is_opinion=hook_chars["is_opinion"],
                    is_example=hook_chars["is_example"],
                    is_analogy=hook_chars["is_analogy"],
                    terms=hook_chars["keywords"],
                    embedding=None,  # To be filled by embedder
                    embedding_model=embedding_model,
                )
            )
            chunk_index += 1

        # Split body if needed
        if body:
            body_chunks = self._split_body(body)

            for i, body_text in enumerate(body_chunks):
                body_chars = self._extract_characteristics(body_text)

                # Context summaries
                context_before = None
                if i == 0 and hook:
                    context_before = self._summarize_text(hook)
                elif i > 0:
                    context_before = self._summarize_text(body_chunks[i - 1][:200])

                context_after = None
                if i < len(body_chunks) - 1:
                    context_after = self._summarize_text(body_chunks[i + 1][:200])
                elif conclusion:
                    context_after = self._summarize_text(conclusion)

                chunks.append(
                    ContentChunk(
                        channel_id=channel_id,
                        script_id=script_id,
                        content_type=content_type,
                        text=body_text,
                        chunk_index=chunk_index,
                        position=ChunkPosition.BODY,
                        context_before=context_before,
                        context_after=context_after,
                        is_opinion=body_chars["is_opinion"],
                        is_example=body_chars["is_example"],
                        is_analogy=body_chars["is_analogy"],
                        terms=body_chars["keywords"],
                        embedding=None,
                        embedding_model=embedding_model,
                    )
                )
                chunk_index += 1

        # Create conclusion chunk
        if conclusion:
            conclusion_chars = self._extract_characteristics(conclusion)
            chunks.append(
                ContentChunk(
                    channel_id=channel_id,
                    script_id=script_id,
                    content_type=content_type,
                    text=conclusion,
                    chunk_index=chunk_index,
                    position=ChunkPosition.CONCLUSION,
                    context_before=self._summarize_text(body[-200:]) if body else None,
                    context_after=None,
                    is_opinion=conclusion_chars["is_opinion"],
                    is_example=conclusion_chars["is_example"],
                    is_analogy=conclusion_chars["is_analogy"],
                    terms=conclusion_chars["keywords"],
                    embedding=None,
                    embedding_model=embedding_model,
                )
            )

        logger.info(
            f"Created {len(chunks)} chunks",
            extra={
                "hook_count": sum(1 for c in chunks if c.position == ChunkPosition.HOOK),
                "body_count": sum(1 for c in chunks if c.position == ChunkPosition.BODY),
                "conclusion_count": sum(
                    1 for c in chunks if c.position == ChunkPosition.CONCLUSION
                ),
            },
        )

        return chunks

    async def _chunk_by_fixed_size(
        self,
        script_text: str,
        channel_id: uuid.UUID,
        script_id: uuid.UUID | None,
        content_type: ContentType,
        embedding_model: str,
    ) -> list[ContentChunk]:
        """Chunk by fixed token size with overlap.

        Args:
            script_text: Full script text
            channel_id: Channel UUID
            script_id: Script UUID
            content_type: Type of content
            embedding_model: Embedding model name

        Returns:
            List of ContentChunk objects
        """
        # Simple word-based approximation (1 token ≈ 0.75 words)
        words = script_text.split()
        max_words = int(self.config.max_chunk_tokens * 0.75)
        overlap_words = int(self.config.overlap_tokens * 0.75)

        chunks: list[ContentChunk] = []
        chunk_index = 0
        start = 0

        while start < len(words):
            end = min(start + max_words, len(words))
            chunk_words = words[start:end]
            chunk_text = " ".join(chunk_words)

            chars = self._extract_characteristics(chunk_text)

            # Determine position based on location
            if start == 0:
                position = ChunkPosition.HOOK
            elif end >= len(words):
                position = ChunkPosition.CONCLUSION
            else:
                position = ChunkPosition.BODY

            chunks.append(
                ContentChunk(
                    channel_id=channel_id,
                    script_id=script_id,
                    content_type=content_type,
                    text=chunk_text,
                    chunk_index=chunk_index,
                    position=position,
                    context_before=None,
                    context_after=None,
                    is_opinion=chars["is_opinion"],
                    is_example=chars["is_example"],
                    is_analogy=chars["is_analogy"],
                    terms=chars["keywords"],
                    embedding=None,
                    embedding_model=embedding_model,
                )
            )

            chunk_index += 1
            start = end - overlap_words if end < len(words) else end

        return chunks

    def _identify_sections(self, script_text: str) -> tuple[str, str, str]:
        """Identify hook, body, and conclusion sections.

        Heuristic:
        - Hook: First 2-3 sentences or first paragraph
        - Conclusion: Last 1-2 sentences or last paragraph
        - Body: Everything in between

        Args:
            script_text: Full script text

        Returns:
            Tuple of (hook, body, conclusion)
        """
        # Split into sentences
        sentences = self._split_sentences(script_text)

        if len(sentences) <= 3:
            # Short script: hook + conclusion only
            return (
                sentences[0] if sentences else "",
                "",
                sentences[-1] if len(sentences) > 1 else "",
            )

        # Hook: First 2-3 sentences (up to ~15% of total)
        hook_count = min(3, max(1, len(sentences) // 7))
        hook = " ".join(sentences[:hook_count])

        # Conclusion: Last 1-2 sentences (up to ~10% of total)
        conclusion_count = min(2, max(1, len(sentences) // 10))
        conclusion = " ".join(sentences[-conclusion_count:])

        # Body: Everything in between
        body = " ".join(sentences[hook_count:-conclusion_count])

        return hook, body, conclusion

    def _split_body(self, body_text: str) -> list[str]:
        """Split body into chunks if too long.

        Preserves paragraph and sentence boundaries.

        Args:
            body_text: Body section text

        Returns:
            List of body chunks
        """
        # Estimate tokens (1 token ≈ 0.75 words)
        words = body_text.split()
        max_words = int(self.config.max_chunk_tokens * 0.75)

        if len(words) <= max_words:
            return [body_text]

        # Split by paragraphs
        paragraphs = body_text.split("\n\n")
        chunks: list[str] = []
        current_chunk: list[str] = []
        current_words = 0

        for para in paragraphs:
            para_words = len(para.split())

            if current_words + para_words > max_words and current_chunk:
                # Save current chunk
                chunks.append("\n\n".join(current_chunk))
                current_chunk = []
                current_words = 0

            current_chunk.append(para)
            current_words += para_words

        # Add remaining
        if current_chunk:
            chunks.append("\n\n".join(current_chunk))

        return chunks

    def _split_sentences(self, text: str) -> list[str]:
        """Split text into sentences.

        Args:
            text: Input text

        Returns:
            List of sentences
        """
        # Simple sentence splitting (handles Korean and English)
        # Split by period, question mark, exclamation mark
        sentences = re.split(r"[.!?]+\s+", text.strip())
        return [s.strip() for s in sentences if s.strip()]

    async def _extract_characteristics_async(self, text: str) -> dict[str, bool | list[str]]:
        """Extract chunk characteristics using pattern matching or LLM.

        Uses pattern matching by default (fast). If use_llm_classification
        is enabled and LLM classifier is available, uses LLM for more
        accurate classification.

        Args:
            text: Chunk text

        Returns:
            Dict with is_opinion, is_example, is_analogy, keywords
        """
        text_lower = text.lower()

        # Pattern-based classification (fast, always runs)
        is_opinion = any(
            re.search(pattern, text_lower, re.IGNORECASE)
            for pattern in self.config.opinion_patterns
        )
        is_example = any(
            re.search(pattern, text_lower, re.IGNORECASE)
            for pattern in self.config.example_patterns
        )
        is_analogy = any(
            re.search(pattern, text_lower, re.IGNORECASE)
            for pattern in self.config.analogy_patterns
        )

        # LLM-based classification (accurate, optional)
        if self.config.use_llm_classification and self.llm_classifier:
            try:
                llm_result = await self.llm_classifier.classify_characteristics(text)
                # Override with LLM results
                is_opinion = llm_result["is_opinion"]
                is_example = llm_result["is_example"]
                is_analogy = llm_result["is_analogy"]
                logger.debug("Using LLM classification results")
            except Exception as e:
                logger.warning(f"LLM classification failed, using pattern-based results: {e}")

        # Extract keywords
        keywords = self._extract_keywords(text)

        return {
            "is_opinion": is_opinion,
            "is_example": is_example,
            "is_analogy": is_analogy,
            "keywords": keywords,
        }

    def _extract_characteristics(self, text: str) -> dict[str, bool | list[str]]:
        """Synchronous wrapper for characteristic extraction.

        For backward compatibility. Uses pattern matching only.

        Args:
            text: Chunk text

        Returns:
            Dict with is_opinion, is_example, is_analogy, keywords
        """
        text_lower = text.lower()

        # Pattern-based classification only (sync)
        is_opinion = any(
            re.search(pattern, text_lower, re.IGNORECASE)
            for pattern in self.config.opinion_patterns
        )
        is_example = any(
            re.search(pattern, text_lower, re.IGNORECASE)
            for pattern in self.config.example_patterns
        )
        is_analogy = any(
            re.search(pattern, text_lower, re.IGNORECASE)
            for pattern in self.config.analogy_patterns
        )

        keywords = self._extract_keywords(text)

        return {
            "is_opinion": is_opinion,
            "is_example": is_example,
            "is_analogy": is_analogy,
            "keywords": keywords,
        }

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract keywords from text.

        Simple implementation: capitalize words (likely proper nouns/important terms).
        For production, use NLP POS tagging.

        Args:
            text: Input text

        Returns:
            List of keywords
        """
        words = text.split()
        # Find capitalized words (excluding sentence starts)
        keywords = []
        for i, word in enumerate(words):
            # Remove punctuation
            clean_word = re.sub(r"[^\w가-힣]", "", word)
            if not clean_word:
                continue

            # Check if capitalized (English) or meaningful length (Korean)
            if clean_word[0].isupper() and i > 0:
                keywords.append(clean_word)
            elif len(clean_word) >= 3 and any("\u3131" <= c <= "\ud7a3" for c in clean_word):
                # Korean word with 3+ characters
                keywords.append(clean_word)

        # Deduplicate and limit
        unique_keywords = list(dict.fromkeys(keywords))[:10]
        return unique_keywords

    def _summarize_text(self, text: str, max_length: int = 100) -> str:
        """Create a short summary of text.

        For now, just truncate. In production, use extractive summarization.

        Args:
            text: Input text
            max_length: Maximum summary length

        Returns:
            Summary text
        """
        if len(text) <= max_length:
            return text

        # Truncate at sentence boundary
        truncated = text[:max_length]
        last_period = max(
            truncated.rfind("."),
            truncated.rfind("!"),
            truncated.rfind("?"),
        )

        if last_period > max_length // 2:
            return truncated[: last_period + 1]

        return truncated + "..."


__all__ = ["ScriptChunker"]
