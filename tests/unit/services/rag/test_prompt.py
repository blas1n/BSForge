"""Unit tests for PromptBuilder."""

from unittest.mock import MagicMock, patch

import pytest

from app.config.rag import GenerationConfig
from app.prompts.manager import PromptType
from app.services.rag.context import GenerationContext, RetrievedContent
from app.services.rag.prompt import PromptBuilder

from .conftest import create_retrieval_result


class TestPromptBuilder:
    """Test PromptBuilder functionality."""

    @pytest.fixture
    def prompt_builder(self) -> PromptBuilder:
        """Create PromptBuilder instance."""
        return PromptBuilder()

    @pytest.fixture
    def mock_persona(self) -> MagicMock:
        """Create mock Persona."""
        persona = MagicMock()
        persona.name = "TechExplainer"
        persona.tagline = "Making tech simple"
        persona.description = "I explain complex tech in simple terms."
        persona.expertise = ["Python", "Machine Learning", "Web Development"]
        persona.communication_style = {
            "tone": "friendly",
            "formality": "casual",
            "sentence_endings": ["!", "?"],
            "connectors": ["so", "actually", "basically"],
            "avoid_words": ["terrible", "hate", "boring"],
        }
        persona.perspective = {
            "values": ["simplicity", "clarity", "fun"],
            "biases": "Prefers practical examples over theory",
            "contrarian": False,
        }
        return persona

    @pytest.fixture
    def mock_topic(self) -> MagicMock:
        """Create mock Topic."""
        topic = MagicMock()
        topic.title_normalized = "Python List Comprehensions"
        topic.summary = "A guide to using list comprehensions in Python"
        topic.keywords = ["python", "list", "comprehension"]
        topic.categories = ["programming", "tutorial"]
        topic.source_url = "https://example.com/article"
        return topic

    @pytest.fixture
    def mock_retrieved(self) -> RetrievedContent:
        """Create mock RetrievedContent."""
        return RetrievedContent(
            similar=[
                create_retrieval_result(
                    text="List comprehensions are a concise way to create lists.",
                    score=0.9,
                ),
                create_retrieval_result(
                    text="They can replace traditional for loops.",
                    score=0.85,
                ),
            ],
            opinions=[
                create_retrieval_result(
                    text="I think list comprehensions are one of Python's best features.",
                    score=0.8,
                    is_opinion=True,
                ),
            ],
            examples=[
                create_retrieval_result(
                    text="For example: [x*2 for x in range(10)]",
                    score=0.75,
                    is_example=True,
                ),
            ],
            hooks=[
                create_retrieval_result(
                    text="Ever wanted to write Python like a pro?",
                    score=0.7,
                    performance_score=0.85,
                ),
            ],
        )

    @pytest.fixture
    def generation_context(
        self,
        mock_topic: MagicMock,
        mock_persona: MagicMock,
        mock_retrieved: RetrievedContent,
    ) -> GenerationContext:
        """Create GenerationContext."""
        return GenerationContext(
            topic=mock_topic,
            persona=mock_persona,
            retrieved=mock_retrieved,
            config=GenerationConfig(
                format="shorts",
                target_duration=60,
                style="tutorial",  # Must be valid enum value
            ),
        )

    @pytest.mark.asyncio
    async def test_build_prompt_basic(
        self,
        prompt_builder: PromptBuilder,
        generation_context: GenerationContext,
    ) -> None:
        """Should build prompt successfully."""
        prompt = await prompt_builder.build_prompt(generation_context)

        assert isinstance(prompt, str)
        assert len(prompt) > 0

    @pytest.mark.asyncio
    async def test_build_prompt_uses_prompt_manager(
        self,
        generation_context: GenerationContext,
    ) -> None:
        """Should use PromptManager for template rendering."""
        with patch("app.services.rag.prompt.get_prompt_manager") as mock_get_pm:
            mock_pm = MagicMock()
            mock_pm.render.return_value = "Rendered prompt content"
            mock_get_pm.return_value = mock_pm

            builder = PromptBuilder()
            await builder.build_prompt(generation_context)

            mock_pm.render.assert_called_once()
            call_args = mock_pm.render.call_args
            assert call_args[0][0] == PromptType.SCRIPT_GENERATION

    @pytest.mark.asyncio
    async def test_build_prompt_includes_persona_name(
        self,
        prompt_builder: PromptBuilder,
        generation_context: GenerationContext,
    ) -> None:
        """Should include persona name in prompt."""
        prompt = await prompt_builder.build_prompt(generation_context)

        assert "TechExplainer" in prompt

    @pytest.mark.asyncio
    async def test_build_prompt_includes_topic_title(
        self,
        prompt_builder: PromptBuilder,
        generation_context: GenerationContext,
    ) -> None:
        """Should include topic title in prompt."""
        prompt = await prompt_builder.build_prompt(generation_context)

        assert "Python List Comprehensions" in prompt

    @pytest.mark.asyncio
    async def test_build_prompt_includes_expertise(
        self,
        prompt_builder: PromptBuilder,
        generation_context: GenerationContext,
    ) -> None:
        """Should include persona expertise."""
        prompt = await prompt_builder.build_prompt(generation_context)

        assert "Python" in prompt or "Machine Learning" in prompt

    @pytest.mark.asyncio
    async def test_build_prompt_includes_similar_content(
        self,
        prompt_builder: PromptBuilder,
        generation_context: GenerationContext,
    ) -> None:
        """Should include retrieved similar content."""
        prompt = await prompt_builder.build_prompt(generation_context)

        assert "List comprehensions are a concise way" in prompt

    def test_build_template_variables(
        self,
        prompt_builder: PromptBuilder,
        generation_context: GenerationContext,
    ) -> None:
        """Should build correct template variables."""
        variables = prompt_builder._build_template_variables(generation_context)

        assert "persona_name" in variables
        assert variables["persona_name"] == "TechExplainer"
        assert "topic_title" in variables
        assert variables["topic_title"] == "Python List Comprehensions"
        assert "similar_content" in variables
        assert "opinions" in variables
        assert "examples" in variables
        assert "hooks" in variables

    def test_build_template_variables_with_communication_style(
        self,
        prompt_builder: PromptBuilder,
        generation_context: GenerationContext,
    ) -> None:
        """Should include communication style variables."""
        variables = prompt_builder._build_template_variables(generation_context)

        assert variables["communication_tone"] == "friendly"
        assert variables["communication_formality"] == "casual"
        assert "sentence_endings" in variables
        assert "connectors" in variables
        assert "avoid_words" in variables

    def test_build_template_variables_with_perspective(
        self,
        prompt_builder: PromptBuilder,
        generation_context: GenerationContext,
    ) -> None:
        """Should include perspective variables."""
        variables = prompt_builder._build_template_variables(generation_context)

        assert "perspective_values" in variables
        assert "simplicity" in variables["perspective_values"]
        assert "perspective_biases" in variables
        assert variables["perspective_contrarian"] is False

    def test_build_template_variables_with_config(
        self,
        prompt_builder: PromptBuilder,
        generation_context: GenerationContext,
    ) -> None:
        """Should include generation config variables."""
        variables = prompt_builder._build_template_variables(generation_context)

        assert "video_format" in variables
        assert "YouTube Shorts" in variables["video_format"]
        assert "target_duration" in variables
        assert variables["target_duration"] == 60
        assert "content_style" in variables
        assert variables["content_style"] == "tutorial"

    def test_build_template_variables_formats_retrieved_content(
        self,
        prompt_builder: PromptBuilder,
        generation_context: GenerationContext,
    ) -> None:
        """Should format retrieved content as list of dicts."""
        variables = prompt_builder._build_template_variables(generation_context)

        assert isinstance(variables["similar_content"], list)
        assert len(variables["similar_content"]) == 2
        assert "text" in variables["similar_content"][0]
        assert "score" in variables["similar_content"][0]

    def test_build_template_variables_with_hooks_performance(
        self,
        prompt_builder: PromptBuilder,
        generation_context: GenerationContext,
    ) -> None:
        """Should include hook performance scores."""
        variables = prompt_builder._build_template_variables(generation_context)

        hooks = variables["hooks"]
        assert len(hooks) == 1
        assert "performance_score" in hooks[0]
        assert hooks[0]["performance_score"] == 0.85

    def test_build_template_variables_empty_persona_fields(
        self,
        prompt_builder: PromptBuilder,
        mock_topic: MagicMock,
        mock_retrieved: RetrievedContent,
    ) -> None:
        """Should handle empty persona fields."""
        empty_persona = MagicMock()
        empty_persona.name = None
        empty_persona.tagline = None
        empty_persona.description = None
        empty_persona.expertise = None
        empty_persona.communication_style = None
        empty_persona.perspective = None

        context = GenerationContext(
            topic=mock_topic,
            persona=empty_persona,
            retrieved=mock_retrieved,
            config=GenerationConfig(),
        )

        variables = prompt_builder._build_template_variables(context)

        assert variables["persona_name"] is None
        assert variables["communication_tone"] is None
        assert variables["sentence_endings"] == []
        assert variables["perspective_values"] == []

    def test_build_template_variables_empty_retrieved(
        self,
        prompt_builder: PromptBuilder,
        mock_topic: MagicMock,
        mock_persona: MagicMock,
    ) -> None:
        """Should handle empty retrieved content."""
        empty_retrieved = RetrievedContent(
            similar=[],
            opinions=[],
            examples=[],
            hooks=[],
        )

        context = GenerationContext(
            topic=mock_topic,
            persona=mock_persona,
            retrieved=empty_retrieved,
            config=GenerationConfig(),
        )

        variables = prompt_builder._build_template_variables(context)

        assert variables["similar_content"] == []
        assert variables["opinions"] == []
        assert variables["examples"] == []
        assert variables["hooks"] == []

    @pytest.mark.asyncio
    async def test_build_prompt_long_form_format(
        self,
        prompt_builder: PromptBuilder,
        mock_topic: MagicMock,
        mock_persona: MagicMock,
        mock_retrieved: RetrievedContent,
    ) -> None:
        """Should format correctly for long-form videos."""
        context = GenerationContext(
            topic=mock_topic,
            persona=mock_persona,
            retrieved=mock_retrieved,
            config=GenerationConfig(format="long"),
        )

        variables = prompt_builder._build_template_variables(context)

        assert "long-form video" in variables["video_format"]
