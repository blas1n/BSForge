"""Remotion-based video compositor.

Replaces FFmpegCompositor for video rendering.
Calls Remotion CLI via subprocess to compose Korean Shorts videos.
Supports karaoke subtitles, Ken Burns, and rich text animations.
"""

import asyncio
import json
import os
import platform
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.config.video import CompositionConfig
from app.config.video_template import SafeZoneConfig, ThemeConfig, VisualEffectsConfig
from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.config.persona import PersonaStyleConfig
    from app.config.video_template import VideoTemplateConfig
    from app.models.scene import Scene
    from app.services.generator.subtitle import SubtitleFile
    from app.services.generator.tts.base import SceneTTSResult
    from app.services.generator.visual.manager import SceneVisualResult

logger = get_logger(__name__)


@dataclass
class CompositionResult:
    """Result of video composition.

    Attributes:
        video_path: Path to final video file
        duration_seconds: Video duration
        file_size_bytes: Video file size
        resolution: Video resolution string
        fps: Frames per second
    """

    video_path: Path
    duration_seconds: float
    file_size_bytes: int
    resolution: str
    fps: int


# Composition ID registered in remotion/src/Root.tsx
_COMPOSITION_ID = "KoreanShorts"


class RemotionCompositor:
    """Compose video using Remotion (React-based video generation).

    Replaces FFmpegCompositor with browser-quality rendering:
    - Crisp text and animations via CSS/React
    - TikTok-style karaoke subtitles
    - Rich transitions and effects

    Calls Remotion CLI via asyncio subprocess, keeping the pipeline fully async.

    Assets are staged into a unique subdirectory under the Remotion
    project's ``public/`` folder so that ``staticFile()`` can resolve
    them.  The subdirectory is cleaned up after rendering.
    """

    def __init__(
        self,
        config: CompositionConfig,
        remotion_dir: Path | None = None,
    ) -> None:
        """Initialize RemotionCompositor.

        Args:
            config: Video composition configuration
            remotion_dir: Path to the Remotion project directory
        """
        self.config = config
        self.remotion_dir = remotion_dir or Path("/workspace/remotion")

    async def compose_scenes(
        self,
        scenes: list["Scene"],
        scene_tts_results: list["SceneTTSResult"],
        scene_visuals: list["SceneVisualResult"],
        combined_audio_path: Path,
        subtitle_file: Path | None,
        output_path: Path,
        persona_style: "PersonaStyleConfig | None" = None,
        background_music_path: Path | None = None,
        headline: str | None = None,
        subtitle_data: "SubtitleFile | None" = None,
        video_template: "VideoTemplateConfig | None" = None,
        sfx_dir: Path | None = None,
    ) -> CompositionResult:
        """Compose video from scene-based components using Remotion.

        Args:
            scenes: List of Scene objects
            scene_tts_results: Per-scene TTS results (word timestamps)
            scene_visuals: Per-scene visual assets (local file paths)
            combined_audio_path: Path to merged TTS audio
            subtitle_file: Path to saved ASS/SRT file (used as fallback)
            output_path: Output video path (without extension)
            persona_style: Channel persona style config
            background_music_path: Optional BGM path
            headline: Headline string (split into 2 lines at newline)
            subtitle_data: SubtitleFile object with word timestamps for karaoke
            video_template: Video template config (provides safe_zone and theme)

        Returns:
            CompositionResult with path and metadata
        """
        output_mp4 = output_path.with_suffix(".mp4").resolve()
        output_mp4.parent.mkdir(parents=True, exist_ok=True)

        # Determine audio duration from TTS results
        total_duration = sum(r.duration_seconds for r in scene_tts_results)

        # Build accent color from persona style
        accent_color = "#FF69B4"  # default hot pink
        if persona_style:
            accent_color = persona_style.accent_color

        # Parse headline into two lines
        headline_line1, headline_line2 = self._parse_headline(headline or "")

        # Extract visual effects config from template
        vfx = (
            video_template.visual_effects
            if video_template and video_template.visual_effects
            else VisualEffectsConfig()
        )

        # Build visual assets list for props (with camera movement and per-scene transitions)
        visuals = self._build_visual_assets(scene_visuals, vfx, scenes)

        # Build subtitle segments list for props (with word timestamps if available)
        subtitle_anim = (
            video_template.subtitle.text_animation
            if video_template and video_template.subtitle
            else "fade_in"
        )
        subtitles = self._build_subtitles(subtitle_data, scene_tts_results, subtitle_anim)

        # BGM volume from config
        bgm_volume = self.config.background_music_volume

        # Stage assets into Remotion's public/ directory for staticFile() resolution.
        # Use a unique subdirectory per render to avoid collisions.
        render_id = f"_render_{os.getpid()}_{int(time.time())}"
        public_dir = self.remotion_dir / "public" / render_id
        public_dir.mkdir(parents=True, exist_ok=True)

        audio_rel = self._stage_asset(combined_audio_path, public_dir, "audio", render_id)
        bgm_rel = (
            self._stage_asset(background_music_path, public_dir, "bgm", render_id)
            if background_music_path
            else None
        )

        # Stage SFX files (whoosh, pop, ding) from sfx_dir
        sfx_paths_rel: dict[str, str] = {}
        _default_sfx_dir = Path("data/sfx")
        _sfx_source = (
            sfx_dir
            if sfx_dir and sfx_dir.exists()
            else (_default_sfx_dir if _default_sfx_dir.exists() else None)
        )
        if _sfx_source:
            for sfx_name in ("whoosh", "pop", "ding"):
                sfx_file = _sfx_source / f"{sfx_name}.mp3"
                if sfx_file.exists():
                    rel = self._stage_asset(sfx_file, public_dir, f"sfx_{sfx_name}", render_id)
                    sfx_paths_rel[sfx_name] = rel

        # Stage visual assets and rewrite paths to relative.
        # OffthreadVideo uses server-side FFmpeg, so no re-encoding needed.
        for v in visuals:
            src = Path(v["path"])
            staged = self._stage_asset(src, public_dir, f"visual_{v['start_time']:.1f}", render_id)
            v["path"] = staged

        # Build safe zone and theme from template config
        safe_zone_dict = self._build_safe_zone(video_template)
        theme_dict = self._build_theme(video_template, persona_style)

        # Resolve headline animation from template
        headline_animation = "fade_in"
        if (
            video_template
            and video_template.layout.headline
            and video_template.layout.headline.headline_animation
        ):
            headline_animation = video_template.layout.headline.headline_animation

        # Build scene metadata for Remotion (scene types, transitions, emphasis)
        scene_metadata = self._build_scene_metadata(scenes, scene_tts_results)

        # Build color grading dict from template VFX.
        # brightness in config is an offset (-0.5 to 0.5); CSS brightness() is a multiplier.
        color_grading = None
        if vfx.color_grading_enabled:
            color_grading = {
                "brightness": 1.0 + vfx.brightness,
                "contrast": vfx.contrast,
                "saturation": vfx.saturation,
                "warmth": vfx.warmth,
            }

        props: dict[str, Any] = {
            "duration_seconds": total_duration,
            "fps": self.config.fps,
            "width": self.config.width,
            "height": self.config.height,
            "audio_path": audio_rel,
            "bgm_path": bgm_rel,
            "bgm_volume": bgm_volume,
            "headline_line1": headline_line1,
            "headline_line2": headline_line2,
            "accent_color": accent_color,
            "headline_animation": headline_animation,
            "visuals": visuals,
            "subtitles": subtitles,
            "enable_ken_burns": vfx.ken_burns_enabled,
            "enable_karaoke": subtitle_data is not None,
            "headline_exit_after_seconds": 3.0,
            "safe_zone": safe_zone_dict,
            "theme": theme_dict,
            "color_grading": color_grading,
            "scenes": scene_metadata,
            "sfx_paths": sfx_paths_rel if sfx_paths_rel else None,
        }

        # Save props to a temp JSON file (avoids shell escaping issues).
        # Use absolute path because Remotion CLI runs with cwd=remotion/.
        props_path = (output_mp4.parent / "remotion_props.json").resolve()
        props_path.write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")

        try:
            result = await self._render(props_path, output_mp4, total_duration)
        finally:
            props_path.unlink(missing_ok=True)
            shutil.rmtree(public_dir, ignore_errors=True)

        return result

    @staticmethod
    def _stage_asset(src: Path, public_dir: Path, prefix: str, render_id: str) -> str:
        """Symlink or copy an asset into the public directory.

        Args:
            src: Source file path
            public_dir: Remotion public/<render_id>/ directory
            prefix: Filename prefix for the staged file
            render_id: Unique render subdirectory name

        Returns:
            Relative path usable by staticFile() (e.g. "_render_123/audio.wav")
        """
        if not src.exists():
            logger.warning("staging_file_missing", path=str(src))
            return ""

        dest_name = f"{prefix}{src.suffix}"
        dest = public_dir / dest_name

        if not dest.exists():
            shutil.copy2(src, dest)

        # staticFile() resolves from remotion/public/, so include subdirectory
        return f"{render_id}/{dest_name}"

    async def _render(
        self,
        props_path: Path,
        output_path: Path,
        total_duration: float,
    ) -> CompositionResult:
        """Invoke Remotion CLI to render the composition.

        Args:
            props_path: Path to JSON props file
            output_path: Output MP4 path
            total_duration: Expected duration (for logging)

        Returns:
            CompositionResult

        Raises:
            RuntimeError: If Remotion render fails
        """
        entry_point = self.remotion_dir / "src" / "index.ts"
        cmd = [
            "npx",
            "remotion",
            "render",
            str(entry_point),
            _COMPOSITION_ID,
            str(output_path),
            "--props",
            str(props_path),
            "--log",
            "error",  # suppress verbose output
            "--concurrency",
            "1",  # limit parallelism to prevent OOM
            "--video-bitrate",
            "8M",
        ]

        logger.info(
            f"Starting Remotion render: {_COMPOSITION_ID}, "
            f"duration={total_duration:.1f}s, output={output_path.name}"
        )
        start_time = time.time()

        # Chromium headless requires certain shared libraries; extend LD_LIBRARY_PATH
        env = os.environ.copy()
        arch = platform.machine()
        arch_dir = {"aarch64": "aarch64-linux-gnu", "x86_64": "x86_64-linux-gnu"}.get(
            arch, f"{arch}-linux-gnu"
        )
        chromium_libs = Path.home() / ".local/lib/chromium-deps/usr/lib" / arch_dir
        if chromium_libs.exists():
            env["LD_LIBRARY_PATH"] = f"{chromium_libs}:{env.get('LD_LIBRARY_PATH', '')}"

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(self.remotion_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await proc.communicate()

        elapsed = time.time() - start_time

        if proc.returncode != 0:
            stderr_text = stderr.decode("utf-8", errors="replace")
            logger.error(f"Remotion render failed (rc={proc.returncode}):\n{stderr_text}")
            raise RuntimeError(
                f"Remotion render failed with exit code {proc.returncode}: {stderr_text[:500]}"
            )

        if not output_path.exists():
            raise RuntimeError(
                f"Remotion render completed but output file not found: {output_path}"
            )

        file_size = output_path.stat().st_size
        logger.info(
            f"Remotion render complete: {output_path.name}, "
            f"duration={total_duration:.1f}s, size={file_size / 1024 / 1024:.1f}MB, "
            f"render_time={elapsed:.1f}s"
        )

        return CompositionResult(
            video_path=output_path,
            duration_seconds=total_duration,
            file_size_bytes=file_size,
            resolution=f"{self.config.width}x{self.config.height}",
            fps=self.config.fps,
        )

    @staticmethod
    def _build_safe_zone(
        video_template: "VideoTemplateConfig | None",
    ) -> dict[str, Any]:
        """Build safe zone dict for Remotion props.

        Args:
            video_template: Template config with safe zone settings

        Returns:
            Safe zone dict with pixel margins
        """
        sz = (
            video_template.layout.safe_zone
            if video_template and video_template.layout.safe_zone
            else SafeZoneConfig()
        )

        return {
            "top_px": sz.top_px,
            "bottom_px": sz.bottom_px,
            "left_px": sz.left_px,
            "right_px": sz.right_px,
        }

    @staticmethod
    def _build_theme(
        video_template: "VideoTemplateConfig | None",
        persona_style: "PersonaStyleConfig | None",
    ) -> dict[str, Any]:
        """Build theme dict for Remotion props.

        Merges template theme with persona style overrides.
        Persona accent_color takes precedence over template theme.

        Args:
            video_template: Template config with theme settings
            persona_style: Persona style (may override accent_color)

        Returns:
            Theme dict for Remotion components
        """
        t = video_template.theme if video_template and video_template.theme else ThemeConfig()

        theme = {
            "accent_color": t.accent_color,
            "secondary_color": t.secondary_color,
            "font_family": t.font_family,
            "headline_font_size_line1": t.headline_font_size_line1,
            "headline_font_size_line2": t.headline_font_size_line2,
            "subtitle_font_size": t.subtitle_font_size,
            "headline_bg_color": t.headline_bg_color,
            "headline_bg_opacity": t.headline_bg_opacity,
            "highlight_color": t.highlight_color,
            "text_color": t.text_color,
            "outline_color": t.outline_color,
        }

        # Persona accent_color overrides template theme
        if persona_style:
            theme["accent_color"] = persona_style.accent_color

        return theme

    def _parse_headline(self, headline: str) -> tuple[str, str]:
        """Split headline string into two display lines.

        Args:
            headline: Raw headline (newline-separated or single line)

        Returns:
            Tuple of (line1, line2)
        """
        if not headline:
            return "", ""

        lines = headline.strip().split("\n", 1)
        line1 = lines[0].strip() if lines else ""
        line2 = lines[1].strip() if len(lines) > 1 else ""
        return line1, line2

    def _build_visual_assets(
        self,
        scene_visuals: list["SceneVisualResult"],
        vfx: VisualEffectsConfig,
        scenes: list["Scene"] | None = None,
    ) -> list[dict[str, Any]]:
        """Convert SceneVisualResult list to Remotion props format.

        Uses per-scene transition types from Scene metadata when available,
        falling back to the global vfx.transition_type.

        Args:
            scene_visuals: Per-scene visual sourcing results
            vfx: Visual effects config (camera movement, transitions)
            scenes: Optional list of Scene objects for per-scene transitions

        Returns:
            List of visual asset dicts for KoreanShortsProps
        """
        import random

        assets = []
        current_time = 0.0
        options = vfx.camera_movement_options or [vfx.camera_movement]

        for idx, sv in enumerate(scene_visuals):
            asset = sv.asset
            if asset.path is None or not asset.path.exists():
                current_time += sv.duration
                continue

            # Assign camera movement
            camera = random.choice(options) if vfx.randomize_camera else vfx.camera_movement

            # Per-scene transitions from Scene metadata, fallback to vfx global
            scene = scenes[idx] if scenes and idx < len(scenes) else None
            if scene:
                t_in = scene.transition_in.value if idx > 0 else "none"
                t_out = scene.transition_out.value
            else:
                t_in = vfx.transition_type if idx > 0 else "none"
                t_out = vfx.transition_type

            assets.append(
                {
                    "path": str(asset.path),
                    "type": "video" if asset.is_video else "image",
                    "start_time": sv.start_offset,
                    "duration": sv.duration,
                    "camera_movement": camera,
                    "transition_in": t_in,
                    "transition_out": t_out,
                }
            )
            current_time += sv.duration

        return assets

    def _build_subtitles(
        self,
        subtitle_data: "SubtitleFile | None",
        scene_tts_results: list["SceneTTSResult"],
        text_animation: str = "fade_in",
    ) -> list[dict[str, Any]]:
        """Build subtitle segments list for Remotion props.

        Args:
            subtitle_data: SubtitleFile with word timestamps (for karaoke)
            scene_tts_results: TTS results (fallback if no subtitle_data)
            text_animation: Per-segment entrance animation type

        Returns:
            List of subtitle segment dicts for KoreanShortsProps
        """
        if subtitle_data is None:
            return []

        segments = []
        for seg in subtitle_data.segments:
            words_data = None
            if seg.words:
                words_data = [{"word": w.word, "start": w.start, "end": w.end} for w in seg.words]

            segments.append(
                {
                    "index": seg.index,
                    "start": seg.start,
                    "end": seg.end,
                    "text": self._strip_ass_tags(seg.text),
                    "words": words_data,
                    "text_animation": text_animation,
                }
            )

        return segments

    @staticmethod
    def _build_scene_metadata(
        scenes: list["Scene"],
        scene_tts_results: list["SceneTTSResult"],
    ) -> list[dict[str, Any]]:
        """Build per-scene metadata for Remotion props.

        Extracts scene_type, visual_style, transitions, and emphasis_words
        from each Scene and computes timing from TTS results.

        Args:
            scenes: List of Scene objects with metadata
            scene_tts_results: Per-scene TTS results for timing

        Returns:
            List of SceneInfo dicts for Remotion
        """
        metadata = []
        cumulative_time = 0.0

        for i, scene in enumerate(scenes):
            duration = scene_tts_results[i].duration_seconds if i < len(scene_tts_results) else 0.0

            metadata.append(
                {
                    "index": i,
                    "scene_type": scene.scene_type.value,
                    "visual_style": scene.inferred_visual_style.value,
                    "transition_in": scene.transition_in.value,
                    "transition_out": scene.transition_out.value,
                    "emphasis_words": scene.emphasis_words,
                    "start_time": cumulative_time,
                    "duration": duration,
                }
            )
            cumulative_time += duration

        return metadata

    @staticmethod
    def _strip_ass_tags(text: str) -> str:
        """Remove ASS override tags from text.

        SubtitleGenerator adds ASS inline tags (e.g. {\\c&H...&}) for
        emphasis styling.  Remotion handles styling via React/CSS, so
        these tags must be stripped before passing to props.

        Args:
            text: Text potentially containing ASS tags

        Returns:
            Plain text without ASS tags
        """
        return re.sub(r"\{\\[^}]*\}", "", text)
