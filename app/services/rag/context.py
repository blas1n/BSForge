"""RAG context building services.

This module provides context building for script generation by gathering
persona, retrieved content, and topic information.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.rag import GenerationConfig
from app.core.logging import get_logger
from app.core.types import SessionFactory
from app.models.channel import Persona
from app.models.topic import Topic
from app.services.rag.retriever import RetrievalResult, SpecializedRetriever

logger = get_logger(__name__)


@dataclass
class RetrievedContent:
    """Retrieved content for generation context.

    Attributes:
        similar: Similar content chunks (general retrieval)
        opinions: Opinion chunks related to topic
        examples: Example chunks related to topic
        hooks: High-quality hook chunks
    """

    similar: list[RetrievalResult]
    opinions: list[RetrievalResult]
    examples: list[RetrievalResult]
    hooks: list[RetrievalResult]


@dataclass
class GenerationContext:
    """Complete context for script generation.

    Attributes:
        topic: Topic information
        persona: Channel persona
        retrieved: Retrieved content
        config: Generation configuration
    """

    topic: Topic
    persona: Persona
    retrieved: RetrievedContent
    config: GenerationConfig


class ContextBuilder:
    """Build generation context from topic and retrieved chunks.

    Orchestrates parallel retrieval of:
    - Similar content (general)
    - Opinions
    - Examples
    - High-quality hooks

    Attributes:
        retriever: SpecializedRetriever instance
        db_session_factory: AsyncSession factory
    """

    def __init__(
        self,
        retriever: SpecializedRetriever,
        db_session_factory: SessionFactory,
    ):
        """Initialize ContextBuilder.

        Args:
            retriever: SpecializedRetriever instance
            db_session_factory: SQLAlchemy async session factory
        """
        self.retriever = retriever
        self.db_session_factory = db_session_factory

    async def build_context(
        self,
        topic_id: uuid.UUID,
        channel_id: uuid.UUID,
        config: GenerationConfig,
    ) -> GenerationContext:
        """Build complete generation context.

        Args:
            topic_id: Topic UUID
            channel_id: Channel UUID
            config: Generation configuration

        Returns:
            GenerationContext with topic, persona, and retrieved content

        Raises:
            ValueError: If topic or persona not found
        """
        logger.info(f"Building context for topic {topic_id}")

        async with self.db_session_factory() as session:
            # Fetch topic
            topic = await self._fetch_topic(session, topic_id, channel_id)
            if not topic:
                raise ValueError(f"Topic {topic_id} not found for channel {channel_id}")

            # Fetch persona
            persona = await self._fetch_persona(session, channel_id)
            if not persona:
                raise ValueError(f"Persona not found for channel {channel_id}")

        # Build query from topic
        query = self._build_query(topic)

        # Parallel retrieval
        logger.info("Retrieving content in parallel")

        # NOTE: For true parallelism, use asyncio.gather
        # For now, sequential is fine
        similar = await self.retriever.retrieve(
            query=query,
            channel_id=channel_id,
            top_k=5,
        )

        opinions = await self.retriever.retrieve_opinions(
            topic=query,
            channel_id=channel_id,
            top_k=3,
        )

        examples = await self.retriever.retrieve_examples(
            topic=query,
            channel_id=channel_id,
            top_k=3,
        )

        hooks = await self.retriever.retrieve_hooks(
            topic=query,
            channel_id=channel_id,
            top_k=3,
            min_performance=0.5,
        )

        retrieved = RetrievedContent(
            similar=similar,
            opinions=opinions,
            examples=examples,
            hooks=hooks,
        )

        context = GenerationContext(
            topic=topic,
            persona=persona,
            retrieved=retrieved,
            config=config,
        )

        logger.info(
            "Context built successfully",
            extra={
                "topic_id": str(topic_id),
                "similar_count": len(similar),
                "opinions_count": len(opinions),
                "examples_count": len(examples),
                "hooks_count": len(hooks),
            },
        )

        return context

    async def _fetch_topic(
        self,
        session: AsyncSession,
        topic_id: uuid.UUID,
        channel_id: uuid.UUID,
    ) -> Topic | None:
        """Fetch topic from database.

        Args:
            session: Database session
            topic_id: Topic UUID
            channel_id: Channel UUID

        Returns:
            Topic object or None
        """
        result = await session.execute(
            select(Topic).where(
                Topic.id == topic_id,
                Topic.channel_id == channel_id,
            )
        )
        topic: Topic | None = result.scalar_one_or_none()
        return topic

    async def _fetch_persona(
        self,
        session: AsyncSession,
        channel_id: uuid.UUID,
    ) -> Persona | None:
        """Fetch persona from database.

        Args:
            session: Database session
            channel_id: Channel UUID

        Returns:
            Persona object or None
        """
        result = await session.execute(select(Persona).where(Persona.channel_id == channel_id))
        persona: Persona | None = result.scalar_one_or_none()
        return persona

    def _build_query(self, topic: Topic) -> str:
        """Build search query from topic.

        Combines title, summary, and keywords for comprehensive search.

        Args:
            topic: Topic object

        Returns:
            Search query string
        """
        parts = []

        if topic.title_normalized:
            parts.append(topic.title_normalized)

        if topic.summary:
            parts.append(topic.summary)

        if topic.keywords:
            parts.append(" ".join(topic.keywords[:5]))

        query = " ".join(parts)
        logger.debug(f"Built query: {query[:100]}...")
        return query


__all__ = [
    "RetrievedContent",
    "GenerationContext",
    "ContextBuilder",
]
