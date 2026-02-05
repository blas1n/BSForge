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
from app.core.logging import get_logger
from app.core.types import SessionFactory
from app.infrastructure.llm import LLMClient, LLMConfig
from app.infrastructure.pgvector_db import PgVectorDB
from app.models.channel import Persona
from app.models.content_chunk import ContentType
from app.models.scene import Scene, SceneScript, SceneType
from app.models.script import Script, ScriptStatus
from app.prompts.manager import PromptManager, PromptType
from app.services.rag.chunker import ScriptChunker
from app.services.rag.context import ContextBuilder
from app.services.rag.embedder import ContentEmbedder
from app.services.rag.prompt import PromptBuilder
from app.services.rag.quality import ScriptQualityChecker

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
        llm_client: LLMClient,
        prompt_manager: PromptManager,
        db_session_factory: SessionFactory | None = None,
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
            llm_client: LLMClient instance
            prompt_manager: PromptManager for loading templates
            db_session_factory: SQLAlchemy async session factory
            config: Generation configuration (default: from settings)
            quality_config: Quality check configuration
        """
        self.context_builder = context_builder
        self.prompt_builder = prompt_builder
        self.chunker = chunker
        self.embedder = embedder
        self.vector_db = vector_db
        self.llm_client = llm_client
        self.prompt_manager = prompt_manager
        self.db_session_factory = db_session_factory
        self.config = config or GenerationConfig()
        self.quality_config = quality_config or QualityCheckConfig()
        self.quality_checker = ScriptQualityChecker(self.quality_config)

    def _get_llm_config_from_template(self, prompt_type: PromptType) -> LLMConfig:
        """Get LLMConfig from prompt template settings.

        Each prompt template specifies its own model, max_tokens, and temperature.
        This allows per-task model selection (e.g., OpenAI for script generation).

        Args:
            prompt_type: Type of prompt to get settings for

        Returns:
            LLMConfig from prompt template
        """
        llm_settings = self.prompt_manager.get_llm_settings(prompt_type)
        return LLMConfig.from_prompt_settings(llm_settings)

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

        # Get LLM config from prompt template
        llm_config = self._get_llm_config_from_template(PromptType.SCRIPT_GENERATION)

        logger.info(
            f"Generating script for topic {topic_id}",
            extra={"channel_id": str(channel_id), "model": llm_config.model},
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

        # 3. Get LLM config from prompt template
        llm_config = self._get_llm_config_from_template(PromptType.SCRIPT_GENERATION)

        # 4. Generate via LLM
        logger.info(f"Calling LLM API ({llm_config.model})")

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
            model_used=llm_config.model,
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
        persona: Persona,
    ) -> dict[str, Any]:
        """Check script quality against gates.

        Args:
            script_text: Full script text
            persona: Persona object

        Returns:
            Dict with 'passed' (bool) and quality metrics
        """
        # Extract hook from script (first few sentences)
        parsed = self._parse_script(script_text)
        hook = parsed["hook"]

        # Use quality checker
        result = self.quality_checker.check_script(script_text, persona, hook)

        # Build reasons list for failed checks
        reasons = []
        if result.estimated_duration > self.quality_config.max_duration:
            reasons.append(
                f"Duration too long: {result.estimated_duration}s > "
                f"{self.quality_config.max_duration}s"
            )
        if result.estimated_duration < self.quality_config.min_duration:
            reasons.append(
                f"Duration too short: {result.estimated_duration}s < "
                f"{self.quality_config.min_duration}s"
            )
        if result.style_score < self.quality_config.min_style_score:
            reasons.append(
                f"Style score too low: {result.style_score:.2f} < "
                f"{self.quality_config.min_style_score}"
            )
        if result.hook_score < self.quality_config.min_hook_score:
            reasons.append(
                f"Hook score too low: {result.hook_score:.2f} < "
                f"{self.quality_config.min_hook_score}"
            )
        if len(result.forbidden_words) > self.quality_config.max_forbidden_words:
            reasons.append(
                f"Too many forbidden words: {result.forbidden_words} "
                f"(max: {self.quality_config.max_forbidden_words})"
            )

        # Re-evaluate passed considering duration constraints
        passed = len(reasons) == 0

        return {
            "passed": passed,
            "reasons": reasons,
            "duration": result.estimated_duration,
            "style_score": result.style_score,
            "hook_score": result.hook_score,
            "forbidden_words": result.forbidden_words,
        }

    def _estimate_duration(self, script_text: str) -> int:
        """Estimate script duration in seconds. Delegates to quality_checker."""
        return self.quality_checker.estimate_duration(script_text)

    def _calculate_style_score(self, script_text: str, persona: Persona) -> float:
        """Calculate style consistency score. Delegates to quality_checker."""
        return self.quality_checker.calculate_style_score(script_text, persona)

    def _evaluate_hook(self, hook: str) -> float:
        """Evaluate hook quality. Delegates to quality_checker."""
        return self.quality_checker.evaluate_hook(hook)

    def _find_forbidden_words(self, script_text: str, persona: Persona) -> list[str]:
        """Find forbidden words in script. Delegates to quality_checker."""
        return self.quality_checker.find_forbidden_words(script_text, persona)

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

        if self.db_session_factory is None:
            raise ScriptGenerationError("db_session_factory is required to save script")

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
                keywords=chunk.terms or [],
            )
            chunk.embedding = embedding

        # 3. Save to database
        if self.db_session_factory is None:
            raise ScriptGenerationError("db_session_factory is required to save chunks")

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

        # Get LLM config from prompt template (scene-based)
        llm_config = self._get_llm_config_from_template(PromptType.SCRIPT_GENERATION)

        logger.info(
            f"Generating scene-based script for topic {topic_id}",
            extra={"channel_id": str(channel_id), "model": llm_config.model},
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
                max_attempts = config.max_retries + 1
                logger.warning(
                    f"Scene quality check failed on attempt {attempt + 1}/{max_attempts}: {e}"
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
        prompt = await self.prompt_builder.build_prompt(context)

        # 3. Get LLM config from prompt template (scene-based)
        llm_config = self._get_llm_config_from_template(PromptType.SCRIPT_GENERATION)

        # 4. Generate via LLM
        logger.info(f"Calling LLM API for scene script ({llm_config.model})")

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
            model_used=llm_config.model,
            context_chunks_used=len(context.retrieved.similar),
        )

        # 8. Chunk and embed
        logger.info("Chunking and embedding scene script")
        await self._chunk_and_embed(script)

        return script

    def _parse_scene_response(self, response: str) -> SceneScript:
        """Parse LLM response into SceneScript.

        Args:
            response: Raw LLM response (JSON object with headline + scenes, or JSON array)

        Returns:
            SceneScript object

        Raises:
            ScriptGenerationError: If parsing fails
        """
        headline: str | None = None

        # Try to extract JSON object first (new format with headline)
        json_obj_match = re.search(r"\{[\s\S]*\}", response)
        if json_obj_match:
            try:
                parsed = json.loads(json_obj_match.group())
                if isinstance(parsed, dict) and "scenes" in parsed:
                    # New format: {headline, scenes: [...]}
                    headline = parsed.get("headline")
                    raw_scenes = parsed["scenes"]
                elif isinstance(parsed, dict):
                    # Single scene object, wrap in array
                    raw_scenes = [parsed]
                else:
                    raw_scenes = None
            except json.JSONDecodeError:
                raw_scenes = None
        else:
            raw_scenes = None

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

                visual_keyword = raw.get("visual_keyword")
                requires_web_search = raw.get("requires_web_search", False)

                scenes.append(
                    Scene(
                        scene_type=scene_type,
                        text=raw.get("text", ""),
                        visual_keyword=visual_keyword,
                        requires_web_search=requires_web_search,
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

        if not headline:
            raise ScriptGenerationError("headline is required but not found in response")

        return SceneScript(
            scenes=scenes,
            headline=headline,
        )

    async def _check_scene_quality(
        self,
        scene_script: SceneScript,
        persona: Persona,
    ) -> dict[str, Any]:
        """Check scene script quality.

        Args:
            scene_script: SceneScript object
            persona: Persona DB model

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

        # 2. Use quality checker for content quality
        result = self.quality_checker.check_scene_script(scene_script, persona)

        # 3. Duration check (use scene_script's duration, not estimated)
        duration = scene_script.total_estimated_duration
        if duration > self.quality_config.max_duration:
            reasons.append(
                f"Duration too long: {duration:.1f}s > {self.quality_config.max_duration}s"
            )
        if duration < self.quality_config.min_duration:
            reasons.append(
                f"Duration too short: {duration:.1f}s < {self.quality_config.min_duration}s"
            )

        # 4. Style check
        if result.style_score < self.quality_config.min_style_score:
            reasons.append(
                f"Style score too low: {result.style_score:.2f} < "
                f"{self.quality_config.min_style_score}"
            )

        # 5. Hook check
        if result.hook_score < self.quality_config.min_hook_score:
            reasons.append(
                f"Hook score too low: {result.hook_score:.2f} < "
                f"{self.quality_config.min_hook_score}"
            )

        # 6. Forbidden words
        if len(result.forbidden_words) > self.quality_config.max_forbidden_words:
            reasons.append(
                f"Too many forbidden words: {result.forbidden_words} "
                f"(max: {self.quality_config.max_forbidden_words})"
            )

        passed = len(reasons) == 0

        return {
            "passed": passed,
            "reasons": reasons,
            "duration": int(duration),
            "style_score": result.style_score,
            "hook_score": result.hook_score,
            "forbidden_words": result.forbidden_words,
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
            headline=scene_script.headline,
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

        if self.db_session_factory is None:
            raise ScriptGenerationError("db_session_factory is required to save scene script")

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
