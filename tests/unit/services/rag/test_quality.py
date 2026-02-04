"""Tests for ScriptQualityChecker."""

from unittest.mock import MagicMock

import pytest

from app.config.rag import QualityCheckConfig
from app.models.scene import Scene, SceneScript, SceneType, VisualStyle
from app.services.rag.quality import QualityResult, ScriptQualityChecker


@pytest.fixture
def quality_checker() -> ScriptQualityChecker:
    """Create a quality checker with default config."""
    return ScriptQualityChecker()


@pytest.fixture
def custom_config() -> QualityCheckConfig:
    """Create a custom quality check config."""
    return QualityCheckConfig(
        min_style_score=0.8,
        min_hook_score=0.6,
        max_forbidden_words=1,
    )


@pytest.fixture
def mock_persona() -> MagicMock:
    """Create a mock Persona with communication style."""
    persona = MagicMock()
    persona.communication_style = {
        "connectors": ["therefore", "however", "consequently"],
        "sentence_endings": ["right?", "you know"],
        "avoid_words": ["very", "really", "basically"],
    }
    return persona


@pytest.fixture
def mock_persona_no_style() -> MagicMock:
    """Create a mock Persona without communication style."""
    persona = MagicMock()
    persona.communication_style = None
    return persona


class TestQualityResult:
    """Tests for QualityResult dataclass."""

    @pytest.mark.unit
    def test_to_dict(self) -> None:
        """Test QualityResult serialization."""
        result = QualityResult(
            passed=True,
            style_score=0.85,
            hook_score=0.75,
            forbidden_words=["very"],
            word_count=150,
            estimated_duration=60,
        )

        result_dict = result.to_dict()

        assert result_dict["passed"] is True
        assert result_dict["style_score"] == 0.85
        assert result_dict["hook_score"] == 0.75
        assert result_dict["forbidden_words"] == ["very"]
        assert result_dict["word_count"] == 150
        assert result_dict["estimated_duration"] == 60

    @pytest.mark.unit
    def test_to_dict_empty_forbidden_words(self) -> None:
        """Test QualityResult with no forbidden words."""
        result = QualityResult(
            passed=True,
            style_score=0.9,
            hook_score=0.8,
            forbidden_words=[],
            word_count=100,
            estimated_duration=40,
        )

        result_dict = result.to_dict()

        assert result_dict["forbidden_words"] == []


class TestScriptQualityChecker:
    """Tests for ScriptQualityChecker."""

    @pytest.mark.unit
    def test_init_default_config(self) -> None:
        """Test initialization with default config."""
        checker = ScriptQualityChecker()

        assert checker.config is not None
        assert isinstance(checker.config, QualityCheckConfig)

    @pytest.mark.unit
    def test_init_custom_config(self, custom_config: QualityCheckConfig) -> None:
        """Test initialization with custom config."""
        checker = ScriptQualityChecker(config=custom_config)

        assert checker.config.min_style_score == 0.8
        assert checker.config.min_hook_score == 0.6
        assert checker.config.max_forbidden_words == 1


class TestEstimateDuration:
    """Tests for duration estimation."""

    @pytest.mark.unit
    def test_estimate_duration_basic(self, quality_checker: ScriptQualityChecker) -> None:
        """Test basic duration estimation."""
        # 150 words = 60 seconds at 150 WPM
        script = " ".join(["word"] * 150)

        duration = quality_checker.estimate_duration(script)

        assert duration == 60

    @pytest.mark.unit
    def test_estimate_duration_short_script(self, quality_checker: ScriptQualityChecker) -> None:
        """Test duration estimation for short script."""
        # 30 words = 12 seconds
        script = " ".join(["word"] * 30)

        duration = quality_checker.estimate_duration(script)

        assert duration == 12

    @pytest.mark.unit
    def test_estimate_duration_empty_script(self, quality_checker: ScriptQualityChecker) -> None:
        """Test duration estimation for empty script."""
        duration = quality_checker.estimate_duration("")

        assert duration == 0


class TestCalculateStyleScore:
    """Tests for style score calculation."""

    @pytest.mark.unit
    def test_style_score_base_without_communication_style(
        self,
        quality_checker: ScriptQualityChecker,
        mock_persona_no_style: MagicMock,
    ) -> None:
        """Test base style score when persona has no communication style."""
        score = quality_checker.calculate_style_score(
            "This is a test script.", mock_persona_no_style
        )

        assert score == 0.7  # Base score

    @pytest.mark.unit
    def test_style_score_with_connectors(
        self,
        quality_checker: ScriptQualityChecker,
        mock_persona: MagicMock,
    ) -> None:
        """Test style score boost from connector words."""
        script = "Therefore, this is important. However, we should consider."

        score = quality_checker.calculate_style_score(script, mock_persona)

        # Base 0.7 + bonus for connectors
        assert score > 0.7

    @pytest.mark.unit
    def test_style_score_with_sentence_endings(
        self,
        quality_checker: ScriptQualityChecker,
        mock_persona: MagicMock,
    ) -> None:
        """Test style score boost from sentence endings."""
        script = "This is interesting, right? Makes sense, you know."

        score = quality_checker.calculate_style_score(script, mock_persona)

        assert score > 0.7

    @pytest.mark.unit
    def test_style_score_penalty_for_avoid_words(
        self,
        quality_checker: ScriptQualityChecker,
        mock_persona: MagicMock,
    ) -> None:
        """Test style score penalty for forbidden words."""
        script = "This is very basically really important."

        score = quality_checker.calculate_style_score(script, mock_persona)

        # Should be penalized below base
        assert score < 0.7

    @pytest.mark.unit
    def test_style_score_clamped_to_zero_one(
        self,
        quality_checker: ScriptQualityChecker,
        mock_persona: MagicMock,
    ) -> None:
        """Test that style score is clamped between 0 and 1."""
        # Many avoid words should heavily penalize but not go below 0
        script = "Very very really basically very really basically test."

        score = quality_checker.calculate_style_score(script, mock_persona)

        assert 0.0 <= score <= 1.0


class TestEvaluateHook:
    """Tests for hook evaluation."""

    @pytest.mark.unit
    def test_evaluate_hook_empty(self, quality_checker: ScriptQualityChecker) -> None:
        """Test hook score for empty hook."""
        score = quality_checker.evaluate_hook("")

        assert score == 0.0

    @pytest.mark.unit
    def test_evaluate_hook_question(self, quality_checker: ScriptQualityChecker) -> None:
        """Test hook score boost for questions."""
        score = quality_checker.evaluate_hook("Have you ever wondered why?")

        # Base 0.5 + 0.2 for question + 0.15 for word count
        assert score >= 0.7

    @pytest.mark.unit
    def test_evaluate_hook_surprising_pattern(self, quality_checker: ScriptQualityChecker) -> None:
        """Test hook score boost for surprising statements."""
        score = quality_checker.evaluate_hook("You won't believe what happens next!")

        assert score > 0.5

    @pytest.mark.unit
    def test_evaluate_hook_with_numbers(self, quality_checker: ScriptQualityChecker) -> None:
        """Test hook score boost for numeric content."""
        score = quality_checker.evaluate_hook("5 ways to improve your life")

        # Base 0.5 + 0.1 for numbers + 0.15 for word count
        assert score >= 0.65

    @pytest.mark.unit
    def test_evaluate_hook_korean_patterns(self, quality_checker: ScriptQualityChecker) -> None:
        """Test hook score with Korean surprising patterns."""
        score = quality_checker.evaluate_hook("놀랍게도 이것이 가능합니다")

        assert score > 0.5

    @pytest.mark.unit
    def test_evaluate_hook_optimal_length(self, quality_checker: ScriptQualityChecker) -> None:
        """Test hook score for optimal length (3-15 words)."""
        # 7 words - optimal
        score_optimal = quality_checker.evaluate_hook("This is an interesting hook for you")
        # 20 words - too long
        long_hook = " ".join(["word"] * 20)
        score_long = quality_checker.evaluate_hook(long_hook)

        assert score_optimal > score_long

    @pytest.mark.unit
    def test_evaluate_hook_capped_at_one(self, quality_checker: ScriptQualityChecker) -> None:
        """Test that hook score doesn't exceed 1.0."""
        # Combine all bonuses
        hook = "What if I told you 10 surprising facts you won't believe?"

        score = quality_checker.evaluate_hook(hook)

        assert score <= 1.0


class TestFindForbiddenWords:
    """Tests for forbidden word detection."""

    @pytest.mark.unit
    def test_find_forbidden_words_found(
        self,
        quality_checker: ScriptQualityChecker,
        mock_persona: MagicMock,
    ) -> None:
        """Test finding forbidden words in script."""
        script = "This is very basically a really good test."

        found = quality_checker.find_forbidden_words(script, mock_persona)

        assert "very" in found
        assert "really" in found
        assert "basically" in found

    @pytest.mark.unit
    def test_find_forbidden_words_none_found(
        self,
        quality_checker: ScriptQualityChecker,
        mock_persona: MagicMock,
    ) -> None:
        """Test when no forbidden words are present."""
        script = "This is an excellent demonstration of quality."

        found = quality_checker.find_forbidden_words(script, mock_persona)

        assert found == []

    @pytest.mark.unit
    def test_find_forbidden_words_no_communication_style(
        self,
        quality_checker: ScriptQualityChecker,
        mock_persona_no_style: MagicMock,
    ) -> None:
        """Test forbidden word search when no communication style."""
        script = "This is very really basically a test."

        found = quality_checker.find_forbidden_words(script, mock_persona_no_style)

        assert found == []

    @pytest.mark.unit
    def test_find_forbidden_words_case_insensitive(
        self,
        quality_checker: ScriptQualityChecker,
        mock_persona: MagicMock,
    ) -> None:
        """Test case insensitive matching."""
        script = "This is VERY BASICALLY a test."

        found = quality_checker.find_forbidden_words(script, mock_persona)

        assert len(found) == 2


class TestCheckScript:
    """Tests for full script quality check."""

    @pytest.mark.unit
    def test_check_script_passes(
        self,
        quality_checker: ScriptQualityChecker,
        mock_persona: MagicMock,
    ) -> None:
        """Test script that passes quality check."""
        script = (
            "Have you ever wondered why? "
            "Therefore, this is important. However, we should consider, right? "
            "This makes sense, you know."
        )

        result = quality_checker.check_script(script, mock_persona)

        assert isinstance(result, QualityResult)
        assert result.word_count > 0
        assert result.estimated_duration > 0

    @pytest.mark.unit
    def test_check_script_with_custom_hook(
        self,
        quality_checker: ScriptQualityChecker,
        mock_persona: MagicMock,
    ) -> None:
        """Test script check with custom hook text."""
        script = "Main content of the script goes here."
        hook = "What if 5 surprising things happened?"

        result = quality_checker.check_script(script, mock_persona, hook_text=hook)

        assert result.hook_score >= 0.5

    @pytest.mark.unit
    def test_check_script_fails_forbidden_words(
        self,
        mock_persona: MagicMock,
    ) -> None:
        """Test script failing due to too many forbidden words."""
        config = QualityCheckConfig(max_forbidden_words=0)
        checker = ScriptQualityChecker(config=config)
        script = "This is very basically really a test."

        result = checker.check_script(script, mock_persona)

        assert result.passed is False
        assert len(result.forbidden_words) > 0


class TestCheckSceneScript:
    """Tests for scene-based script quality check."""

    @pytest.fixture
    def scene_script(self) -> SceneScript:
        """Create a sample SceneScript."""
        scenes = [
            Scene(
                scene_type=SceneType.HOOK,
                text="Have you ever wondered about this?",
                visual_style=VisualStyle.NEUTRAL,
            ),
            Scene(
                scene_type=SceneType.CONTENT,
                text="Here is the main content of our discussion.",
                visual_style=VisualStyle.NEUTRAL,
            ),
            Scene(
                scene_type=SceneType.CONCLUSION,
                text="In conclusion, this is what we learned.",
                visual_style=VisualStyle.PERSONA,
            ),
        ]
        return SceneScript(scenes=scenes, headline="Test Headline")

    @pytest.mark.unit
    def test_check_scene_script(
        self,
        quality_checker: ScriptQualityChecker,
        mock_persona: MagicMock,
        scene_script: SceneScript,
    ) -> None:
        """Test scene script quality check."""
        result = quality_checker.check_scene_script(scene_script, mock_persona)

        assert isinstance(result, QualityResult)
        assert result.word_count > 0
        assert result.hook_score > 0  # Uses HOOK scene

    @pytest.mark.unit
    def test_check_scene_script_no_hook_scene(
        self,
        quality_checker: ScriptQualityChecker,
        mock_persona: MagicMock,
    ) -> None:
        """Test scene script without explicit HOOK scene."""
        scenes = [
            Scene(
                scene_type=SceneType.CONTENT,
                text="This is the first content scene.",
                visual_style=VisualStyle.NEUTRAL,
            ),
            Scene(
                scene_type=SceneType.CONCLUSION,
                text="This is the conclusion.",
                visual_style=VisualStyle.PERSONA,
            ),
        ]
        scene_script = SceneScript(scenes=scenes, headline="Test Headline")

        result = quality_checker.check_scene_script(scene_script, mock_persona)

        # Should use first scene as hook
        assert result.hook_score >= 0


class TestExtractHook:
    """Tests for hook extraction from script."""

    @pytest.mark.unit
    def test_extract_hook_first_paragraph(self, quality_checker: ScriptQualityChecker) -> None:
        """Test extracting first paragraph as hook."""
        script = "This is the hook paragraph.\n\nThis is the second paragraph."

        hook = quality_checker._extract_hook(script)

        assert hook == "This is the hook paragraph."

    @pytest.mark.unit
    def test_extract_hook_long_paragraph(self, quality_checker: ScriptQualityChecker) -> None:
        """Test extracting first sentence from long paragraph."""
        long_para = "This is the first sentence. " + "x " * 100

        hook = quality_checker._extract_hook(long_para)

        assert hook == "This is the first sentence"

    @pytest.mark.unit
    def test_extract_hook_short_script(self, quality_checker: ScriptQualityChecker) -> None:
        """Test extracting hook from short script."""
        script = "Short script"

        hook = quality_checker._extract_hook(script)

        assert hook == "Short script"
