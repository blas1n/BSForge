"""Subtitle generation service.

This module provides subtitle generation from text and timing information,
with support for ASS (Advanced SubStation Alpha) and SRT formats.

Supports template-based styling via VideoTemplateConfig for consistent
visual styles across different video types (e.g., Korean viral, minimal).

Scene-based generation:
- generate_from_scene_results() respects scene boundaries
- Different visual styles for NEUTRAL vs PERSONA scenes
"""

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from app.config.video import CompositionConfig, SubtitleConfig, SubtitleStyleConfig
from app.core.config_loader import load_language_config
from app.core.logging import get_logger
from app.services.generator.templates import (
    ASSDialogueParams,
    ASSStyleParams,
    ASSTemplateLoader,
)
from app.services.generator.tts.base import SceneTTSResult, WordTimestamp

logger = get_logger(__name__)

# Safety margin when clamping subtitle end times to scene boundaries (seconds)
_SCENE_BOUNDARY_MARGIN = 0.02
# Minimum gap between consecutive subtitle segments to prevent overlap (seconds)
_MIN_SEGMENT_GAP = 0.05


def _hex_to_inline_bgr(hex_color: str) -> str:
    """Convert hex color to ASS inline override BGR format (&HBBGGRR&).

    Used for inline color tags like {\\c&HBBGGRR&} in subtitle text.
    For style definitions (with alpha), use SubtitleGenerator._hex_to_ass_color().

    Args:
        hex_color: Hex color string (e.g., "#FF69B4" or "FF69B4")

    Returns:
        ASS BGR color string (e.g., "&HB469FF&")
    """
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6 or not all(c in "0123456789abcdefABCDEF" for c in hex_color):
        logger.warning("invalid_hex_color", hex_color=hex_color)
        hex_color = "FFFFFF"
    r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6]
    return f"&H{b}{g}{r}&"


if TYPE_CHECKING:
    from app.config.persona import PersonaStyleConfig
    from app.config.video_template import VideoTemplateConfig
    from app.models.scene import Scene, VisualStyle


@lru_cache(maxsize=1)
def _get_korean_subtitle_config() -> dict[str, Any]:
    """Get Korean subtitle configuration from config/language/korean.yaml."""
    config = load_language_config("korean")
    subtitle = config.get("subtitle", {})
    return subtitle if isinstance(subtitle, dict) else {}


@lru_cache(maxsize=1)
def _get_korean_timing_config() -> dict[str, Any]:
    """Get Korean timing configuration from config/language/korean.yaml."""
    config = load_language_config("korean")
    timing = config.get("timing", {})
    return timing if isinstance(timing, dict) else {}


@dataclass
class SubtitleSegment:
    """Single subtitle segment.

    Attributes:
        index: Segment index (1-based for SRT)
        start: Start time in seconds
        end: End time in seconds
        text: Subtitle text
        words: Optional word-level timestamps for this segment
    """

    index: int
    start: float
    end: float
    text: str
    words: list[WordTimestamp] | None = None


@dataclass
class SubtitleFile:
    """Complete subtitle file.

    Attributes:
        segments: List of subtitle segments
        style: Subtitle style configuration
        format: File format (ass or srt)
    """

    segments: list[SubtitleSegment]
    style: SubtitleStyleConfig = field(default_factory=SubtitleStyleConfig)
    format: Literal["ass", "srt"] = "ass"


class SubtitleGenerator:
    """Generate subtitles from text and timing information.

    Supports two generation modes:
    1. From word timestamps (preferred, more accurate)
    2. From script with even time distribution (fallback)

    Example:
        >>> generator = SubtitleGenerator()
        >>> timestamps = [WordTimestamp("Hello", 0.0, 0.5), ...]
        >>> subtitle = generator.generate_from_timestamps(timestamps)
        >>> generator.to_ass(subtitle, Path("/tmp/subtitle.ass"))
    """

    def __init__(
        self,
        config: SubtitleConfig,
        composition_config: CompositionConfig,
        template_loader: ASSTemplateLoader,
    ) -> None:
        """Initialize SubtitleGenerator.

        Args:
            config: Subtitle configuration
            composition_config: Video composition config for resolution settings
            template_loader: ASS template loader
        """
        self.config = config
        self.composition_config = composition_config
        self.template_loader = template_loader

    def generate_from_timestamps(
        self,
        word_timestamps: list[WordTimestamp],
        template: "VideoTemplateConfig | None" = None,
    ) -> SubtitleFile:
        """Generate subtitles from word-level timestamps.

        Groups words into segments based on template settings or defaults.
        Shorter segments improve readability on mobile devices.

        Args:
            word_timestamps: List of word timestamps
            template: Video template config for styling (optional)

        Returns:
            SubtitleFile with segments
        """
        if not word_timestamps:
            logger.warning("No word timestamps provided")
            return SubtitleFile(segments=[], style=self.config.style)

        segments: list[SubtitleSegment] = []
        current_words: list[WordTimestamp] = []
        current_text = ""
        segment_index = 1

        # Get timing defaults from config
        timing_config = _get_korean_timing_config()
        karaoke_max_words = timing_config.get("karaoke_max_words", 4)
        default_max_words = timing_config.get("default_max_words", 10)

        # Get max_chars from template or config
        if template and template.subtitle:
            max_chars = template.subtitle.max_chars_per_line
            # Shorter segments for karaoke-enabled templates
            if template.subtitle.karaoke_enabled:
                max_words_per_segment = karaoke_max_words
            else:
                max_words_per_segment = default_max_words
        else:
            max_chars = self.config.max_chars_per_line
            max_words_per_segment = default_max_words

        for word_ts in word_timestamps:
            word = word_ts.word.strip()
            if not word:
                continue

            # Check if we should create a new segment
            potential_text = f"{current_text} {word}".strip() if current_text else word
            word_count = len(current_words) + 1

            # 문장 부호로 끝나거나, 단어 수/글자 수 초과시 새 세그먼트
            should_break = (
                (len(potential_text) > max_chars and current_words)
                or (word_count > max_words_per_segment and current_words)
                or (current_text and current_text[-1] in ".!?。！？")
            )

            if should_break:
                # Create segment from current words
                segments.append(
                    SubtitleSegment(
                        index=segment_index,
                        start=current_words[0].start,
                        end=current_words[-1].end,
                        text=current_text,
                        words=current_words.copy(),
                    )
                )
                segment_index += 1
                current_words = []
                current_text = ""

            current_words.append(word_ts)
            current_text = f"{current_text} {word}".strip() if current_text else word

        # Add remaining words as final segment
        if current_words:
            segments.append(
                SubtitleSegment(
                    index=segment_index,
                    start=current_words[0].start,
                    end=current_words[-1].end,
                    text=current_text,
                    words=current_words.copy(),
                )
            )

        logger.info("subtitle_segments_from_timestamps", count=len(segments))

        return SubtitleFile(
            segments=segments,
            style=self.config.style,
            format=self.config.format,
        )

    def generate_from_script(
        self,
        script: str,
        audio_duration: float,
    ) -> SubtitleFile:
        """Generate subtitles with even time distribution.

        Splits script into sentences and distributes time evenly.
        Use this as fallback when word timestamps are not available.

        Args:
            script: Script text
            audio_duration: Total audio duration in seconds

        Returns:
            SubtitleFile with segments
        """
        # Split into sentences
        sentences = self._split_into_sentences(script)
        if not sentences:
            logger.warning("No sentences found in script")
            return SubtitleFile(segments=[], style=self.config.style)

        # Calculate time per sentence (proportional to length)
        total_chars = sum(len(s) for s in sentences)
        if total_chars == 0:
            return SubtitleFile(segments=[], style=self.config.style)

        segments: list[SubtitleSegment] = []
        current_time = 0.0

        for sentence in sentences:
            # Calculate duration proportional to sentence length
            sentence_duration = (len(sentence) / total_chars) * audio_duration

            # Split long sentences into multiple segments
            sub_segments = self._split_long_text(sentence)

            sub_duration = sentence_duration / len(sub_segments) if sub_segments else 0

            for sub_text in sub_segments:
                segments.append(
                    SubtitleSegment(
                        index=len(segments) + 1,
                        start=current_time,
                        end=current_time + sub_duration,
                        text=sub_text,
                    )
                )
                current_time += sub_duration

        logger.info("subtitle_segments_from_script", count=len(segments))

        return SubtitleFile(
            segments=segments,
            style=self.config.style,
            format=self.config.format,
        )

    def to_ass(
        self,
        subtitle: SubtitleFile,
        output_path: Path,
        template: "VideoTemplateConfig | None" = None,
    ) -> Path:
        """Export subtitles to ASS format.

        ASS format supports advanced styling including:
        - Fonts, colors, outlines
        - Background boxes
        - Positioning
        - Word highlighting (karaoke)

        Args:
            subtitle: Subtitle data
            output_path: Output file path
            template: Video template config for styling (optional)

        Returns:
            Path to generated ASS file
        """
        output_path = output_path.with_suffix(".ass")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        style = subtitle.style

        # Resolve styling from template or config defaults
        sv = self._resolve_style_vars(style, template)
        highlight_color_hex = sv["highlight_color_hex"]
        fade_in_ms = sv["fade_in_ms"]
        fade_out_ms = sv["fade_out_ms"]
        karaoke_enabled = sv["karaoke_enabled"]

        # Build styles using template loader
        default_style = self._make_style_params("Default", sv)
        highlight_color_ass = self._hex_to_ass_color(highlight_color_hex)
        highlight_sv = {**sv, "primary_color": highlight_color_ass, "bold": 1}
        highlight_style = self._make_style_params("Highlight", highlight_sv)

        # Render header with styles
        ass_content = self.template_loader.render_header(
            title="BSForge Generated Subtitles",
            styles=[default_style, highlight_style],
        )

        # Add dialogue lines
        for segment in subtitle.segments:
            start_time = self._seconds_to_ass_time(segment.start)
            end_time = self._seconds_to_ass_time(segment.end)

            # Apply karaoke highlighting if enabled and words available
            if karaoke_enabled and segment.words:
                text = self._apply_karaoke_effect(segment)
            else:
                text = segment.text

            # Auto-highlight numbers and percentages (Korean Shorts style)
            text = self._auto_highlight_numbers(text, highlight_color_hex)

            # Add fade animation if configured
            if fade_in_ms > 0 or fade_out_ms > 0:
                text = f"{{\\fad({fade_in_ms},{fade_out_ms})}}{text}"

            dialogue = self.template_loader.render_dialogue(
                ASSDialogueParams(start=start_time, end=end_time, text=text)
            )
            ass_content += dialogue + "\n"

        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(ass_content)
        except OSError as e:
            logger.error("ass_write_failed", path=str(output_path), error=str(e))
            raise

        logger.info("ass_subtitle_generated", path=str(output_path))
        return output_path

    def to_srt(
        self,
        subtitle: SubtitleFile,
        output_path: Path,
    ) -> Path:
        """Export subtitles to SRT format.

        SRT is a simple format supported by most players.
        Styling is not preserved in SRT.

        Args:
            subtitle: Subtitle data
            output_path: Output file path

        Returns:
            Path to generated SRT file
        """
        output_path = output_path.with_suffix(".srt")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        srt_content = ""

        for segment in subtitle.segments:
            start_time = self._seconds_to_srt_time(segment.start)
            end_time = self._seconds_to_srt_time(segment.end)

            srt_content += f"{segment.index}\n"
            srt_content += f"{start_time} --> {end_time}\n"
            srt_content += f"{segment.text}\n\n"

        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(srt_content)
        except OSError as e:
            logger.error("srt_write_failed", path=str(output_path), error=str(e))
            raise

        logger.info("srt_subtitle_generated", path=str(output_path))
        return output_path

    def _split_into_sentences(self, text: str) -> list[str]:
        """Split text into sentences.

        Args:
            text: Text to split

        Returns:
            List of sentences
        """
        # Split on sentence-ending punctuation
        sentences = re.split(r"(?<=[.!?。！？])\s+", text.strip())
        return [s.strip() for s in sentences if s.strip()]

    def _split_long_text(self, text: str) -> list[str]:
        """Split long text into chunks based on max_chars_per_line.

        Args:
            text: Text to split

        Returns:
            List of text chunks
        """
        max_chars = self.config.max_chars_per_line
        words = text.split()
        chunks: list[str] = []
        current_chunk = ""

        for word in words:
            potential = f"{current_chunk} {word}".strip() if current_chunk else word

            if len(potential) > max_chars and current_chunk:
                chunks.append(current_chunk)
                current_chunk = word
            else:
                current_chunk = potential

        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    def _resolve_style_vars(
        self,
        style: SubtitleStyleConfig,
        template: "VideoTemplateConfig | None",
    ) -> dict[str, Any]:
        """Resolve styling variables from template or config defaults.

        Returns a dict with keys: font_name, font_size, outline_width, bold, italic,
        primary_color, outline_color, bg_color, border_style, alignment, margin_v,
        fade_in_ms, fade_out_ms, karaoke_enabled, highlight_color_hex.
        """
        if template and template.subtitle:
            tmpl_sub = template.subtitle
            tmpl_layout = template.layout

            if tmpl_sub.background_enabled:
                bg_color = self._hex_to_ass_color(
                    tmpl_sub.background_color, opacity=tmpl_sub.background_opacity
                )
                border_style = 3
            else:
                bg_color = "&H00000000"
                border_style = 1

            position = tmpl_layout.subtitle_position if tmpl_layout else "center"
            margin_ratio = tmpl_layout.subtitle_margin_ratio if tmpl_layout else 0.5
            video_height = self.composition_config.height
            if position == "bottom":
                alignment, margin_v = 2, int(video_height * margin_ratio)
            elif position == "top":
                alignment, margin_v = 8, int(video_height * (1 - margin_ratio))
            else:
                alignment, margin_v = 5, int(video_height * (0.5 - margin_ratio / 2))

            return {
                "font_name": tmpl_sub.font_name,
                "font_size": tmpl_sub.font_size,
                "outline_width": tmpl_sub.outline_width,
                "bold": 1 if tmpl_sub.bold else 0,
                "italic": 1 if getattr(tmpl_sub, "italic", False) else 0,
                "primary_color": self._hex_to_ass_color(tmpl_sub.primary_color),
                "outline_color": self._hex_to_ass_color(tmpl_sub.outline_color),
                "bg_color": bg_color,
                "border_style": border_style,
                "alignment": alignment,
                "margin_v": margin_v,
                "fade_in_ms": tmpl_sub.fade_in_ms,
                "fade_out_ms": tmpl_sub.fade_out_ms,
                "karaoke_enabled": tmpl_sub.karaoke_enabled,
                "highlight_color_hex": tmpl_sub.highlight_color,
            }

        return {
            "font_name": style.font_name,
            "font_size": style.font_size,
            "outline_width": style.outline_width,
            "bold": 0,
            "italic": 0,
            "primary_color": self._hex_to_ass_color(style.primary_color),
            "outline_color": self._hex_to_ass_color(style.outline_color),
            "bg_color": self._hex_to_ass_color(
                style.background_color,
                opacity=style.background_opacity if style.background_enabled else 0.0,
            ),
            "border_style": 3 if style.background_enabled else 1,
            "alignment": self._get_ass_alignment(),
            "margin_v": self.config.margin_bottom,
            "fade_in_ms": 100,
            "fade_out_ms": 50,
            "karaoke_enabled": self.config.highlight_current_word,
            "highlight_color_hex": self.config.highlight_color,
        }

    def _make_style_params(self, name: str, sv: dict[str, Any]) -> ASSStyleParams:
        """Create ASSStyleParams from resolved style variables."""
        return ASSStyleParams(
            name=name,
            font_name=sv["font_name"],
            font_size=sv["font_size"],
            primary_color=sv["primary_color"],
            outline_color=sv["outline_color"],
            back_color=sv["bg_color"],
            bold=sv["bold"],
            italic=sv["italic"],
            border_style=sv["border_style"],
            outline=sv["outline_width"],
            alignment=sv["alignment"],
            margin_l=self.config.margin_horizontal,
            margin_r=self.config.margin_horizontal,
            margin_v=sv["margin_v"],
        )

    def _hex_to_ass_color(
        self,
        hex_color: str,
        opacity: float = 1.0,
    ) -> str:
        """Convert hex color to ASS format (&HAABBGGRR).

        Args:
            hex_color: Hex color (e.g., "#FFFFFF")
            opacity: Opacity (0-1)

        Returns:
            ASS color string
        """
        # Remove # prefix and validate
        hex_color = hex_color.lstrip("#")
        if len(hex_color) != 6 or not all(c in "0123456789abcdefABCDEF" for c in hex_color):
            logger.warning("invalid_hex_color", hex_color=hex_color)
            hex_color = "FFFFFF"

        # Parse RGB
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)

        # Calculate alpha (inverted: 00 = opaque, FF = transparent)
        alpha = int((1 - opacity) * 255)

        # ASS uses &HAABBGGRR format (reversed)
        return f"&H{alpha:02X}{b:02X}{g:02X}{r:02X}"

    def _seconds_to_ass_time(self, seconds: float) -> str:
        """Convert seconds to ASS time format (H:MM:SS.CC).

        Args:
            seconds: Time in seconds

        Returns:
            ASS time string
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        centisecs = int((seconds % 1) * 100)

        return f"{hours}:{minutes:02d}:{secs:02d}.{centisecs:02d}"

    def _seconds_to_srt_time(self, seconds: float) -> str:
        """Convert seconds to SRT time format (HH:MM:SS,mmm).

        Args:
            seconds: Time in seconds

        Returns:
            SRT time string
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)

        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def _get_ass_alignment(self) -> int:
        """Get ASS alignment value based on position config.

        Returns:
            ASS alignment value (1-9, numpad layout)
        """
        position_map = {
            "bottom": 2,  # Bottom center
            "center": 5,  # Middle center
            "top": 8,  # Top center
        }
        return position_map.get(self.config.position, 2)

    def _apply_karaoke_effect(self, segment: SubtitleSegment) -> str:
        """Apply karaoke highlighting effect to segment.

        Args:
            segment: Subtitle segment with words

        Returns:
            Text with karaoke tags
        """
        if not segment.words:
            return segment.text

        # Build karaoke text with timing
        parts: list[str] = []

        for i, word in enumerate(segment.words):
            # Duration in centiseconds
            word_duration = (word.end - word.start) * 100  # centiseconds

            # Use \\k tag for karaoke timing
            # Add space between words (except for first word)
            if i > 0:
                parts.append(" ")
            parts.append(f"{{\\k{int(word_duration)}}}{word.word}")

        return "".join(parts)

    def _auto_highlight_numbers(
        self,
        text: str,
        highlight_color: str = "#FFFF00",  # 노란색 기본값
    ) -> str:
        """Automatically highlight numbers, percentages, and key data.

        Korean Shorts style: important numbers should pop visually.
        Protects existing ASS tags (e.g. karaoke \\k timing) from being altered.

        Args:
            text: Original text
            highlight_color: Hex color for highlights (default: yellow)

        Returns:
            Text with ASS color tags for numbers/percentages
        """
        ass_color = _hex_to_inline_bgr(highlight_color)

        # Protect existing ASS tags from number matching (e.g. {\k101}, {\fad(100,50)})
        protected_tags: list[str] = []

        def protect_tag(m: re.Match[str]) -> str:
            protected_tags.append(m.group())
            return f"\x00TAG{len(protected_tags) - 1}\x00"

        safe_text = re.sub(r"\{[^}]*\}", protect_tag, text)

        # Combined pattern to match all number formats in one pass
        # Priority: Korean expressions > units > percentages > plain numbers
        combined_pattern = (
            r"(\d+분의\s*\d+|\d+(?:만|억|조|배|점|위|개|명|원|달러|불)|\d+(?:\.\d+)?%|\d{2,})"
        )

        def replacer(match: re.Match[str]) -> str:
            return f"{{\\c{ass_color}}}{match.group(1)}{{\\c}}"

        safe_text = re.sub(combined_pattern, replacer, safe_text)

        # Restore protected ASS tags
        for i, tag in enumerate(protected_tags):
            safe_text = safe_text.replace(f"\x00TAG{i}\x00", tag)

        return safe_text

    def _split_scene_text_with_timing(
        self,
        scene_text: str,
        word_timestamps: list[WordTimestamp],
        scene_result: "SceneTTSResult",
        visual_style: "VisualStyle",
        emphasis_words: list[str],
        persona_style: "PersonaStyleConfig | None",
        max_chars: int,
        max_words: int,
        start_index: int,
    ) -> list[SubtitleSegment]:
        """Split scene.text into segments with timing from word_timestamps.

        This method uses scene.text (original notation like GPT-4, Claude 3.5)
        for display while deriving timing from TTS word timestamps
        (which may be based on pronunciation text).

        Args:
            scene_text: Original text from scene.text (for subtitle display)
            word_timestamps: Word timing from TTS (may be from tts_text)
            scene_result: TTS result with timing info
            visual_style: Visual style for this scene
            emphasis_words: Words to emphasize
            persona_style: Optional persona styling
            max_chars: Maximum characters per line
            max_words: Maximum words per segment
            start_index: Starting segment index

        Returns:
            List of subtitle segments using scene_text with TTS timing
        """
        segments: list[SubtitleSegment] = []
        segment_index = start_index

        # If no word timestamps, create a single segment for entire scene
        if not word_timestamps:
            styled_text = self._apply_scene_styling(
                scene_text, visual_style, emphasis_words, persona_style
            )
            segments.append(
                SubtitleSegment(
                    index=segment_index,
                    start=scene_result.start_offset,
                    end=scene_result.start_offset + scene_result.duration_seconds,
                    text=styled_text,
                    words=None,
                )
            )
            return segments

        # Split scene_text into words (Korean-aware)
        scene_words = scene_text.split()
        if not scene_words:
            return segments

        # Use scene duration for timing calculation
        scene_duration = scene_result.duration_seconds

        # Group scene words into segments
        current_segment_words: list[str] = []

        for word_idx, word in enumerate(scene_words):
            word_count = len(current_segment_words) + 1

            # Check if we should break
            potential_text = " ".join(current_segment_words + [word])
            should_break = self._should_break_korean(
                current_text=" ".join(current_segment_words),
                next_word=word,
                potential_text=potential_text,
                word_count=word_count,
                max_chars=max_chars,
                max_words=max_words,
            )

            if should_break and current_segment_words:
                # Create segment with timing proportional to words processed
                progress_start = (word_idx - len(current_segment_words)) / len(scene_words)
                progress_end = word_idx / len(scene_words)

                seg_start = scene_result.start_offset + progress_start * scene_duration
                seg_end = scene_result.start_offset + progress_end * scene_duration

                segment_text = " ".join(current_segment_words)
                styled_text = self._apply_scene_styling(
                    segment_text, visual_style, emphasis_words, persona_style
                )
                segments.append(
                    SubtitleSegment(
                        index=segment_index,
                        start=seg_start,
                        end=seg_end,
                        text=styled_text,
                        words=None,  # No word-level timing for original text
                    )
                )
                segment_index += 1
                current_segment_words = []

            current_segment_words.append(word)

        # Don't forget the last segment
        if current_segment_words:
            progress_start = (len(scene_words) - len(current_segment_words)) / len(scene_words)
            seg_start = scene_result.start_offset + progress_start * scene_duration
            seg_end = scene_result.start_offset + scene_duration

            segment_text = " ".join(current_segment_words)
            styled_text = self._apply_scene_styling(
                segment_text, visual_style, emphasis_words, persona_style
            )
            segments.append(
                SubtitleSegment(
                    index=segment_index,
                    start=seg_start,
                    end=seg_end,
                    text=styled_text,
                    words=None,
                )
            )

        return segments

    def _split_words_with_timestamps(
        self,
        word_timestamps: list[WordTimestamp],
        scene_result: "SceneTTSResult",
        visual_style: "VisualStyle",
        emphasis_words: list[str],
        persona_style: "PersonaStyleConfig | None",
        max_chars: int,
        max_words: int,
        start_index: int,
    ) -> list[SubtitleSegment]:
        """Split word timestamps into segments, preserving per-word timing for karaoke.

        Used when scene.tts_text is None (display text == TTS text),
        meaning word timestamps map directly to the display words.

        Args:
            word_timestamps: Word timing from TTS
            scene_result: TTS result with timing info
            visual_style: Visual style for this scene
            emphasis_words: Words to emphasize
            persona_style: Optional persona styling
            max_chars: Maximum characters per line
            max_words: Maximum words per segment
            start_index: Starting segment index

        Returns:
            List of subtitle segments with word-level timing
        """
        segments: list[SubtitleSegment] = []
        segment_index = start_index
        current_words: list[WordTimestamp] = []
        current_text = ""

        for word_ts in word_timestamps:
            word = word_ts.word.strip()
            if not word:
                continue

            potential_text = f"{current_text} {word}".strip() if current_text else word
            word_count = len(current_words) + 1

            should_break = self._should_break_korean(
                current_text=current_text,
                next_word=word,
                potential_text=potential_text,
                word_count=word_count,
                max_chars=max_chars,
                max_words=max_words,
            )

            if should_break and current_words:
                styled_text = self._apply_scene_styling(
                    current_text,
                    visual_style,
                    emphasis_words,
                    persona_style,
                )
                segments.append(
                    SubtitleSegment(
                        index=segment_index,
                        start=current_words[0].start + scene_result.start_offset,
                        end=current_words[-1].end + scene_result.start_offset,
                        text=styled_text,
                        words=current_words.copy(),
                    )
                )
                segment_index += 1
                current_words = []
                current_text = ""

            current_words.append(word_ts)
            current_text = f"{current_text} {word}".strip() if current_text else word

        if current_words:
            styled_text = self._apply_scene_styling(
                current_text,
                visual_style,
                emphasis_words,
                persona_style,
            )
            segments.append(
                SubtitleSegment(
                    index=segment_index,
                    start=current_words[0].start + scene_result.start_offset,
                    end=current_words[-1].end + scene_result.start_offset,
                    text=styled_text,
                    words=current_words.copy(),
                )
            )

        return segments

    def generate_from_scene_results(
        self,
        scene_results: list[SceneTTSResult],
        scenes: list["Scene"],
        persona_style: "PersonaStyleConfig | None" = None,
        template: "VideoTemplateConfig | None" = None,
    ) -> SubtitleFile:
        """Generate subtitles from scene-based TTS results.

        This method respects scene boundaries when grouping subtitles,
        ensuring that subtitle segments don't cross scene transitions.
        Each scene type gets appropriate visual styling.

        Priority:
        1. If scene.subtitle_segments is defined, use those segments (문맥에 맞게 끊기)
        2. Otherwise, auto-split based on TTS word boundaries and max_chars

        Args:
            scene_results: List of SceneTTSResult from synthesize_scenes()
            scenes: List of Scene objects with scene metadata
            persona_style: Optional PersonaStyleConfig for persona scene styling
            template: Optional VideoTemplateConfig for base styling

        Returns:
            SubtitleFile with scene-aware segments
        """
        from app.models.scene import VisualStyle

        if not scene_results:
            logger.warning("No scene results provided")
            return SubtitleFile(segments=[], style=self.config.style)

        if len(scene_results) != len(scenes):
            logger.warning(
                "scene_tts_count_mismatch",
                tts_results=len(scene_results),
                scenes=len(scenes),
            )

        all_segments: list[SubtitleSegment] = []
        segment_index = 1

        # Get max_chars from template or config
        if template and template.subtitle:
            max_chars = template.subtitle.max_chars_per_line
            max_words_per_segment = 4 if template.subtitle.karaoke_enabled else 10
        else:
            max_chars = self.config.max_chars_per_line
            max_words_per_segment = 10

        for i, scene_result in enumerate(scene_results):
            # Get corresponding scene (if available)
            scene = scenes[i] if i < len(scenes) else None
            visual_style = scene.inferred_visual_style if scene else VisualStyle.NEUTRAL
            emphasis_words = scene.emphasis_words if scene else []

            # Get word timestamps for this scene
            word_timestamps = scene_result.word_timestamps or []

            # Priority 1: Use manual subtitle_segments if defined
            if scene and scene.subtitle_segments:
                segments_from_manual = self._create_segments_from_manual(
                    subtitle_segments=scene.subtitle_segments,
                    word_timestamps=word_timestamps,
                    scene_result=scene_result,
                    visual_style=visual_style,
                    emphasis_words=emphasis_words,
                    persona_style=persona_style,
                    start_index=segment_index,
                )
                all_segments.extend(segments_from_manual)
                segment_index += len(segments_from_manual)
                continue

            # Priority 2: When tts_text differs from text, word timestamps
            # can't be mapped to display text. Use proportional timing instead.
            if scene and scene.tts_text is not None:
                scene_segments = self._split_scene_text_with_timing(
                    scene_text=scene.text,
                    word_timestamps=word_timestamps,
                    scene_result=scene_result,
                    visual_style=visual_style,
                    emphasis_words=emphasis_words,
                    persona_style=persona_style,
                    max_chars=max_chars,
                    max_words=max_words_per_segment,
                    start_index=segment_index,
                )
                all_segments.extend(scene_segments)
                segment_index += len(scene_segments)
                continue

            # Priority 3: When tts_text is None (text == tts_content), word
            # timestamps map directly to display text. Use them for karaoke.
            if not word_timestamps:
                continue

            karaoke_segments = self._split_words_with_timestamps(
                word_timestamps=word_timestamps,
                scene_result=scene_result,
                visual_style=visual_style,
                emphasis_words=emphasis_words,
                persona_style=persona_style,
                max_chars=max_chars,
                max_words=max_words_per_segment,
                start_index=segment_index,
            )
            all_segments.extend(karaoke_segments)
            segment_index += len(karaoke_segments)

        # Post-process 1: clamp each segment's end to its scene boundary.
        # TTS word timestamps can slightly exceed scene duration, causing
        # the last 2-4 characters to render in the next scene cut.
        # Uses bisect for O(N log M) instead of O(N*M) nested loops.
        from bisect import bisect_right

        scene_boundaries: list[float] = [
            sr.start_offset + sr.duration_seconds for sr in scene_results
        ]

        for seg in all_segments:
            # Find the scene boundary this segment should be clamped to.
            # bisect_right returns the first boundary AFTER seg.start,
            # which is the end of the scene this segment belongs to.
            # e.g. boundaries=[5.0, 8.0], seg.start=5.0 → idx=1 → boundary=8.0 (scene 1 end)
            idx = bisect_right(scene_boundaries, seg.start)
            if idx < len(scene_boundaries):
                boundary = scene_boundaries[idx]
                if seg.end > boundary:
                    seg.end = boundary - _SCENE_BOUNDARY_MARGIN

        # Post-process 2: enforce minimum gap between consecutive segments
        # to prevent subtitle overlap in the renderer.
        for i in range(len(all_segments) - 1):
            if all_segments[i].end > all_segments[i + 1].start - _MIN_SEGMENT_GAP:
                adjusted_end = all_segments[i + 1].start - _MIN_SEGMENT_GAP
                # Prevent invalid segment where start >= end
                all_segments[i].end = max(adjusted_end, all_segments[i].start)

        logger.info(
            f"Generated {len(all_segments)} scene-aware subtitle segments "
            f"from {len(scene_results)} scenes"
        )

        return SubtitleFile(
            segments=all_segments,
            style=self.config.style,
            format=self.config.format,
        )

    def _should_break_korean(
        self,
        current_text: str,
        next_word: str,
        potential_text: str,
        word_count: int,
        max_chars: int,
        max_words: int,
    ) -> bool:
        """Determine if subtitle should break at this point (Korean-aware).

        Korean subtitle breaking rules:
        1. Break AFTER sentence-ending markers: ~요, ~다, ~죠, ~네, ~거든요, ~세요
        2. Break AFTER comma or period
        3. Break BEFORE connectors: 근데, 그래서, 하지만, 그리고, 사실
        4. Respect max_chars limit
        5. Use max_words as soft limit (can be exceeded to complete a phrase)

        Args:
            current_text: Current segment text so far
            next_word: Next word to potentially add
            potential_text: What text would be if we add next_word
            word_count: How many words would be in segment if we add next_word
            max_chars: Maximum characters per line
            max_words: Soft maximum words per segment

        Returns:
            True if we should break before adding next_word
        """
        if not current_text:
            return False

        # Load Korean rules from config
        korean_config = _get_korean_subtitle_config()
        timing_config = _get_korean_timing_config()

        # Korean sentence endings that signal natural break points
        sentence_endings = tuple(korean_config.get("sentence_endings", []))

        # Connectors that should start a new segment
        connectors = tuple(korean_config.get("connectors", []))

        # Punctuation characters
        punctuation = korean_config.get("punctuation_with_comma", ".!?。！？,，")

        # Word limit overhead for soft breaks
        word_limit_overhead = timing_config.get("word_limit_overhead", 2)

        # 1. Hard break: exceeds max_chars
        if len(potential_text) > max_chars:
            return True

        # 2. Break after punctuation
        if current_text and current_text[-1] in punctuation:
            return True

        # 3. Break after Korean sentence endings
        for ending in sentence_endings:
            if current_text.endswith(ending):
                return True

        # 4. Break before connectors (next_word starts a new thought)
        for connector in connectors:
            if next_word.startswith(connector):
                return True

        # 5. Soft break: exceeded word limit, but only if we have a natural point
        # For karaoke style (max_words=4~5), be a bit more flexible
        if word_count > max_words:
            # Check if current_text ends with particles that complete a phrase
            # (subject markers, topic markers, object markers)
            complete_particles = tuple(korean_config.get("complete_particles", []))
            for particle in complete_particles:
                if current_text.endswith(particle):
                    return True
            # Also break if we're significantly over the limit
            if word_count > max_words + word_limit_overhead:
                return True

        return False

    def _create_segments_from_manual(
        self,
        subtitle_segments: list[str],
        word_timestamps: list[WordTimestamp],
        scene_result: SceneTTSResult,
        visual_style: "VisualStyle",
        emphasis_words: list[str],
        persona_style: "PersonaStyleConfig | None",
        start_index: int,
    ) -> list[SubtitleSegment]:
        """Create subtitle segments from manually defined breaks.

        Matches manual segment text to TTS word timestamps to get accurate timing.
        Falls back to proportional timing if word timestamps don't match.

        Args:
            subtitle_segments: List of manually defined segment texts
            word_timestamps: Word-level timestamps from TTS
            scene_result: Scene TTS result for timing info
            visual_style: Visual style for this scene
            emphasis_words: Words to emphasize
            persona_style: Persona style config
            start_index: Starting segment index

        Returns:
            List of SubtitleSegment with proper timing
        """
        segments: list[SubtitleSegment] = []
        segment_index = start_index

        if not word_timestamps:
            # No word timestamps - distribute time proportionally
            total_chars = sum(len(seg) for seg in subtitle_segments)
            current_time = scene_result.start_offset

            for seg_text in subtitle_segments:
                seg_duration = (
                    (len(seg_text) / total_chars) * scene_result.duration_seconds
                    if total_chars > 0
                    else scene_result.duration_seconds / len(subtitle_segments)
                )
                styled_text = self._apply_scene_styling(
                    seg_text, visual_style, emphasis_words, persona_style
                )
                segments.append(
                    SubtitleSegment(
                        index=segment_index,
                        start=current_time,
                        end=current_time + seg_duration,
                        text=styled_text,
                        words=None,
                    )
                )
                segment_index += 1
                current_time += seg_duration

            return segments

        # Build a mapping of words to their timestamps
        # Normalize words for matching (remove spaces, punctuation variations)
        word_ts_idx = 0
        total_words = len(word_timestamps)

        for seg_pos, seg_text in enumerate(subtitle_segments):
            # Find words in this segment
            seg_words = seg_text.split()
            matched_timestamps: list[WordTimestamp] = []

            for seg_word in seg_words:
                # Try to find matching word timestamp
                # Allow some flexibility in matching (strip punctuation)
                seg_word_clean = seg_word.strip(".,!?。！？")

                while word_ts_idx < total_words:
                    ts_word = word_timestamps[word_ts_idx]
                    ts_word_clean = ts_word.word.strip().strip(".,!?。！？")

                    if seg_word_clean == ts_word_clean or (
                        seg_word_clean in ts_word_clean
                        and len(seg_word_clean) >= len(ts_word_clean) * 0.7
                    ):
                        matched_timestamps.append(ts_word)
                        word_ts_idx += 1
                        break
                    elif ts_word_clean in seg_word_clean:
                        # Partial match (e.g., compound words)
                        matched_timestamps.append(ts_word)
                        word_ts_idx += 1
                        # Don't break - continue looking for more parts
                    else:
                        # No match - might be a timing gap, skip this timestamp
                        word_ts_idx += 1

            # Create segment with matched timing
            if matched_timestamps:
                start_time = matched_timestamps[0].start + scene_result.start_offset
                end_time = matched_timestamps[-1].end + scene_result.start_offset
            else:
                # Fallback: estimate based on position in scene
                seg_duration = scene_result.duration_seconds / len(subtitle_segments)
                start_time = scene_result.start_offset + (seg_pos * seg_duration)
                end_time = start_time + seg_duration

            styled_text = self._apply_scene_styling(
                seg_text, visual_style, emphasis_words, persona_style
            )
            segments.append(
                SubtitleSegment(
                    index=segment_index,
                    start=start_time,
                    end=end_time,
                    text=styled_text,
                    words=matched_timestamps if matched_timestamps else None,
                )
            )
            segment_index += 1

        return segments

    def _apply_scene_styling(
        self,
        text: str,
        visual_style: "VisualStyle",
        emphasis_words: list[str],
        persona_style: "PersonaStyleConfig | None" = None,
    ) -> str:
        """Apply styling based on scene visual style.

        Args:
            text: Original text
            visual_style: Scene's visual style (NEUTRAL, PERSONA, EMPHASIS)
            emphasis_words: Words to highlight
            persona_style: Optional PersonaStyleConfig

        Returns:
            Styled text (may include ASS tags for special styling)
        """
        result = text

        # Highlight emphasis words (wrap with secondary color tag)
        # Note: This creates inline ASS override tags
        if emphasis_words and persona_style:
            ass_color = _hex_to_inline_bgr(persona_style.secondary_color)
            for word in emphasis_words:
                # Match whole word only, replace first occurrence to avoid
                # corrupting already-inserted ASS tags
                pattern = re.compile(re.escape(word))
                if pattern.search(result):
                    highlighted = f"{{\\c{ass_color}}}{word}{{\\c}}"
                    repl = highlighted  # bind for lambda closure
                    result = pattern.sub(lambda _, r=repl: r, result, count=1)

        return result

    def to_ass_with_scene_styles(
        self,
        subtitle: SubtitleFile,
        output_path: Path,
        scenes: list["Scene"],
        scene_results: list[SceneTTSResult],
        persona_style: "PersonaStyleConfig | None" = None,
        template: "VideoTemplateConfig | None" = None,
    ) -> Path:
        """Export subtitles to ASS format with scene-specific styles.

        Creates multiple ASS styles for different visual styles (NEUTRAL, PERSONA, EMPHASIS)
        and applies them based on which scene each subtitle segment belongs to.

        Args:
            subtitle: Subtitle data
            output_path: Output file path
            scenes: List of Scene objects
            scene_results: List of SceneTTSResult for timing lookup
            persona_style: Optional PersonaStyleConfig
            template: Video template config for base styling

        Returns:
            Path to generated ASS file
        """
        from app.models.scene import VisualStyle

        output_path = output_path.with_suffix(".ass")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        style = subtitle.style

        # Resolve styling from template or config defaults (shared with to_ass)
        sv = self._resolve_style_vars(style, template)
        highlight_color_hex = sv["highlight_color_hex"]
        fade_in_ms = sv["fade_in_ms"]
        fade_out_ms = sv["fade_out_ms"]
        karaoke_enabled = sv["karaoke_enabled"]

        # Create style params for each visual style (same base, different names)
        neutral_style_params = self._make_style_params("Neutral", sv)
        persona_style_params = self._make_style_params("Persona", sv)
        emphasis_style_params = self._make_style_params("Emphasis", sv)

        # Render header with styles
        ass_content = self.template_loader.render_header(
            title="BSForge Scene-Based Subtitles",
            styles=[neutral_style_params, persona_style_params, emphasis_style_params],
        )

        # Build scene timing lookup: scene_index -> (start, end)
        scene_timings: list[tuple[float, float]] = []
        for sr in scene_results:
            scene_timings.append((sr.start_offset, sr.start_offset + sr.duration_seconds))

        # Add dialogue lines with appropriate style
        for segment in subtitle.segments:
            start_time = self._seconds_to_ass_time(segment.start)
            end_time = self._seconds_to_ass_time(segment.end)

            # Determine which scene this segment belongs to
            scene_idx = self._find_scene_index(segment.start, scene_timings)
            scene = scenes[scene_idx] if 0 <= scene_idx < len(scenes) else None
            visual_style = scene.inferred_visual_style if scene else VisualStyle.NEUTRAL

            # Map visual style to ASS style name
            style_name = {
                VisualStyle.NEUTRAL: "Neutral",
                VisualStyle.PERSONA: "Persona",
                VisualStyle.EMPHASIS: "Emphasis",
            }.get(visual_style, "Neutral")

            # Apply karaoke if enabled and words available
            if karaoke_enabled and segment.words:
                text = self._apply_karaoke_effect(segment)
            else:
                text = segment.text

            # Auto-highlight numbers and percentages (Korean Shorts style)
            text = self._auto_highlight_numbers(text, highlight_color_hex)

            # Add fade animation
            if fade_in_ms > 0 or fade_out_ms > 0:
                text = f"{{\\fad({fade_in_ms},{fade_out_ms})}}{text}"

            dialogue = self.template_loader.render_dialogue(
                ASSDialogueParams(start=start_time, end=end_time, style=style_name, text=text)
            )
            ass_content += dialogue + "\n"

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(ass_content)

        logger.info("scene_styled_ass_generated", path=str(output_path))
        return output_path

    def _find_scene_index(self, timestamp: float, scene_timings: list[tuple[float, float]]) -> int:
        """Find which scene a timestamp belongs to.

        Args:
            timestamp: Time in seconds
            scene_timings: List of (start, end) tuples for each scene

        Returns:
            Scene index (0-based), or -1 if not found
        """
        for i, (start, end) in enumerate(scene_timings):
            if start <= timestamp < end:
                return i
        # If timestamp is exactly at the end of the last scene, return last index
        if scene_timings and timestamp >= scene_timings[-1][1] - 0.01:
            return len(scene_timings) - 1
        return -1


__all__ = [
    "SubtitleGenerator",
    "SubtitleSegment",
    "SubtitleFile",
]
