"""Subtitle generation service.

This module provides subtitle generation from text and timing information,
with support for ASS (Advanced SubStation Alpha) and SRT formats.
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from app.config.video import SubtitleConfig, SubtitleStyleConfig
from app.services.generator.tts.base import WordTimestamp

logger = logging.getLogger(__name__)


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

    def __init__(self, config: SubtitleConfig | None = None) -> None:
        """Initialize SubtitleGenerator.

        Args:
            config: Subtitle configuration
        """
        self.config = config or SubtitleConfig()

    def generate_from_timestamps(
        self,
        word_timestamps: list[WordTimestamp],
    ) -> SubtitleFile:
        """Generate subtitles from word-level timestamps.

        Groups words into segments based on max_chars_per_line setting.

        Args:
            word_timestamps: List of word timestamps

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

        for word_ts in word_timestamps:
            word = word_ts.word.strip()
            if not word:
                continue

            # Check if adding this word exceeds line limit
            potential_text = f"{current_text} {word}".strip() if current_text else word

            if len(potential_text) > self.config.max_chars_per_line and current_words:
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

        logger.info(f"Generated {len(segments)} subtitle segments from timestamps")

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

        logger.info(f"Generated {len(segments)} subtitle segments from script")

        return SubtitleFile(
            segments=segments,
            style=self.config.style,
            format=self.config.format,
        )

    def to_ass(
        self,
        subtitle: SubtitleFile,
        output_path: Path,
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

        Returns:
            Path to generated ASS file
        """
        output_path = output_path.with_suffix(".ass")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        style = subtitle.style

        # Convert colors to ASS format (&HAABBGGRR)
        primary_color = self._hex_to_ass_color(style.primary_color)
        outline_color = self._hex_to_ass_color(style.outline_color)
        bg_color = self._hex_to_ass_color(
            style.background_color,
            opacity=style.background_opacity if style.background_enabled else 0.0,
        )
        highlight_color = self._hex_to_ass_color(self.config.highlight_color)

        # Build ASS content
        ass_content = f"""[Script Info]
Title: BSForge Generated Subtitles
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{style.font_name},{style.font_size},{primary_color},&H00000000,{outline_color},{bg_color},0,0,0,0,100,100,0,0,{3 if style.background_enabled else 1},{style.outline_width},{style.shadow_offset},{self._get_ass_alignment()},{self.config.margin_horizontal},{self.config.margin_horizontal},{self.config.margin_bottom},1
Style: Highlight,{style.font_name},{style.font_size},{highlight_color},&H00000000,{outline_color},{bg_color},1,0,0,0,100,100,0,0,{3 if style.background_enabled else 1},{style.outline_width},{style.shadow_offset},{self._get_ass_alignment()},{self.config.margin_horizontal},{self.config.margin_horizontal},{self.config.margin_bottom},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

        # Add dialogue lines
        for segment in subtitle.segments:
            start_time = self._seconds_to_ass_time(segment.start)
            end_time = self._seconds_to_ass_time(segment.end)

            # Apply karaoke highlighting if enabled and words available
            if self.config.highlight_current_word and segment.words:
                text = self._apply_karaoke_effect(segment)
            else:
                text = segment.text

            ass_content += f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{text}\n"

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(ass_content)

        logger.info(f"Generated ASS subtitle: {output_path}")
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

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(srt_content)

        logger.info(f"Generated SRT subtitle: {output_path}")
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
        # Remove # prefix
        hex_color = hex_color.lstrip("#")

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

        for word in segment.words:
            # Duration in centiseconds
            word_duration = (word.end - word.start) * 100  # centiseconds

            # Use \\k tag for karaoke timing
            parts.append(f"{{\\k{int(word_duration)}}}{word.word}")

        return "".join(parts)


__all__ = [
    "SubtitleGenerator",
    "SubtitleSegment",
    "SubtitleFile",
]
