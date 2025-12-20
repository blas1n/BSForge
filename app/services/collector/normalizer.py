"""Topic normalization service.

This module handles:
1. Language detection
2. Translation (EN→KO or KO→EN as needed)
3. Title cleaning and normalization
4. Summary generation
5. Classification (terms, entities)
6. Hash generation for deduplication
"""

import hashlib
import json
import re
import uuid
from typing import Any

from pydantic import BaseModel

# TODO: This module is legacy and should be migrated to DI container.
from app.core.config import get_config
from app.core.logging import get_logger
from app.infrastructure.llm import LLMClient, LLMConfig, get_llm_client
from app.prompts.manager import PromptType, get_prompt_manager
from app.services.collector.base import NormalizedTopic, RawTopic

logger = get_logger(__name__)


class ClassificationResult(BaseModel):
    """LLM classification result."""

    terms: list[str]
    entities: dict[str, list[str]]
    summary: str


class TopicNormalizer:
    """Normalizes raw topics for storage and scoring.

    Uses LLM (Claude Haiku via LiteLLM) for translation and classification.
    Implements caching to reduce API costs.
    """

    def __init__(self, llm_client: LLMClient | None = None):
        """Initialize normalizer with API clients.

        Args:
            llm_client: LLMClient instance (default: singleton)
        """
        self.llm_client = llm_client or get_llm_client()
        self.supported_languages = {"en", "ko"}
        self.prompt_manager = get_prompt_manager()

    async def normalize(
        self, raw: RawTopic, source_id: uuid.UUID, target_language: str = "ko"
    ) -> NormalizedTopic:
        """Normalize a raw topic.

        Args:
            raw: Raw topic from source
            source_id: Source UUID
            target_language: Channel's target language (default: "ko")
                           Only translates if source language != target language

        Returns:
            Normalized topic ready for scoring

        Raises:
            NormalizationError: If normalization fails
        """
        try:
            # Detect language
            language = await self._detect_language(raw.title)
            logger.debug("Language detected", language=language, title=raw.title[:50])

            # Translate ONLY if source language differs from target language
            title_translated = None
            if language != target_language:
                logger.info(
                    "Translation needed",
                    source_lang=language,
                    target_lang=target_language,
                    title=raw.title[:50],
                )
                title_translated = await self._translate(raw.title, language, target_language)
            else:
                logger.debug(
                    "Translation skipped (same language)",
                    language=language,
                    title=raw.title[:50],
                )

            # Clean and normalize title
            title_normalized = self._clean_title(raw.title)

            # Classify and summarize
            classification = await self._classify(raw.title, raw.content)

            # Generate content hash for deduplication
            content_hash = self._generate_hash(title_normalized, classification.terms)

            normalized = NormalizedTopic(
                source_id=source_id,
                source_url=raw.source_url,
                title_original=raw.title,
                title_translated=title_translated,
                title_normalized=title_normalized,
                summary=classification.summary,
                terms=classification.terms,
                entities=classification.entities,
                language=language,
                published_at=raw.published_at,
                content_hash=content_hash,
                metrics=raw.metrics,
                metadata=raw.metadata,
            )

            logger.info(
                "Topic normalized",
                title=title_normalized[:50],
                language=language,
                terms=classification.terms,
            )
            return normalized

        except Exception as e:
            logger.error(
                "Normalization failed",
                title=raw.title[:50],
                error=str(e),
                exc_info=True,
            )
            raise

    async def _detect_language(self, text: str) -> str:
        """Detect text language using simple heuristics.

        For now, uses basic character detection. Can be replaced with
        langdetect library if needed.

        Args:
            text: Text to analyze

        Returns:
            Language code (en, ko, etc.)
        """
        # Simple Korean detection: check for Hangul characters
        hangul_pattern = re.compile(r"[가-힣]")
        if hangul_pattern.search(text):
            return "ko"
        return "en"

    async def _translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """Translate text using LLM.

        Uses lightweight LLM model for cost-effective translation with good quality.

        Args:
            text: Text to translate
            source_lang: Source language code
            target_lang: Target language code

        Returns:
            Translated text
        """
        try:
            lang_names = {"en": "English", "ko": "Korean"}
            source_name = lang_names.get(source_lang, source_lang)
            target_name = lang_names.get(target_lang, target_lang)

            # Render translation prompt from template
            prompt = self.prompt_manager.render(
                PromptType.TRANSLATION,
                source_name=source_name,
                target_name=target_name,
                text=text,
            )

            cfg = get_config()
            config = LLMConfig(
                model=cfg.llm_model_light,
                max_tokens=cfg.llm_model_light_max_tokens,
                temperature=0.3,
            )

            response = await self.llm_client.complete(
                config=config,
                messages=[{"role": "user", "content": prompt}],
            )

            translation = response.content.strip()
            logger.debug(
                "Translation complete",
                source_lang=source_lang,
                target_lang=target_lang,
                original_length=len(text),
                translated_length=len(translation),
            )
            return translation

        except Exception as e:
            logger.error(
                "Translation failed",
                source_lang=source_lang,
                target_lang=target_lang,
                error=str(e),
                exc_info=True,
            )
            # Return original text if translation fails
            return text

    def _clean_title(self, title: str) -> str:
        """Clean and normalize title text.

        Removes extra whitespace, special characters, emojis, etc.
        Returns lowercase for consistent matching.

        Args:
            title: Raw title

        Returns:
            Cleaned lowercase title
        """
        # Remove URLs
        title = re.sub(r"https?://\S+", "", title)

        # Remove extra whitespace
        title = re.sub(r"\s+", " ", title)

        # Remove leading/trailing whitespace
        title = title.strip()

        # Remove common prefixes (Show HN:, Ask HN:, etc.)
        title = re.sub(r"^(Show HN|Ask HN|Tell HN):\s*", "", title, flags=re.IGNORECASE)

        # Lowercase for consistent matching
        return title.lower()

    async def _classify(self, title: str, content: str | None) -> ClassificationResult:
        """Classify topic using LLM.

        Extracts terms and named entities.
        Generates a concise summary.

        Args:
            title: Topic title
            content: Optional content/body

        Returns:
            Classification result
        """
        try:
            text_to_analyze = title
            if content and len(content) < 1000:
                text_to_analyze = f"{title}\n\n{content}"

            # Render classification prompt from template
            prompt = self.prompt_manager.render(
                PromptType.CLASSIFICATION,
                text_to_analyze=text_to_analyze,
            )

            cfg = get_config()
            config = LLMConfig(
                model=cfg.llm_model_light,
                max_tokens=cfg.llm_model_light_max_tokens,
                temperature=0.0,
            )

            response = await self.llm_client.complete(
                config=config,
                messages=[{"role": "user", "content": prompt}],
            )

            # Parse JSON response
            response_text = response.content.strip()

            # Extract JSON from response (handle markdown code blocks)
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()
            elif "```" in response_text:
                json_start = response_text.find("```") + 3
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()

            # Extract first JSON object (handle extra text after JSON)
            result_dict = self._extract_first_json_object(response_text)

            # Lowercase terms for consistent matching
            terms = [t.lower() for t in result_dict.get("terms", [])]

            result = ClassificationResult(
                terms=terms,
                entities=result_dict.get("entities", {}),
                summary=result_dict.get("summary", title[:200]),
            )

            logger.debug(
                "Classification complete",
                terms=result.terms,
            )
            return result

        except Exception as e:
            logger.error("Classification failed", error=str(e), exc_info=True)
            # Return fallback classification
            return ClassificationResult(
                terms=["general"],
                entities={},
                summary=title[:200],
            )

    def _extract_first_json_object(self, text: str) -> dict[str, Any]:
        """Extract the first valid JSON object from text.

        Handles cases where LLM outputs extra text after the JSON.

        Args:
            text: Text potentially containing JSON

        Returns:
            Parsed JSON object

        Raises:
            json.JSONDecodeError: If no valid JSON found
        """
        # Try parsing the whole text first
        try:
            result: dict[str, Any] = json.loads(text)
            return result
        except json.JSONDecodeError:
            pass

        # Find the first { and try to find matching }
        start = text.find("{")
        if start == -1:
            raise json.JSONDecodeError("No JSON object found", text, 0)

        # Track brace nesting to find the complete object
        depth = 0
        in_string = False
        escape_next = False

        for i, char in enumerate(text[start:], start):
            if escape_next:
                escape_next = False
                continue

            if char == "\\":
                escape_next = True
                continue

            if char == '"' and not escape_next:
                in_string = not in_string
                continue

            if in_string:
                continue

            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    # Found complete JSON object
                    json_str = text[start : i + 1]
                    parsed: dict[str, Any] = json.loads(json_str)
                    return parsed

        # If we get here, no complete object was found
        raise json.JSONDecodeError("Incomplete JSON object", text, len(text))

    def _generate_hash(self, title: str, terms: list[str]) -> str:
        """Generate SHA-256 hash for deduplication.

        Hash is based on normalized title and terms to catch
        near-duplicates with slight title variations.

        Args:
            title: Normalized title (already lowercase)
            terms: Extracted terms (already lowercase)

        Returns:
            SHA-256 hash (64 hex characters)
        """
        # Sort terms for consistency (already lowercase)
        terms_sorted = sorted(terms)

        # Combine for hashing
        hash_input = f"{title}|{'|'.join(terms_sorted)}"

        # Generate SHA-256 hash
        hash_bytes = hashlib.sha256(hash_input.encode("utf-8")).digest()
        return hash_bytes.hex()


__all__ = ["TopicNormalizer", "ClassificationResult"]
