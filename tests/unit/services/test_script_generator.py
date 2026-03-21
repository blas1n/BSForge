"""Unit tests for script generator service."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config.persona import (
    CommunicationStyle,
    PersonaConfig,
    Perspective,
    VoiceConfig,
)
from app.infrastructure.llm import LLMResponse
from app.models.scene import SceneType
from app.services.script_generator import ScriptGenerationResult, ScriptGenerator


def _make_persona(**kwargs: object) -> PersonaConfig:
    """Create a PersonaConfig with sensible defaults for testing."""
    defaults = {
        "name": "테크브로",
        "tagline": "뻔한 소리 없이 핵심만",
        "voice": VoiceConfig(gender="male", service="edge-tts", voice_id="ko-KR-InJoonNeural"),
        "communication": CommunicationStyle(tone="friendly", formality="semi-formal"),
        "perspective": Perspective(),
    }
    defaults.update(kwargs)
    return PersonaConfig(**defaults)


@pytest.fixture
def mock_llm_client() -> MagicMock:
    """Create a mock LLM client."""
    client = MagicMock()
    client.complete = AsyncMock()
    return client


@pytest.fixture
def mock_prompt_manager() -> MagicMock:
    """Create a mock prompt manager."""
    pm = MagicMock()
    pm.render.return_value = "rendered prompt"
    pm.get_llm_settings.return_value = MagicMock(
        model="",
        max_tokens=2000,
        temperature=0.7,
    )
    return pm


@pytest.fixture
def sample_llm_response() -> dict:
    """Sample JSON response from LLM."""
    return {
        "headline": "AI가 바꾸는 미래",
        "scenes": [
            {
                "scene_type": "hook",
                "text": "여러분, AI가 세상을 바꾸고 있습니다.",
                "visual_keyword": "AI technology future",
            },
            {
                "scene_type": "content",
                "text": "최근 AI 기술의 발전 속도가 놀랍습니다.",
                "visual_keyword": "technology progress chart",
            },
            {
                "scene_type": "conclusion",
                "text": "앞으로의 변화가 기대됩니다.",
                "visual_keyword": "hopeful future",
            },
        ],
    }


@pytest.fixture
def generator(mock_llm_client: MagicMock, mock_prompt_manager: MagicMock) -> ScriptGenerator:
    """Create ScriptGenerator with mocked dependencies."""
    return ScriptGenerator(
        llm_client=mock_llm_client,
        prompt_manager=mock_prompt_manager,
    )


class TestScriptGenerator:
    """Tests for ScriptGenerator."""

    @pytest.mark.asyncio
    async def test_generate_returns_result(
        self,
        generator: ScriptGenerator,
        mock_llm_client: MagicMock,
        sample_llm_response: dict,
    ) -> None:
        """Test that generate returns a ScriptGenerationResult."""
        mock_llm_client.complete.return_value = LLMResponse(
            content=json.dumps(sample_llm_response),
            model="test-model",
            usage={"prompt_tokens": 100, "completion_tokens": 200, "total_tokens": 300},
        )

        result = await generator.generate(
            topic_title="AI 뉴스",
            topic_summary="AI 기술 발전",
            topic_terms=["AI", "기술"],
        )

        assert isinstance(result, ScriptGenerationResult)
        assert result.scene_script.headline == "AI가 바꾸는 미래"
        assert len(result.scene_script.scenes) == 3
        assert result.model == "test-model"

    @pytest.mark.asyncio
    async def test_generate_with_persona(
        self,
        generator: ScriptGenerator,
        mock_llm_client: MagicMock,
        mock_prompt_manager: MagicMock,
        sample_llm_response: dict,
    ) -> None:
        """Test that persona config is passed to prompt variables."""
        mock_llm_client.complete.return_value = LLMResponse(
            content=json.dumps(sample_llm_response),
            model="test-model",
            usage={},
        )

        persona = _make_persona()

        await generator.generate(
            topic_title="AI 뉴스",
            topic_summary="요약",
            topic_terms=["AI"],
            persona=persona,
        )

        # Verify render was called with persona variables
        render_kwargs = mock_prompt_manager.render.call_args
        assert render_kwargs.kwargs.get("persona_name") == "테크브로"
        assert render_kwargs.kwargs.get("persona_tagline") == "뻔한 소리 없이 핵심만"

    @pytest.mark.asyncio
    async def test_generate_scene_types(
        self,
        generator: ScriptGenerator,
        mock_llm_client: MagicMock,
        sample_llm_response: dict,
    ) -> None:
        """Test that scene types are correctly parsed."""
        mock_llm_client.complete.return_value = LLMResponse(
            content=json.dumps(sample_llm_response),
            model="test",
            usage={},
        )

        result = await generator.generate(
            topic_title="test",
            topic_summary="test",
            topic_terms=[],
        )

        assert result.scene_script.scenes[0].scene_type == SceneType.HOOK
        assert result.scene_script.scenes[1].scene_type == SceneType.CONTENT
        assert result.scene_script.scenes[2].scene_type == SceneType.CONCLUSION

    @pytest.mark.asyncio
    async def test_generate_strips_markdown_code_blocks(
        self,
        generator: ScriptGenerator,
        mock_llm_client: MagicMock,
        sample_llm_response: dict,
    ) -> None:
        """Test that markdown code blocks are stripped from response."""
        wrapped = f"```json\n{json.dumps(sample_llm_response)}\n```"
        mock_llm_client.complete.return_value = LLMResponse(
            content=wrapped,
            model="test",
            usage={},
        )

        result = await generator.generate(
            topic_title="test",
            topic_summary="test",
            topic_terms=[],
        )

        assert result.scene_script.headline == "AI가 바꾸는 미래"
        assert len(result.scene_script.scenes) == 3

    @pytest.mark.asyncio
    async def test_generate_invalid_json_raises(
        self,
        generator: ScriptGenerator,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test that invalid JSON raises ValueError."""
        mock_llm_client.complete.return_value = LLMResponse(
            content="not valid json",
            model="test",
            usage={},
        )

        with pytest.raises(ValueError, match="Failed to parse"):
            await generator.generate(
                topic_title="test",
                topic_summary="test",
                topic_terms=[],
            )

    @pytest.mark.asyncio
    async def test_generate_empty_scenes_raises(
        self,
        generator: ScriptGenerator,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test that empty scenes list raises ValueError."""
        mock_llm_client.complete.return_value = LLMResponse(
            content=json.dumps({"headline": "test", "scenes": []}),
            model="test",
            usage={},
        )

        with pytest.raises(ValueError, match="no scenes"):
            await generator.generate(
                topic_title="test",
                topic_summary="test",
                topic_terms=[],
            )

    def test_build_variables_without_persona(self, generator: ScriptGenerator) -> None:
        """Test _build_variables without persona."""
        variables = generator._build_variables(
            topic_title="Test",
            topic_summary="Summary",
            topic_terms=["AI"],
            persona=None,
            target_duration=55,
            video_format="YouTube Shorts",
        )

        assert variables["topic_title"] == "Test"
        assert variables["persona_name"] is None
        assert variables["target_duration"] == 55

    def test_build_variables_includes_current_date(self, generator: ScriptGenerator) -> None:
        """Test _build_variables includes current_date for LLM context."""

        variables = generator._build_variables(
            topic_title="Test",
            topic_summary="Summary",
            topic_terms=["AI"],
            persona=None,
            target_duration=55,
            video_format="YouTube Shorts",
        )

        assert "current_date" in variables
        # Validate ISO date format (YYYY-MM-DD) instead of comparing to now()
        # to avoid midnight UTC race conditions
        import re

        assert re.match(r"^\d{4}-\d{2}-\d{2}$", variables["current_date"])

    def test_build_variables_with_persona(self, generator: ScriptGenerator) -> None:
        """Test _build_variables with persona."""
        persona = _make_persona()

        variables = generator._build_variables(
            topic_title="Test",
            topic_summary="Summary",
            topic_terms=["AI"],
            persona=persona,
            target_duration=55,
            video_format="YouTube Shorts",
        )

        assert variables["persona_name"] == "테크브로"
        assert variables["persona_tagline"] == "뻔한 소리 없이 핵심만"


class TestInputValidation:
    """Tests for input validation in generate()."""

    @pytest.mark.asyncio
    async def test_empty_title_raises(self, generator: ScriptGenerator) -> None:
        """Empty topic_title raises ValueError."""
        with pytest.raises(ValueError, match="topic_title cannot be empty"):
            await generator.generate(
                topic_title="",
                topic_summary="Some summary",
                topic_terms=["test"],
            )

    @pytest.mark.asyncio
    async def test_whitespace_title_raises(self, generator: ScriptGenerator) -> None:
        """Whitespace-only topic_title raises ValueError."""
        with pytest.raises(ValueError, match="topic_title cannot be empty"):
            await generator.generate(
                topic_title="   ",
                topic_summary="Some summary",
                topic_terms=["test"],
            )

    @pytest.mark.asyncio
    async def test_empty_summary_raises(self, generator: ScriptGenerator) -> None:
        """Empty topic_summary raises ValueError."""
        with pytest.raises(ValueError, match="topic_summary cannot be empty"):
            await generator.generate(
                topic_title="Valid title",
                topic_summary="",
                topic_terms=["test"],
            )
