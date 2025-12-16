"""RAG script generation service.

This module provides the main ScriptGenerator that orchestrates the complete
RAG pipeline from topic to generated script with quality checks.

Uses scene-based scripts (generate_scene_script method) - BSForge differentiator.
"""

import json
import re
import uuid
from typing import Any

from app.config.rag import GenerationConfig, QualityCheckConfig
from app.core.config import settings
from app.core.logging import get_logger
from app.infrastructure.llm import LLMClient, LLMConfig, get_llm_client
from app.infrastructure.pgvector_db import PgVectorDB
from app.models.content_chunk import ContentType
from app.models.scene import Scene, SceneScript, SceneType, VisualHintType
from app.models.script import Script, ScriptStatus
from app.services.rag.chunker import ScriptChunker
from app.services.rag.context import ContextBuilder
from app.services.rag.embedder import ContentEmbedder
from app.services.rag.prompt import PromptBuilder

logger = get_logger(__name__)


class ScriptGenerationError(Exception):
    """Script generation failed."""

    pass


class QualityCheckFailedError(ScriptGenerationError):
    """Quality checks failed."""

    pass


class ScriptGenerator:
    """Orchestrate end-to-end script generation with quality checks.

    Pipeline:
    1. Build context (topic + persona + retrieved content)
    2. Build prompt
    3. Generate script via LLM
    4. Post-process (parse, quality check)
    5. Save to database
    6. Chunk and embed for future retrieval

    Attributes:
        context_builder: ContextBuilder instance
        prompt_builder: PromptBuilder instance
        chunker: ScriptChunker instance
        embedder: ContentEmbedder instance
        vector_db: PgVectorDB instance
        llm_client: LLMClient for unified LLM access
        db_session_factory: AsyncSession factory
        config: Generation configuration
        quality_config: Quality check configuration
    """

    def __init__(
        self,
        context_builder: ContextBuilder,
        prompt_builder: PromptBuilder,
        chunker: ScriptChunker,
        embedder: ContentEmbedder,
        vector_db: PgVectorDB,
        llm_client: LLMClient | None = None,
        db_session_factory: Any = None,
        config: GenerationConfig | None = None,
        quality_config: QualityCheckConfig | None = None,
    ):
        """Initialize ScriptGenerator.

        Args:
            context_builder: ContextBuilder instance
            prompt_builder: PromptBuilder instance
            chunker: ScriptChunker instance
            embedder: ContentEmbedder instance
            vector_db: PgVectorDB instance
            llm_client: LLMClient instance (default: singleton)
            db_session_factory: SQLAlchemy async session factory
            config: Generation configuration (default: from settings)
            quality_config: Quality check configuration
        """
        self.context_builder = context_builder
        self.prompt_builder = prompt_builder
        self.chunker = chunker
        self.embedder = embedder
        self.vector_db = vector_db
        self.llm_client = llm_client or get_llm_client()
        self.db_session_factory = db_session_factory
        self.config = config or GenerationConfig()
        self.quality_config = quality_config or QualityCheckConfig()

    def _get_model_name(self, config: GenerationConfig) -> str:
        """Get LiteLLM-format model name.

        Args:
            config: Generation config

        Returns:
            Model name in LiteLLM format (provider/model)
        """
        model = config.model
        # If already in LiteLLM format, return as-is
        if model.startswith(("anthropic/", "openai/", "gemini/")):
            return model
        # Otherwise, use settings default
        return settings.llm_model_heavy

    async def generate(
        self,
        topic_id: uuid.UUID,
        channel_id: uuid.UUID,
        config: GenerationConfig | None = None,
    ) -> Script:
        """Generate script from topic.

        Args:
            topic_id: Topic UUID
            channel_id: Channel UUID
            config: Optional generation config (default: from self.config)

        Returns:
            Script object (saved to database)

        Raises:
            ScriptGenerationError: If generation fails
            QualityCheckFailedError: If quality checks fail after max retries
        """
        if config is None:
            config = self.config

        model = self._get_model_name(config)

        logger.info(
            f"Generating script for topic {topic_id}",
            extra={"channel_id": str(channel_id), "model": model},
        )

        # Retry loop
        for attempt in range(config.max_retries + 1):
            try:
                script = await self._generate_attempt(topic_id, channel_id, config, attempt)
                logger.info(
                    f"Script generated successfully on attempt {attempt + 1}",
                    extra={
                        "script_id": str(script.id),
                        "quality_passed": script.quality_passed,
                        "word_count": script.word_count,
                    },
                )
                return script

            except QualityCheckFailedError as e:
                logger.warning(
                    f"Quality check failed on attempt {attempt + 1}/{config.max_retries + 1}: {e}"
                )

                if attempt >= config.max_retries or not config.retry_on_failure:
                    raise

                logger.info(f"Retrying generation (attempt {attempt + 2})")

        raise ScriptGenerationError("Max retries exceeded")

    async def _generate_attempt(
        self,
        topic_id: uuid.UUID,
        channel_id: uuid.UUID,
        config: GenerationConfig,
        attempt: int,
    ) -> Script:
        """Single generation attempt.

        Args:
            topic_id: Topic UUID
            channel_id: Channel UUID
            config: Generation config
            attempt: Attempt number (0-indexed)

        Returns:
            Generated Script object

        Raises:
            QualityCheckFailedError: If quality checks fail
        """
        # 1. Build context
        logger.info("Building generation context")
        context = await self.context_builder.build_context(topic_id, channel_id, config)

        # 2. Build prompt
        logger.info("Building prompt")
        prompt = await self.prompt_builder.build_prompt(context)

        # 3. Get model name
        model = self._get_model_name(config)

        # 4. Generate via LLM
        logger.info(f"Calling LLM API ({model})")
        llm_config = LLMConfig(
            model=model,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
        )

        response = await self.llm_client.complete(
            config=llm_config,
            messages=[{"role": "user", "content": prompt}],
        )

        script_text = response.content.strip()
        logger.info(f"Generated {len(script_text)} characters")

        # 5. Quality check
        logger.info("Running quality checks")
        quality_result = await self._check_quality(
            script_text=script_text,
            persona=context.persona,
        )

        if not quality_result["passed"]:
            raise QualityCheckFailedError(f"Quality check failed: {quality_result['reasons']}")

        # 7. Save to database
        logger.info("Saving script to database")
        script = await self._save_script(
            channel_id=channel_id,
            topic_id=topic_id,
            script_text=script_text,
            quality_result=quality_result,
            config=config,
            model_used=model,
            context_chunks_used=len(context.retrieved.similar),
        )

        # 8. Chunk and embed
        logger.info("Chunking and embedding script")
        await self._chunk_and_embed(script)

        return script

    def _parse_script(self, script_text: str) -> dict[str, str]:
        """Parse script into sections.

        Args:
            script_text: Generated script text

        Returns:
            Dict with hook, body, conclusion
        """
        # Simple parsing: assume script follows structure
        # For production, use LLM or regex patterns

        sentences = re.split(r"[.!?]+\s+", script_text.strip())

        if len(sentences) <= 3:
            return {
                "hook": sentences[0] if sentences else "",
                "body": " ".join(sentences[1:-1]) if len(sentences) > 2 else "",
                "conclusion": sentences[-1] if len(sentences) > 1 else "",
            }

        # Hook: First 2-3 sentences
        hook_count = min(3, max(1, len(sentences) // 7))
        hook = " ".join(sentences[:hook_count])

        # Conclusion: Last 1-2 sentences
        conclusion_count = min(2, max(1, len(sentences) // 10))
        conclusion = " ".join(sentences[-conclusion_count:])

        # Body: Middle
        body = " ".join(sentences[hook_count:-conclusion_count])

        return {
            "hook": hook,
            "body": body,
            "conclusion": conclusion,
        }

    async def _check_quality(
        self,
        script_text: str,
        persona: Any,
    ) -> dict[str, Any]:
        """Check script quality against gates.

        Args:
            script_text: Full script text
            persona: Persona object

        Returns:
            Dict with 'passed' (bool) and quality metrics
        """
        reasons = []

        # Extract hook from script (first few sentences)
        parsed = self._parse_script(script_text)
        hook = parsed["hook"]

        # 1. Duration check
        duration = self._estimate_duration(script_text)
        if duration > self.quality_config.max_duration:
            reasons.append(f"Duration too long: {duration}s > {self.quality_config.max_duration}s")
        if duration < self.quality_config.min_duration:
            reasons.append(f"Duration too short: {duration}s < {self.quality_config.min_duration}s")

        # 2. Style check
        style_score = self._calculate_style_score(script_text, persona)
        if style_score < self.quality_config.min_style_score:
            reasons.append(
                f"Style score too low: {style_score:.2f} < {self.quality_config.min_style_score}"
            )

        # 3. Hook check
        hook_score = self._evaluate_hook(hook)
        if hook_score < self.quality_config.min_hook_score:
            reasons.append(
                f"Hook score too low: {hook_score:.2f} < {self.quality_config.min_hook_score}"
            )

        # 4. Forbidden words
        forbidden_words = self._find_forbidden_words(script_text, persona)
        if len(forbidden_words) > self.quality_config.max_forbidden_words:
            reasons.append(
                f"Too many forbidden words: {forbidden_words} "
                f"(max: {self.quality_config.max_forbidden_words})"
            )

        passed = len(reasons) == 0

        return {
            "passed": passed,
            "reasons": reasons,
            "duration": duration,
            "style_score": style_score,
            "hook_score": hook_score,
            "forbidden_words": forbidden_words,
        }

    def _estimate_duration(self, script_text: str) -> int:
        """Estimate script duration in seconds.

        Assumes ~150 words per minute for natural speech.

        Args:
            script_text: Script text

        Returns:
            Estimated duration in seconds
        """
        word_count = len(script_text.split())
        words_per_minute = 150
        duration_seconds = int((word_count / words_per_minute) * 60)
        return duration_seconds

    def _calculate_style_score(self, script_text: str, persona: Any) -> float:
        """Calculate style consistency score.

        Simple heuristic: check for persona-specific patterns.
        For production, use LLM-based style classification.

        Args:
            script_text: Script text
            persona: Persona object

        Returns:
            Style score (0-1)
        """
        score = 0.7  # Base score

        if not persona.communication_style:
            return score

        text_lower = script_text.lower()

        # Check for preferred connectors
        if "connectors" in persona.communication_style:
            connectors = persona.communication_style["connectors"]
            found_connectors = sum(1 for c in connectors if c.lower() in text_lower)
            if connectors:
                score += 0.1 * (found_connectors / len(connectors))

        # Check for sentence endings
        if "sentence_endings" in persona.communication_style:
            endings = persona.communication_style["sentence_endings"]
            found_endings = sum(1 for e in endings if e.lower() in text_lower)
            if endings:
                score += 0.1 * (found_endings / len(endings))

        # Check for avoid words (penalize if found)
        if "avoid_words" in persona.communication_style:
            avoid_words = persona.communication_style["avoid_words"]
            found_avoid = sum(1 for w in avoid_words if w.lower() in text_lower)
            if found_avoid > 0:
                score -= 0.2 * (found_avoid / max(len(avoid_words), 1))

        return max(0.0, min(1.0, score))

    def _evaluate_hook(self, hook: str) -> float:
        """Evaluate hook quality.

        Simple heuristic: check for attention-grabbing patterns.
        For production, use LLM-based hook classification.

        Args:
            hook: Hook text

        Returns:
            Hook score (0-1)
        """
        if not hook:
            return 0.0

        score = 0.5  # Base score

        hook_lower = hook.lower()

        # Question hooks
        if "?" in hook:
            score += 0.2

        # Surprising statements
        surprising_patterns = [
            "you won't believe",
            "surprising",
            "shocking",
            "what if",
            "imagine",
            "놀랍게도",
            "믿기 힘들지만",
            "만약",
        ]
        if any(pattern in hook_lower for pattern in surprising_patterns):
            score += 0.15

        # Numbers (concrete facts)
        if re.search(r"\d+", hook):
            score += 0.1

        # Short and punchy (3-15 words)
        word_count = len(hook.split())
        if 3 <= word_count <= 15:
            score += 0.15

        return min(1.0, score)

    def _find_forbidden_words(self, script_text: str, persona: Any) -> list[str]:
        """Find forbidden words in script.

        Args:
            script_text: Script text
            persona: Persona object

        Returns:
            List of forbidden words found
        """
        if not persona.communication_style or "avoid_words" not in persona.communication_style:
            return []

        forbidden = persona.communication_style["avoid_words"]
        text_lower = script_text.lower()

        found = [word for word in forbidden if word.lower() in text_lower]
        return found

    async def _save_script(
        self,
        channel_id: uuid.UUID,
        topic_id: uuid.UUID,
        script_text: str,
        quality_result: dict[str, Any],
        config: GenerationConfig,
        model_used: str,
        context_chunks_used: int,
    ) -> Script:
        """Save script to database.

        Args:
            channel_id: Channel UUID
            topic_id: Topic UUID
            script_text: Full script text
            quality_result: Quality check result
            config: Generation config
            model_used: Actual model used (LiteLLM format)
            context_chunks_used: Number of chunks used

        Returns:
            Saved Script object
        """
        word_count = len(script_text.split())

        script = Script(
            channel_id=channel_id,
            topic_id=topic_id,
            script_text=script_text,
            estimated_duration=quality_result["duration"],
            word_count=word_count,
            style_score=quality_result["style_score"],
            hook_score=quality_result["hook_score"],
            forbidden_words=quality_result["forbidden_words"],
            quality_passed=quality_result["passed"],
            generation_model=model_used,
            context_chunks_used=context_chunks_used,
            generation_metadata={
                "temperature": config.temperature,
                "max_tokens": config.max_tokens,
                "target_duration": config.target_duration,
                "style": config.style,
                "format": config.format,
            },
            status=ScriptStatus.GENERATED,
        )

        async with self.db_session_factory() as session:
            session.add(script)
            await session.commit()
            await session.refresh(script)

        return script

    async def _chunk_and_embed(self, script: Script) -> None:
        """Chunk script and generate embeddings.

        Args:
            script: Script object
        """
        # 1. Chunk script
        chunks = await self.chunker.chunk_script(
            script_text=script.script_text,
            channel_id=script.channel_id,
            script_id=script.id,
            content_type=ContentType.SCRIPT,
            embedding_model=self.vector_db.model_name,
        )

        logger.info(f"Created {len(chunks)} chunks")

        # 2. Generate embeddings
        for chunk in chunks:
            embedding = await self.embedder.embed_chunk(
                text=chunk.text,
                position=chunk.position,
                is_opinion=chunk.is_opinion,
                is_example=chunk.is_example,
                keywords=chunk.keywords,
            )
            chunk.embedding = embedding

        # 3. Save to database
        async with self.db_session_factory() as session:
            session.add_all(chunks)
            await session.commit()

        logger.info(f"Saved {len(chunks)} chunks to database with embeddings")

    # =========================================================================
    # Scene-Based Script Generation (BSForge Differentiator)
    # =========================================================================

    async def generate_scene_script(
        self,
        topic_id: uuid.UUID,
        channel_id: uuid.UUID,
        config: GenerationConfig | None = None,
    ) -> Script:
        """Generate scene-based script from topic.

        This method generates scripts with explicit scene structure,
        including COMMENTARY/REACTION scenes for persona opinions.

        Args:
            topic_id: Topic UUID
            channel_id: Channel UUID
            config: Optional generation config

        Returns:
            Script object with scenes (saved to database)

        Raises:
            ScriptGenerationError: If generation fails
            QualityCheckFailedError: If quality checks fail after max retries
        """
        if config is None:
            config = self.config

        model = self._get_model_name(config)

        logger.info(
            f"Generating scene-based script for topic {topic_id}",
            extra={"channel_id": str(channel_id), "model": model},
        )

        # Retry loop
        for attempt in range(config.max_retries + 1):
            try:
                script = await self._generate_scene_attempt(topic_id, channel_id, config, attempt)
                logger.info(
                    f"Scene script generated successfully on attempt {attempt + 1}",
                    extra={
                        "script_id": str(script.id),
                        "quality_passed": script.quality_passed,
                        "scene_count": len(script.scenes) if script.scenes else 0,
                    },
                )
                return script

            except QualityCheckFailedError as e:
                logger.warning(
                    f"Scene quality check failed on attempt {attempt + 1}/{config.max_retries + 1}: {e}"
                )

                if attempt >= config.max_retries or not config.retry_on_failure:
                    raise

                logger.info(f"Retrying scene generation (attempt {attempt + 2})")

        raise ScriptGenerationError("Max retries exceeded for scene generation")

    async def _generate_scene_attempt(
        self,
        topic_id: uuid.UUID,
        channel_id: uuid.UUID,
        config: GenerationConfig,
        attempt: int,
    ) -> Script:
        """Single scene generation attempt.

        Args:
            topic_id: Topic UUID
            channel_id: Channel UUID
            config: Generation config
            attempt: Attempt number (0-indexed)

        Returns:
            Generated Script object with scenes

        Raises:
            QualityCheckFailedError: If quality checks fail
        """
        # 1. Build context
        logger.info("Building generation context for scene script")
        context = await self.context_builder.build_context(topic_id, channel_id, config)

        # 2. Build scene-aware prompt
        logger.info("Building scene prompt")
        prompt = await self.prompt_builder.build_scene_prompt(context)

        # 3. Get model name
        model = self._get_model_name(config)

        # 4. Generate via LLM
        logger.info(f"Calling LLM API for scene script ({model})")
        llm_config = LLMConfig(
            model=model,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
        )

        response = await self.llm_client.complete(
            config=llm_config,
            messages=[{"role": "user", "content": prompt}],
        )

        raw_response = response.content.strip()
        logger.info(f"Generated scene response: {len(raw_response)} characters")

        # 5. Parse JSON scenes
        logger.info("Parsing scene response")
        scene_script = self._parse_scene_response(raw_response)

        # Apply recommended transitions
        scene_script.apply_recommended_transitions()

        # 6. Quality check
        logger.info("Running scene quality checks")
        quality_result = await self._check_scene_quality(
            scene_script=scene_script,
            persona=context.persona,
        )

        if not quality_result["passed"]:
            raise QualityCheckFailedError(
                f"Scene quality check failed: {quality_result['reasons']}"
            )

        # 7. Save to database
        logger.info("Saving scene script to database")
        script = await self._save_scene_script(
            channel_id=channel_id,
            topic_id=topic_id,
            scene_script=scene_script,
            quality_result=quality_result,
            config=config,
            model_used=model,
            context_chunks_used=len(context.retrieved.similar),
        )

        # 8. Chunk and embed
        logger.info("Chunking and embedding scene script")
        await self._chunk_and_embed(script)

        return script

    def _parse_scene_response(self, response: str) -> SceneScript:
        """Parse LLM response into SceneScript.

        Args:
            response: Raw LLM response (should be JSON array)

        Returns:
            SceneScript object

        Raises:
            ScriptGenerationError: If parsing fails
        """
        # Try to extract JSON array from response
        # Handle cases where LLM adds markdown code blocks
        json_match = re.search(r"\[[\s\S]*\]", response)
        if not json_match:
            raise ScriptGenerationError(
                f"No valid JSON array in scene response. Got: {response[:200]}..."
            )

        try:
            raw_scenes = json.loads(json_match.group())
        except json.JSONDecodeError as e:
            raise ScriptGenerationError(f"Invalid JSON in scene response: {e}") from e

        if not isinstance(raw_scenes, list) or len(raw_scenes) == 0:
            raise ScriptGenerationError("Scene response must be a non-empty array")

        scenes: list[Scene] = []
        for i, raw in enumerate(raw_scenes):
            try:
                # Parse scene_type
                scene_type_str = raw.get("scene_type", "content")
                try:
                    scene_type = SceneType(scene_type_str)
                except ValueError:
                    logger.warning(
                        f"Unknown scene_type '{scene_type_str}' at index {i}, using 'content'"
                    )
                    scene_type = SceneType.CONTENT

                # Parse visual_hint
                visual_hint_str = raw.get("visual_hint", "stock_image")
                try:
                    visual_hint = VisualHintType(visual_hint_str)
                except ValueError:
                    visual_hint = VisualHintType.STOCK_IMAGE

                scenes.append(
                    Scene(
                        scene_type=scene_type,
                        text=raw.get("text", ""),
                        keyword=raw.get("keyword"),
                        visual_hint=visual_hint,
                        emphasis_words=raw.get("emphasis_words", []),
                    )
                )
            except Exception as e:
                logger.warning(f"Failed to parse scene at index {i}: {e}")
                # Try to create a basic scene from text
                if "text" in raw:
                    scenes.append(
                        Scene(
                            scene_type=SceneType.CONTENT,
                            text=raw["text"],
                        )
                    )

        if not scenes:
            raise ScriptGenerationError("No valid scenes parsed from response")

        return SceneScript(scenes=scenes)

    async def _check_scene_quality(
        self,
        scene_script: SceneScript,
        persona: Any,
    ) -> dict[str, Any]:
        """Check scene script quality.

        Args:
            scene_script: SceneScript object
            persona: Persona object

        Returns:
            Dict with 'passed' (bool) and quality metrics
        """
        reasons: list[str] = []

        # 1. Structure validation
        structure_errors = scene_script.validate_structure()
        # Filter out recommendations (not hard failures)
        hard_errors = [e for e in structure_errors if "Recommend" not in e]
        reasons.extend(hard_errors)

        # Log recommendations
        recommendations = [e for e in structure_errors if "Recommend" in e]
        for rec in recommendations:
            logger.warning(f"Scene structure recommendation: {rec}")

        # 2. Duration check
        duration = scene_script.total_estimated_duration
        if duration > self.quality_config.max_duration:
            reasons.append(
                f"Duration too long: {duration:.1f}s > {self.quality_config.max_duration}s"
            )
        if duration < self.quality_config.min_duration:
            reasons.append(
                f"Duration too short: {duration:.1f}s < {self.quality_config.min_duration}s"
            )

        # 3. Style check on full text
        full_text = scene_script.full_text
        style_score = self._calculate_style_score(full_text, persona)
        if style_score < self.quality_config.min_style_score:
            reasons.append(
                f"Style score too low: {style_score:.2f} < {self.quality_config.min_style_score}"
            )

        # 4. Hook check
        hook_scenes = [s for s in scene_script.scenes if s.scene_type == SceneType.HOOK]
        hook_text = hook_scenes[0].text if hook_scenes else ""
        hook_score = self._evaluate_hook(hook_text)
        if hook_score < self.quality_config.min_hook_score:
            reasons.append(
                f"Hook score too low: {hook_score:.2f} < {self.quality_config.min_hook_score}"
            )

        # 5. Forbidden words
        forbidden_words = self._find_forbidden_words(full_text, persona)
        if len(forbidden_words) > self.quality_config.max_forbidden_words:
            reasons.append(
                f"Too many forbidden words: {forbidden_words} "
                f"(max: {self.quality_config.max_forbidden_words})"
            )

        passed = len(reasons) == 0

        return {
            "passed": passed,
            "reasons": reasons,
            "duration": int(duration),
            "style_score": style_score,
            "hook_score": hook_score,
            "forbidden_words": forbidden_words,
            "scene_count": len(scene_script.scenes),
            "has_commentary": scene_script.has_commentary,
        }

    async def _save_scene_script(
        self,
        channel_id: uuid.UUID,
        topic_id: uuid.UUID,
        scene_script: SceneScript,
        quality_result: dict[str, Any],
        config: GenerationConfig,
        model_used: str,
        context_chunks_used: int,
    ) -> Script:
        """Save scene-based script to database.

        Args:
            channel_id: Channel UUID
            topic_id: Topic UUID
            scene_script: SceneScript object
            quality_result: Quality check result
            config: Generation config
            model_used: Actual model used
            context_chunks_used: Number of chunks used

        Returns:
            Saved Script object
        """
        full_text = scene_script.full_text
        word_count = len(full_text.split())

        # Serialize scenes for JSONB storage
        scenes_data = [scene.model_dump(mode="json") for scene in scene_script.scenes]

        script = Script(
            channel_id=channel_id,
            topic_id=topic_id,
            script_text=full_text,
            title_text=scene_script.title_text,
            scenes=scenes_data,
            estimated_duration=quality_result["duration"],
            word_count=word_count,
            style_score=quality_result["style_score"],
            hook_score=quality_result["hook_score"],
            forbidden_words=quality_result["forbidden_words"],
            quality_passed=quality_result["passed"],
            generation_model=model_used,
            context_chunks_used=context_chunks_used,
            generation_metadata={
                "temperature": config.temperature,
                "max_tokens": config.max_tokens,
                "target_duration": config.target_duration,
                "style": config.style,
                "format": config.format,
                "scene_based": True,
                "scene_count": quality_result["scene_count"],
                "has_commentary": quality_result["has_commentary"],
            },
            status=ScriptStatus.GENERATED,
        )

        async with self.db_session_factory() as session:
            session.add(script)
            await session.commit()
            await session.refresh(script)

        return script


__all__ = [
    "ScriptGenerator",
    "ScriptGenerationError",
    "QualityCheckFailedError",
]
