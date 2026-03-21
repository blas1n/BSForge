"""Video generation configuration models.

This module provides typed Pydantic configuration for all video generation components:
- TTS (Text-to-Speech)
- Subtitles
- Visual sourcing
- Video composition
- Thumbnail generation
"""

from typing import Literal

from pydantic import BaseModel, Field


class TTSProviderConfig(BaseModel):
    """TTS provider configuration.

    This configures the TTS service provider and default voices.
    For synthesis parameters (speed, pitch, volume), see TTSSynthesisConfig
    in app/services/generator/tts/base.py.

    Attributes:
        provider: TTS service provider
        default_voice_ko_male: Default Korean male voice ID
        default_voice_ko_female: Default Korean female voice ID
        default_voice_en: Default English voice ID
        speed: Default speech rate (1.0 = normal)
        pitch: Default pitch adjustment in Hz (0 = no change)
        volume: Default volume adjustment (0 = no change)
    """

    provider: Literal["edge-tts", "elevenlabs"] = Field(
        default="edge-tts", description="TTS provider"
    )
    default_voice_ko_male: str = Field(
        default="ko-KR-InJoonNeural", description="Default Korean male voice"
    )
    default_voice_ko_female: str = Field(
        default="ko-KR-SunHiNeural", description="Default Korean female voice"
    )
    default_voice_en: str = Field(default="en-US-AriaNeural", description="Default English voice")
    speed: float = Field(default=1.0, ge=0.5, le=2.0, description="Speech rate multiplier")
    pitch: int = Field(default=0, ge=-50, le=50, description="Pitch adjustment in Hz")
    volume: int = Field(default=0, ge=-50, le=50, description="Volume adjustment")


class SubtitleStyleConfig(BaseModel):
    """Subtitle styling configuration.

    Attributes:
        font_name: Font family name
        font_size: Font size in pixels
        primary_color: Primary text color (hex)
        outline_color: Outline color (hex)
        outline_width: Outline thickness
        shadow_color: Shadow color (hex)
        shadow_offset: Shadow offset in pixels
        background_enabled: Enable background box
        background_color: Background color (hex)
        background_opacity: Background opacity (0-1)
    """

    font_name: str = Field(default="Pretendard", description="Font family")
    font_size: int = Field(default=48, ge=12, le=96, description="Font size")
    primary_color: str = Field(default="#FFFFFF", description="Text color")
    outline_color: str = Field(default="#000000", description="Outline color")
    outline_width: int = Field(default=2, ge=0, le=10, description="Outline width")
    shadow_color: str = Field(default="#000000", description="Shadow color")
    shadow_offset: int = Field(default=2, ge=0, le=10, description="Shadow offset")
    background_enabled: bool = Field(default=True, description="Enable background")
    background_color: str = Field(default="#000000", description="Background color")
    background_opacity: float = Field(default=0.7, ge=0.0, le=1.0, description="Background opacity")


class SubtitleConfig(BaseModel):
    """Subtitle generation configuration.

    Attributes:
        enabled: Enable subtitle generation
        format: Subtitle file format
        position: Vertical position
        margin_bottom: Bottom margin in pixels
        margin_horizontal: Horizontal margin in pixels
        max_chars_per_line: Maximum characters per line
        max_lines: Maximum visible lines
        highlight_current_word: Highlight current word (karaoke style)
        highlight_color: Highlight color (hex)
        style: Subtitle styling configuration
    """

    enabled: bool = Field(default=True, description="Enable subtitles")
    format: Literal["ass", "srt"] = Field(default="ass", description="Subtitle format")
    position: Literal["bottom", "center", "top"] = Field(
        default="bottom", description="Vertical position"
    )
    margin_bottom: int = Field(default=50, ge=0, le=200, description="Bottom margin")
    margin_horizontal: int = Field(default=30, ge=0, le=100, description="Side margins")
    max_chars_per_line: int = Field(default=20, ge=10, le=50, description="Max chars per line")
    max_lines: int = Field(default=2, ge=1, le=4, description="Max visible lines")
    highlight_current_word: bool = Field(default=True, description="Karaoke highlighting")
    highlight_color: str = Field(default="#FFFF00", description="Highlight color")
    style: SubtitleStyleConfig = Field(default_factory=SubtitleStyleConfig)


class VisualSourceConfig(BaseModel):
    """Visual source specific configuration.

    Attributes:
        api_key_env: Environment variable name for API key
        orientation: Preferred orientation
        min_duration: Minimum video duration in seconds
        max_results: Maximum search results
        quality: Preferred quality level
    """

    api_key_env: str = Field(default="PEXELS_API_KEY", description="API key env var")
    orientation: Literal["portrait", "landscape", "square"] = Field(
        default="portrait", description="Video orientation"
    )
    min_duration: int = Field(default=5, ge=1, le=30, description="Min video duration")
    max_results: int = Field(default=10, ge=1, le=50, description="Max search results")
    quality: Literal["low", "medium", "high", "hd"] = Field(
        default="hd", description="Quality preference"
    )


class PixabayConfig(BaseModel):
    """Pixabay API configuration.

    Pixabay provides free stock videos and images without attribution requirement.

    Attributes:
        api_key_env: Environment variable name for API key
        orientation: Preferred orientation
        min_duration: Minimum video duration in seconds
        max_results: Maximum search results
        image_type: Type of images to search
    """

    api_key_env: str = Field(default="PIXABAY_API_KEY", description="API key env var")
    orientation: Literal["portrait", "landscape", "square"] = Field(
        default="portrait", description="Preferred orientation"
    )
    min_duration: int = Field(default=5, ge=1, le=60, description="Min video duration")
    max_results: int = Field(default=10, ge=1, le=50, description="Max search results")
    image_type: Literal["all", "photo", "illustration", "vector"] = Field(
        default="photo", description="Image type filter"
    )


class WanConfig(BaseModel):
    """Wan 2.2 text-to-video generation configuration.

    Wan runs as a separate Docker service and communicates via HTTP API.
    Supports CUDA (NVIDIA) and CPU fallback.

    Attributes:
        service_url: Wan service HTTP endpoint
        enabled: Whether to use Wan for video generation
        timeout: Request timeout in seconds (longer than SD, video takes more time)
        model_id: HuggingFace model ID to load
        default_duration_seconds: Default video clip duration
        default_fps: Default frames per second
        base_width: Generation width (portrait: width < height)
        base_height: Generation height (portrait: height > width)
        wan_version: Model version for future A/B testing (2.2=local, 2.6=API)
        enable_lipsync: Enable Wan 2.6 lip-sync (requires wan_version="2.6")
    """

    service_url: str = Field(default="http://wan:7861", description="Wan service URL")
    enabled: bool = Field(default=True, description="Enable Wan generation")
    timeout: float = Field(default=300.0, ge=30.0, le=900.0, description="Request timeout")
    model_id: str = Field(default="Wan-AI/Wan2.2-T2V-1.3B", description="HuggingFace model ID")
    default_duration_seconds: float = Field(
        default=5.0, ge=2.0, le=10.0, description="Default clip duration"
    )
    default_fps: int = Field(default=16, ge=8, le=30, description="Default FPS")
    base_width: int = Field(default=480, ge=256, le=1280, description="Generation width")
    base_height: int = Field(default=832, ge=256, le=1280, description="Generation height")
    # A/B testing flags (wan_version="2.6" uses fal.ai API instead of local service)
    wan_version: Literal["2.2", "2.6"] = Field(
        default="2.2", description="Wan version: 2.2=local, 2.6=fal.ai API"
    )
    enable_lipsync: bool = Field(
        default=False, description="Enable Wan 2.6 lip-sync (wan_version=2.6 only)"
    )


class VisualConfig(BaseModel):
    """Visual sourcing configuration.

    Attributes:
        source_priority: Priority order for visual sources
        pexels: Pexels video/image configuration
        pixabay: Pixabay video/image configuration
        wan: Wan 2.2 video generation configuration
        fallback_color: Fallback solid color (hex)
        fallback_gradient: Fallback gradient colors
        cache_enabled: Enable visual caching
        cache_ttl_hours: Cache TTL in hours
        metadata_score_threshold: Minimum metadata matching score
    """

    source_priority: list[str] = Field(
        default=[
            "tavily_image",  # Tavily web image search (celebrities, real people)
            "pexels_video",  # Pexels videos
            "pixabay_video",  # Pixabay videos
            "pexels_image",  # Pexels images
            "pixabay_image",  # Pixabay images
            "wan_video",  # Wan 2.2 AI video generation (local, free)
            "solid_color",  # Fallback
        ],
        description="Source priority order",
    )
    tavily_image_enabled: bool = Field(
        default=True, description="Enable Tavily for web image search"
    )
    pexels: VisualSourceConfig = Field(default_factory=VisualSourceConfig)
    pixabay: PixabayConfig = Field(default_factory=PixabayConfig)
    wan: WanConfig = Field(default_factory=WanConfig)
    fallback_color: str = Field(default="#1a1a2e", description="Fallback solid color")
    fallback_gradient: list[str] = Field(
        default=["#1a1a2e", "#16213e"], description="Fallback gradient colors"
    )
    cache_enabled: bool = Field(default=True, description="Enable caching")
    cache_ttl_hours: int = Field(default=24, ge=1, le=168, description="Cache TTL")
    metadata_score_threshold: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Minimum metadata matching score (title/tags). Below this, skip asset.",
    )
    reuse_previous_visual_types: list[str] = Field(
        default=["cta"],
        description="Scene types that reuse previous visual instead of sourcing new one. "
        "Use lowercase scene type names: hook, content, commentary, cta, etc.",
    )


class CompositionConfig(BaseModel):
    """Video composition configuration.

    Attributes:
        width: Output video width
        height: Output video height
        fps: Frames per second
        video_codec: Video codec
        audio_codec: Audio codec
        video_bitrate: Video bitrate
        audio_bitrate: Audio bitrate
        crf: Constant Rate Factor (quality, lower = better)
        preset: Encoding preset (speed vs compression)
        pixel_format: Pixel format
        transition_type: Transition between clips
        transition_duration: Transition duration in seconds
        background_music_volume: Background music volume (0-1)
    """

    width: int = Field(default=1080, ge=480, le=3840, description="Video width")
    height: int = Field(default=1920, ge=480, le=3840, description="Video height")
    fps: int = Field(default=30, ge=24, le=60, description="Frame rate")
    video_codec: str = Field(default="libx264", description="Video codec")
    audio_codec: str = Field(default="aac", description="Audio codec")
    video_bitrate: str = Field(default="5000k", description="Video bitrate")
    audio_bitrate: str = Field(default="192k", description="Audio bitrate")
    crf: int = Field(default=18, ge=0, le=51, description="Quality (0-51, lower=better)")
    preset: Literal[
        "ultrafast",
        "superfast",
        "veryfast",
        "faster",
        "fast",
        "medium",
        "slow",
        "slower",
        "veryslow",
    ] = Field(default="medium", description="Encoding preset")
    pixel_format: str = Field(default="yuv420p", description="Pixel format")
    transition_type: Literal["none", "fade", "crossfade"] = Field(
        default="fade", description="Clip transition"
    )
    transition_duration: float = Field(
        default=0.5, ge=0.0, le=2.0, description="Transition duration"
    )
    background_music_volume: float = Field(
        default=0.1, ge=0.0, le=1.0, description="Background music volume"
    )


class ThumbnailConfig(BaseModel):
    """Thumbnail generation configuration.

    Default values are optimized for YouTube Shorts (1080x1920 portrait).

    Attributes:
        width: Thumbnail width (default: 1080 for Shorts)
        height: Thumbnail height (default: 1920 for Shorts)
        title_font: Title font name
        title_size: Title font size
        title_color: Title text color (hex)
        title_stroke_color: Title stroke color (hex)
        title_stroke_width: Title stroke width
        overlay_color: Background overlay color (hex)
        overlay_opacity: Overlay opacity (0-1)
        text_position: Text position
        padding: Padding from edges
        max_title_lines: Maximum title lines
        quality: JPEG quality (1-100)
    """

    width: int = Field(default=1080, description="Thumbnail width (Shorts: 1080)")
    height: int = Field(default=1920, description="Thumbnail height (Shorts: 1920)")
    title_font: str = Field(default="Noto Sans CJK KR", description="Title font")
    title_size: int = Field(default=90, ge=24, le=200, description="Title size")
    title_color: str = Field(default="#FFFFFF", description="Title color")
    title_stroke_color: str = Field(default="#000000", description="Stroke color")
    title_stroke_width: int = Field(default=5, ge=0, le=15, description="Stroke width")
    overlay_color: str = Field(default="#000000", description="Overlay color")
    overlay_opacity: float = Field(default=0.3, ge=0.0, le=1.0, description="Overlay opacity")
    text_position: Literal["center", "bottom"] = Field(
        default="center", description="Text position"
    )
    padding: int = Field(default=60, ge=0, le=150, description="Edge padding")
    max_title_lines: int = Field(default=4, ge=1, le=6, description="Max title lines")
    quality: int = Field(default=95, ge=1, le=100, description="JPEG quality")


class VideoGenerationConfig(BaseModel):
    """Complete video generation configuration.

    All sub-configs have defaults and can be used without explicit configuration.

    Attributes:
        tts: Text-to-Speech configuration
        subtitle: Subtitle configuration
        visual: Visual sourcing configuration
        composition: Video composition configuration
        thumbnail: Thumbnail configuration
        output_dir: Output directory for generated videos
        temp_dir: Temporary directory for processing
        cleanup_temp: Whether to cleanup temp files after generation
        max_retries: Maximum retry attempts on failure
        timeout_seconds: Generation timeout in seconds
    """

    tts: TTSProviderConfig = Field(default_factory=TTSProviderConfig)
    subtitle: SubtitleConfig = Field(default_factory=SubtitleConfig)
    visual: VisualConfig = Field(default_factory=VisualConfig)
    composition: CompositionConfig = Field(default_factory=CompositionConfig)
    thumbnail: ThumbnailConfig = Field(default_factory=ThumbnailConfig)
    output_dir: str = Field(default="./outputs/videos", description="Output directory")
    temp_dir: str = Field(default="/tmp/bsforge", description="Temp directory")
    cleanup_temp: bool = Field(default=True, description="Cleanup temp files")
    max_retries: int = Field(default=3, ge=0, le=10, description="Max retries")
    timeout_seconds: int = Field(default=3600, ge=60, le=86400, description="Generation timeout")


__all__ = [
    "VideoGenerationConfig",
    "TTSProviderConfig",
    "SubtitleConfig",
    "SubtitleStyleConfig",
    "VisualConfig",
    "VisualSourceConfig",
    "PixabayConfig",
    "WanConfig",
    "CompositionConfig",
    "ThumbnailConfig",
]
