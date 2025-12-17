"""TTS utility functions.

This module provides utility functions for TTS processing,
including audio concatenation for scene-based generation.

All FFmpeg operations use the ffmpeg-python SDK via FFmpegWrapper.
"""

from pathlib import Path

from app.core.logging import get_logger
from app.services.generator.ffmpeg import FFmpegWrapper, get_ffmpeg_wrapper
from app.services.generator.tts.base import SceneTTSResult, TTSResult, WordTimestamp

logger = get_logger(__name__)


async def concatenate_scene_audio(
    scene_results: list[SceneTTSResult],
    output_path: Path,
    gap_duration: float = 0.0,
    ffmpeg_wrapper: FFmpegWrapper | None = None,
) -> TTSResult:
    """Concatenate scene audio files into a single audio file.

    Uses FFmpeg SDK to concatenate individual scene audio files
    while preserving word timestamps with offset adjustment.

    Args:
        scene_results: List of SceneTTSResult from synthesize_scenes()
        output_path: Output file path (without extension)
        gap_duration: Optional gap between scenes in seconds (default 0)
        ffmpeg_wrapper: Optional FFmpegWrapper instance

    Returns:
        Combined TTSResult with merged audio and adjusted timestamps
    """
    if not scene_results:
        raise ValueError("No scene results to concatenate")

    ffmpeg = ffmpeg_wrapper or get_ffmpeg_wrapper()
    output_path = output_path.with_suffix(".mp3")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Create concat file for FFmpeg
    concat_file = output_path.parent / f"{output_path.stem}_concat_list.txt"

    try:
        with open(concat_file, "w", encoding="utf-8") as f:
            for result in scene_results:
                # Escape single quotes in path
                escaped_path = str(result.audio_path).replace("'", "'\\''")
                f.write(f"file '{escaped_path}'\n")

        logger.info(f"Concatenating {len(scene_results)} scene audio files")

        # Concatenate with FFmpeg SDK
        stream = ffmpeg.concat_audio_files(
            concat_file_path=concat_file,
            output_path=output_path,
        )
        await ffmpeg.run(stream)

        # Merge word timestamps with offset adjustment
        all_timestamps: list[WordTimestamp] = []
        current_offset = 0.0

        for result in scene_results:
            if result.word_timestamps:
                for wt in result.word_timestamps:
                    all_timestamps.append(
                        WordTimestamp(
                            word=wt.word,
                            start=wt.start + current_offset,
                            end=wt.end + current_offset,
                        )
                    )
            current_offset += result.duration_seconds + gap_duration

        # Calculate total duration
        total_duration = sum(r.duration_seconds for r in scene_results)
        if gap_duration > 0:
            total_duration += gap_duration * (len(scene_results) - 1)

        logger.info(
            f"Concatenated audio: {total_duration:.2f}s, " f"{len(all_timestamps)} word timestamps"
        )

        return TTSResult(
            audio_path=output_path,
            duration_seconds=total_duration,
            word_timestamps=all_timestamps if all_timestamps else None,
        )

    finally:
        # Cleanup concat file
        if concat_file.exists():
            concat_file.unlink()


async def get_audio_duration_ffprobe(
    audio_path: Path,
    ffmpeg_wrapper: FFmpegWrapper | None = None,
) -> float:
    """Get audio duration using FFmpeg SDK probe.

    Args:
        audio_path: Path to audio file
        ffmpeg_wrapper: Optional FFmpegWrapper instance

    Returns:
        Duration in seconds
    """
    ffmpeg = ffmpeg_wrapper or get_ffmpeg_wrapper()
    return await ffmpeg.get_duration(audio_path)


def adjust_scene_offsets(
    scene_results: list[SceneTTSResult],
    gap_duration: float = 0.0,
) -> None:
    """Adjust start_offset for each scene result in place.

    This is useful when scene results were created without offset
    calculation (e.g., parallel synthesis).

    Args:
        scene_results: List of SceneTTSResult to adjust
        gap_duration: Gap between scenes in seconds
    """
    current_offset = 0.0
    for result in scene_results:
        result.start_offset = current_offset
        current_offset += result.duration_seconds + gap_duration


__all__ = [
    "concatenate_scene_audio",
    "get_audio_duration_ffprobe",
    "adjust_scene_offsets",
]
