"""Factory functions for service dependency creation.

Replaces the DI container with simple factory functions.
Each factory creates a fully-wired service instance.
"""

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.config.bgm import BGMConfig
from app.config.video import (
    TTSProviderConfig,
    VideoGenerationConfig,
    VisualConfig,
    WanConfig,
)
from app.core.config import get_config
from app.core.database import async_session_maker
from app.core.logging import get_logger
from app.core.template_loader import VideoTemplateLoader
from app.core.types import SessionFactory
from app.infrastructure.http_client import HTTPClient
from app.infrastructure.llm import LLMClient
from app.infrastructure.youtube_api import YouTubeAPIClient
from app.infrastructure.youtube_auth import YouTubeAuthClient
from app.prompts.manager import PromptManager
from app.services.collector.normalizer import TopicNormalizer
from app.services.collector.pipeline import TopicCollectionPipeline
from app.services.generator.bgm import BGMManager
from app.services.generator.ffmpeg import FFmpegWrapper
from app.services.generator.pipeline import VideoGenerationPipeline
from app.services.generator.remotion_compositor import RemotionCompositor
from app.services.generator.subtitle import SubtitleGenerator
from app.services.generator.templates import ASSTemplateLoader
from app.services.generator.tts.factory import TTSEngineFactory
from app.services.generator.visual.manager import VisualSourcingManager
from app.services.generator.visual.pexels import PexelsClient
from app.services.generator.visual.wan_video_source import WanVideoSource
from app.services.script_generator import ScriptGenerator
from app.services.uploader.pipeline import UploadPipeline
from app.services.uploader.youtube_uploader import YouTubeUploader

logger = get_logger(__name__)

# Singleton cache for shared resources
_http_client: HTTPClient | None = None
_llm_client: LLMClient | None = None
_prompt_manager: PromptManager | None = None


def get_session_factory() -> SessionFactory:
    """Get database session factory."""
    return async_session_maker


def create_http_client() -> HTTPClient:
    """Get or create shared HTTP client (singleton)."""
    global _http_client
    if _http_client is None:
        _http_client = HTTPClient()
    return _http_client


def create_llm_client() -> LLMClient:
    """Get or create LLM client with gateway config (singleton)."""
    global _llm_client
    if _llm_client is None:
        config = get_config()
        _llm_client = LLMClient(
            base_url=config.llm_api_base,
            api_key=config.llm_api_key,
            default_model=config.llm_model,
        )
    return _llm_client


def create_prompt_manager() -> PromptManager:
    """Get or create prompt manager (singleton)."""
    global _prompt_manager
    if _prompt_manager is None:
        _prompt_manager = PromptManager()
    return _prompt_manager


def create_script_generator(
    llm_client: LLMClient | None = None,
    prompt_manager: PromptManager | None = None,
) -> ScriptGenerator:
    """Create script generator service."""
    return ScriptGenerator(
        llm_client=llm_client or create_llm_client(),
        prompt_manager=prompt_manager or create_prompt_manager(),
    )


def create_normalizer(
    llm_client: LLMClient | None = None,
    prompt_manager: PromptManager | None = None,
) -> TopicNormalizer:
    """Create topic normalizer."""
    return TopicNormalizer(
        llm_client=llm_client or create_llm_client(),
        prompt_manager=prompt_manager or create_prompt_manager(),
    )


async def create_collector_pipeline(
    session: AsyncSession,
    http_client: HTTPClient | None = None,
    llm_client: LLMClient | None = None,
    prompt_manager: PromptManager | None = None,
) -> TopicCollectionPipeline:
    """Create topic collection pipeline.

    Args:
        session: Database session for this pipeline run
        http_client: Shared HTTP client (created if not provided)
        llm_client: LLM client (created if not provided)
        prompt_manager: Prompt manager (created if not provided)

    Returns:
        Configured TopicCollectionPipeline
    """
    _llm = llm_client or create_llm_client()
    _pm = prompt_manager or create_prompt_manager()
    normalizer = create_normalizer(llm_client=_llm, prompt_manager=_pm)

    return TopicCollectionPipeline(
        session=session,
        http_client=http_client or create_http_client(),
        normalizer=normalizer,
    )


def create_ffmpeg_wrapper() -> FFmpegWrapper:
    """Create FFmpeg wrapper."""
    return FFmpegWrapper()


def create_tts_factory(
    ffmpeg_wrapper: FFmpegWrapper | None = None,
) -> TTSEngineFactory:
    """Create TTS engine factory."""
    config = get_config()
    return TTSEngineFactory(
        ffmpeg_wrapper=ffmpeg_wrapper or create_ffmpeg_wrapper(),
        config=TTSProviderConfig(),
        elevenlabs_api_key=config.elevenlabs_api_key,
    )


def create_visual_manager(
    http_client: HTTPClient | None = None,
) -> VisualSourcingManager:
    """Create visual sourcing manager."""
    config = get_config()
    _http = http_client or create_http_client()

    pexels_client = PexelsClient(api_key=config.pexels_api_key)
    wan_source = WanVideoSource(http_client=_http, config=WanConfig())

    return VisualSourcingManager(
        http_client=_http,
        config=VisualConfig(),
        pexels_client=pexels_client,
        wan_video_source=wan_source,
    )


def create_subtitle_generator() -> SubtitleGenerator:
    """Create subtitle generator."""
    from app.config.video import CompositionConfig, SubtitleConfig

    return SubtitleGenerator(
        config=SubtitleConfig(),
        composition_config=CompositionConfig(),
        template_loader=ASSTemplateLoader(),
    )


def create_remotion_compositor() -> RemotionCompositor:
    """Create Remotion compositor."""
    from app.config.video import CompositionConfig

    return RemotionCompositor(config=CompositionConfig())


def create_bgm_manager() -> BGMManager:
    """Create BGM manager."""
    return BGMManager(config=BGMConfig())


def create_video_pipeline(
    http_client: HTTPClient | None = None,
    ffmpeg_wrapper: FFmpegWrapper | None = None,
) -> VideoGenerationPipeline:
    """Create video generation pipeline with all dependencies.

    Args:
        http_client: Shared HTTP client (created if not provided)
        ffmpeg_wrapper: FFmpeg wrapper (created if not provided)

    Returns:
        Configured VideoGenerationPipeline
    """
    _ffmpeg = ffmpeg_wrapper or create_ffmpeg_wrapper()

    return VideoGenerationPipeline(
        tts_factory=create_tts_factory(ffmpeg_wrapper=_ffmpeg),
        visual_manager=create_visual_manager(http_client=http_client),
        subtitle_generator=create_subtitle_generator(),
        compositor=create_remotion_compositor(),
        ffmpeg_wrapper=_ffmpeg,
        db_session_factory=get_session_factory(),
        config=VideoGenerationConfig(),
        template_loader=VideoTemplateLoader(),
        bgm_manager=create_bgm_manager(),
    )


def create_youtube_auth() -> YouTubeAuthClient:
    """Create YouTube auth client."""
    config = get_config()
    return YouTubeAuthClient(
        credentials_path=Path(config.youtube_credentials_path),
        token_path=Path(config.youtube_token_path),
    )


def create_youtube_uploader(
    youtube_auth: YouTubeAuthClient | None = None,
) -> YouTubeUploader:
    """Create YouTube uploader service."""
    auth = youtube_auth or create_youtube_auth()
    youtube_api = YouTubeAPIClient(auth_client=auth)

    return YouTubeUploader(
        youtube_api=youtube_api,
        db_session_factory=get_session_factory(),
    )


def create_upload_pipeline(
    youtube_auth: YouTubeAuthClient | None = None,
) -> UploadPipeline:
    """Create upload pipeline.

    Args:
        youtube_auth: YouTube auth client (created if not provided)

    Returns:
        Configured UploadPipeline
    """
    uploader = create_youtube_uploader(youtube_auth=youtube_auth)

    return UploadPipeline(
        uploader=uploader,
        db_session_factory=get_session_factory(),
    )


async def close_singletons() -> None:
    """Close and reset all singleton instances.

    Ensures HTTPClient is properly closed before clearing references.
    Use this for production shutdown to avoid resource leaks.
    """
    global _http_client, _llm_client, _prompt_manager
    if _http_client is not None:
        await _http_client.close()
    _http_client = None
    _llm_client = None
    _prompt_manager = None


def reset_singletons() -> None:
    """Reset all singleton instances without closing. For testing only."""
    global _http_client, _llm_client, _prompt_manager
    _http_client = None
    _llm_client = None
    _prompt_manager = None


__all__ = [
    "create_bgm_manager",
    "create_collector_pipeline",
    "create_ffmpeg_wrapper",
    "create_http_client",
    "create_llm_client",
    "create_normalizer",
    "create_prompt_manager",
    "create_remotion_compositor",
    "create_script_generator",
    "create_subtitle_generator",
    "create_tts_factory",
    "create_upload_pipeline",
    "create_video_pipeline",
    "create_visual_manager",
    "create_youtube_auth",
    "create_youtube_uploader",
    "get_session_factory",
    "close_singletons",
    "reset_singletons",
]
