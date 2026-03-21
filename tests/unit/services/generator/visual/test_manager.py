"""Unit tests for VisualSourcingManager."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config.video import VisualConfig
from app.models.scene import Scene, SceneType
from app.services.generator.tts.base import SceneTTSResult
from app.services.generator.visual.base import VisualAsset, VisualSourceType
from app.services.generator.visual.manager import SceneVisualResult, VisualSourcingManager


def _make_scene(
    scene_type: SceneType = SceneType.CONTENT,
    visual_keyword: str | None = "nature landscape",
    text: str = "Test scene text for display",
) -> Scene:
    """Create a Scene for testing."""
    return Scene(scene_type=scene_type, text=text, visual_keyword=visual_keyword)


def _make_tts_result(
    index: int = 0,
    duration: float = 5.0,
    start_offset: float = 0.0,
) -> SceneTTSResult:
    """Create a SceneTTSResult for testing."""
    return SceneTTSResult(
        scene_index=index,
        scene_type="content",
        audio_path=Path(f"/tmp/scene_{index:03d}.mp3"),
        duration_seconds=duration,
        start_offset=start_offset,
    )


def _make_asset(
    source: str = "pexels",
    source_id: str = "12345",
    asset_type: VisualSourceType = VisualSourceType.STOCK_IMAGE,
    url: str = "https://pexels.com/photo/12345.jpg",
    path: Path | None = None,
    metadata_score: float = 0.8,
    width: int = 1080,
    height: int = 1920,
) -> VisualAsset:
    """Create a VisualAsset for testing."""
    return VisualAsset(
        type=asset_type,
        source=source,
        source_id=source_id,
        url=url,
        path=path or Path("/tmp/downloaded.jpg"),
        duration=5.0,
        width=width,
        height=height,
        license="pexels",
        keywords=["nature"],
        metadata_score=metadata_score,
    )


@pytest.fixture
def mock_pexels() -> MagicMock:
    """Create a mock PexelsClient."""
    pexels = MagicMock()
    pexels.search_images = AsyncMock(return_value=[])
    pexels.search_videos = AsyncMock(return_value=[])
    pexels.download = AsyncMock(side_effect=lambda asset, _dir: asset)
    pexels.close = AsyncMock()
    return pexels


@pytest.fixture
def mock_wan() -> MagicMock:
    """Create a mock WanVideoSource."""
    wan = MagicMock()
    wan.is_available = AsyncMock(return_value=False)
    wan.generate = AsyncMock(return_value=[])
    wan.download = AsyncMock(side_effect=lambda asset, _dir: asset)
    wan.close = AsyncMock()
    wan.default_duration = 5.0
    return wan


@pytest.fixture
def mock_http_client() -> MagicMock:
    """Create a mock HTTPClient."""
    return MagicMock()


@pytest.fixture
def config() -> VisualConfig:
    """Create a default VisualConfig."""
    return VisualConfig()


@pytest.fixture
def manager(
    mock_http_client: MagicMock,
    config: VisualConfig,
    mock_pexels: MagicMock,
    mock_wan: MagicMock,
) -> VisualSourcingManager:
    """Create a VisualSourcingManager with mocked dependencies."""
    return VisualSourcingManager(
        http_client=mock_http_client,
        config=config,
        pexels_client=mock_pexels,
        wan_video_source=mock_wan,
    )


class TestSourceVisualsForScenes:
    """Tests for source_visuals_for_scenes orchestration."""

    @pytest.mark.asyncio
    async def test_successful_pexels_sourcing(
        self, manager: VisualSourcingManager, mock_pexels: MagicMock, tmp_path: Path
    ) -> None:
        """Pexels image found -> returns SceneVisualResult with correct fields."""
        asset = _make_asset()
        mock_pexels.search_images.return_value = [asset]

        scenes = [_make_scene()]
        tts_results = [_make_tts_result(duration=4.0, start_offset=0.0)]

        results = await manager.source_visuals_for_scenes(scenes, tts_results, tmp_path)

        assert len(results) == 1
        result = results[0]
        assert isinstance(result, SceneVisualResult)
        assert result.scene_index == 0
        assert result.scene_type == "content"
        assert result.duration == 4.0
        assert result.start_offset == 0.0
        assert result.asset.source == "pexels"

    @pytest.mark.asyncio
    async def test_falls_back_to_wan_when_pexels_fails(
        self,
        manager: VisualSourcingManager,
        mock_pexels: MagicMock,
        mock_wan: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Pexels returns nothing -> Wan generates video."""
        mock_pexels.search_images.return_value = []
        mock_pexels.search_videos.return_value = []

        wan_asset = _make_asset(
            source="wan",
            source_id="wan_001",
            asset_type=VisualSourceType.AI_VIDEO,
            url="https://wan.ai/video.mp4",
        )
        mock_wan.is_available.return_value = True
        mock_wan.generate.return_value = [wan_asset]

        scenes = [_make_scene()]
        tts_results = [_make_tts_result()]

        results = await manager.source_visuals_for_scenes(scenes, tts_results, tmp_path)

        assert len(results) == 1
        assert results[0].asset.source == "wan"
        mock_wan.is_available.assert_awaited_once()
        mock_wan.generate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_falls_back_to_solid_color_when_all_fail(
        self,
        manager: VisualSourcingManager,
        mock_pexels: MagicMock,
        mock_wan: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Pexels and Wan both fail -> solid color fallback created."""
        mock_pexels.search_images.side_effect = RuntimeError("API down")
        mock_pexels.search_videos.side_effect = RuntimeError("API down")
        mock_wan.is_available.return_value = False

        scenes = [_make_scene()]
        tts_results = [_make_tts_result(duration=3.0)]

        results = await manager.source_visuals_for_scenes(scenes, tts_results, tmp_path)

        assert len(results) == 1
        assert results[0].asset.type == VisualSourceType.SOLID_COLOR
        assert results[0].asset.source == "fallback"
        assert results[0].duration == 3.0

    @pytest.mark.asyncio
    async def test_cta_reuses_previous_asset(
        self,
        manager: VisualSourcingManager,
        mock_pexels: MagicMock,
        tmp_path: Path,
    ) -> None:
        """CTA scene reuses the previous scene's visual asset."""
        asset = _make_asset()
        mock_pexels.search_images.return_value = [asset]

        scenes = [
            _make_scene(scene_type=SceneType.CONTENT),
            _make_scene(scene_type=SceneType.CTA, visual_keyword="subscribe"),
        ]
        tts_results = [
            _make_tts_result(index=0, duration=5.0, start_offset=0.0),
            _make_tts_result(index=1, duration=2.0, start_offset=5.0),
        ]

        results = await manager.source_visuals_for_scenes(scenes, tts_results, tmp_path)

        assert len(results) == 2
        # CTA reuses previous asset
        assert results[1].asset.source == results[0].asset.source
        assert results[1].asset.source_id == results[0].asset.source_id
        # But duration should match CTA's own duration
        assert results[1].duration == 2.0
        assert results[1].start_offset == 5.0
        # search_images called only once (for the content scene)
        assert mock_pexels.search_images.call_count == 1

    @pytest.mark.asyncio
    async def test_cta_as_first_scene_sources_normally(
        self,
        manager: VisualSourcingManager,
        mock_pexels: MagicMock,
        tmp_path: Path,
    ) -> None:
        """CTA as first scene has no previous -> sources normally."""
        asset = _make_asset()
        mock_pexels.search_images.return_value = [asset]

        scenes = [_make_scene(scene_type=SceneType.CTA)]
        tts_results = [_make_tts_result(duration=2.5)]

        results = await manager.source_visuals_for_scenes(scenes, tts_results, tmp_path)

        assert len(results) == 1
        assert results[0].asset.source == "pexels"
        mock_pexels.search_images.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_scene_tts_count_mismatch_processes_available_pairs(
        self,
        manager: VisualSourcingManager,
        mock_pexels: MagicMock,
        tmp_path: Path,
    ) -> None:
        """More scenes than TTS results -> only processes matching pairs."""
        asset = _make_asset()
        mock_pexels.search_images.return_value = [asset]

        scenes = [
            _make_scene(scene_type=SceneType.HOOK),
            _make_scene(scene_type=SceneType.CONTENT),
            _make_scene(scene_type=SceneType.CTA),
        ]
        tts_results = [
            _make_tts_result(index=0, duration=3.0),
            _make_tts_result(index=1, duration=5.0),
        ]

        results = await manager.source_visuals_for_scenes(scenes, tts_results, tmp_path)

        # Only 2 results because zip(strict=False) stops at shorter list
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_asset_deduplication_skips_same_source_id(
        self,
        manager: VisualSourcingManager,
        mock_pexels: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Second scene skips asset with same (source, source_id) as first."""
        asset_a = _make_asset(source_id="AAA", metadata_score=0.9)
        asset_b = _make_asset(source_id="BBB", metadata_score=0.7)

        # Both scenes return same assets, but second time AAA is excluded by dedup
        mock_pexels.search_images.return_value = [asset_a, asset_b]

        scenes = [_make_scene(), _make_scene(visual_keyword="city")]
        tts_results = [
            _make_tts_result(index=0, duration=5.0, start_offset=0.0),
            _make_tts_result(index=1, duration=4.0, start_offset=5.0),
        ]

        results = await manager.source_visuals_for_scenes(scenes, tts_results, tmp_path)

        assert len(results) == 2
        assert results[0].asset.source_id == "AAA"
        assert results[1].asset.source_id == "BBB"

    @pytest.mark.asyncio
    async def test_empty_scenes_returns_empty(
        self, manager: VisualSourcingManager, tmp_path: Path
    ) -> None:
        """Empty scenes list returns empty results."""
        results = await manager.source_visuals_for_scenes([], [], tmp_path)
        assert results == []

    @pytest.mark.asyncio
    async def test_multiple_scenes_correct_offsets_and_durations(
        self,
        manager: VisualSourcingManager,
        mock_pexels: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Multiple scenes carry through correct start_offset and duration."""
        assets = [_make_asset(source_id=f"img_{i}", metadata_score=0.9) for i in range(3)]
        # Return different asset each call
        mock_pexels.search_images.side_effect = [
            [assets[0]],
            [assets[1]],
            [assets[2]],
        ]

        scenes = [
            _make_scene(scene_type=SceneType.HOOK),
            _make_scene(scene_type=SceneType.CONTENT),
            _make_scene(scene_type=SceneType.CONCLUSION),
        ]
        tts_results = [
            _make_tts_result(index=0, duration=3.0, start_offset=0.0),
            _make_tts_result(index=1, duration=7.0, start_offset=3.0),
            _make_tts_result(index=2, duration=2.5, start_offset=10.0),
        ]

        results = await manager.source_visuals_for_scenes(scenes, tts_results, tmp_path)

        assert len(results) == 3
        assert results[0].duration == 3.0
        assert results[0].start_offset == 0.0
        assert results[1].duration == 7.0
        assert results[1].start_offset == 3.0
        assert results[2].duration == 2.5
        assert results[2].start_offset == 10.0

    @pytest.mark.asyncio
    async def test_visual_keyword_none_falls_back_to_text(
        self,
        manager: VisualSourcingManager,
        mock_pexels: MagicMock,
        tmp_path: Path,
    ) -> None:
        """When visual_keyword is None, uses first 50 chars of text."""
        asset = _make_asset()
        mock_pexels.search_images.return_value = [asset]

        scenes = [_make_scene(visual_keyword=None, text="Some long text for the scene")]
        tts_results = [_make_tts_result()]

        await manager.source_visuals_for_scenes(scenes, tts_results, tmp_path)

        # search_images called with text[:50] as query
        call_kwargs = mock_pexels.search_images.call_args.kwargs
        assert call_kwargs["query"] == "Some long text for the scene"


class TestSourceForScene:
    """Tests for _source_for_scene internal method."""

    @pytest.mark.asyncio
    async def test_tries_pexels_image_first_then_video(
        self,
        manager: VisualSourcingManager,
        mock_pexels: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Pexels image search is tried first, then video if image fails."""
        mock_pexels.search_images.return_value = []

        video_asset = _make_asset(asset_type=VisualSourceType.STOCK_VIDEO, source_id="vid_1")
        mock_pexels.search_videos.return_value = [video_asset]

        result = await manager._source_for_scene(
            keyword="test",
            duration=5.0,
            output_dir=tmp_path / "scene_000",
            orientation="portrait",
        )

        assert result.source_id == "vid_1"
        mock_pexels.search_images.assert_awaited_once()
        mock_pexels.search_videos.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_metadata_score_below_threshold_skipped(
        self,
        manager: VisualSourcingManager,
        mock_pexels: MagicMock,
        mock_wan: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Assets with metadata_score below threshold are skipped."""
        low_score_asset = _make_asset(metadata_score=0.1)  # below 0.3 threshold
        mock_pexels.search_images.return_value = [low_score_asset]
        mock_pexels.search_videos.return_value = []
        mock_wan.is_available.return_value = False

        result = await manager._source_for_scene(
            keyword="test",
            duration=5.0,
            output_dir=tmp_path / "scene_000",
            orientation="portrait",
        )

        # Falls through to fallback because low score asset was skipped
        assert result.type == VisualSourceType.SOLID_COLOR

    @pytest.mark.asyncio
    async def test_exclude_source_ids_skips_duplicates(
        self,
        manager: VisualSourcingManager,
        mock_pexels: MagicMock,
        mock_wan: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Assets matching exclude_source_ids are skipped."""
        asset = _make_asset(source="pexels", source_id="12345")
        mock_pexels.search_images.return_value = [asset]
        mock_pexels.search_videos.return_value = []
        mock_wan.is_available.return_value = False

        exclude = {("pexels", "12345")}
        result = await manager._source_for_scene(
            keyword="test",
            duration=5.0,
            output_dir=tmp_path / "scene_000",
            orientation="portrait",
            exclude_source_ids=exclude,
        )

        # Falls through to fallback because the only asset was excluded
        assert result.type == VisualSourceType.SOLID_COLOR

    @pytest.mark.asyncio
    async def test_wan_used_when_pexels_empty(
        self,
        manager: VisualSourcingManager,
        mock_pexels: MagicMock,
        mock_wan: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Wan is used as fallback when Pexels returns no valid results."""
        mock_pexels.search_images.return_value = []
        mock_pexels.search_videos.return_value = []

        wan_asset = _make_asset(
            source="wan",
            source_id="wan_001",
            asset_type=VisualSourceType.AI_VIDEO,
        )
        mock_wan.is_available.return_value = True
        mock_wan.generate.return_value = [wan_asset]

        result = await manager._source_for_scene(
            keyword="futuristic city",
            duration=5.0,
            output_dir=tmp_path / "scene_000",
            orientation="portrait",
        )

        assert result.source == "wan"
        mock_wan.generate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_downloads_asset_if_not_downloaded(
        self,
        manager: VisualSourcingManager,
        mock_pexels: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Asset without existing path triggers download."""
        asset = _make_asset(path=None)  # is_downloaded will be False
        downloaded_asset = _make_asset(path=tmp_path / "downloaded.jpg")
        mock_pexels.search_images.return_value = [asset]
        # Override the fixture's side_effect so return_value is used
        mock_pexels.download.side_effect = None
        mock_pexels.download.return_value = downloaded_asset

        result = await manager._source_for_scene(
            keyword="test",
            duration=5.0,
            output_dir=tmp_path / "scene_000",
            orientation="portrait",
        )

        mock_pexels.download.assert_awaited_once()
        assert result.path == tmp_path / "downloaded.jpg"


class TestCreateFallback:
    """Tests for _create_fallback solid color generation."""

    @pytest.mark.asyncio
    async def test_portrait_creates_1080x1920(
        self, manager: VisualSourcingManager, tmp_path: Path
    ) -> None:
        """Portrait orientation creates 1080x1920 image."""
        result = await manager._create_fallback(tmp_path, duration=3.0, orientation="portrait")

        assert result.type == VisualSourceType.SOLID_COLOR
        assert result.width == 1080
        assert result.height == 1920
        assert result.duration == 3.0
        assert result.source == "fallback"
        assert result.path is not None
        assert result.path.exists()

    @pytest.mark.asyncio
    async def test_landscape_creates_1920x1080(
        self, manager: VisualSourcingManager, tmp_path: Path
    ) -> None:
        """Landscape orientation creates 1920x1080 image."""
        result = await manager._create_fallback(tmp_path, duration=4.0, orientation="landscape")

        assert result.width == 1920
        assert result.height == 1080
        assert result.path is not None
        assert result.path.exists()

    @pytest.mark.asyncio
    async def test_square_creates_1080x1080(
        self, manager: VisualSourcingManager, tmp_path: Path
    ) -> None:
        """Square orientation creates 1080x1080 image."""
        result = await manager._create_fallback(tmp_path, duration=2.0, orientation="square")

        assert result.width == 1080
        assert result.height == 1080
        assert result.path is not None
        assert result.path.exists()

    @pytest.mark.asyncio
    async def test_fallback_file_is_valid_png(
        self, manager: VisualSourcingManager, tmp_path: Path
    ) -> None:
        """Fallback generates a valid PNG file."""
        from PIL import Image

        result = await manager._create_fallback(tmp_path, duration=1.0, orientation="portrait")

        assert result.path is not None
        img = Image.open(result.path)
        assert img.size == (1080, 1920)
        assert img.mode == "RGB"

    @pytest.mark.asyncio
    async def test_fallback_creates_output_dir(
        self, manager: VisualSourcingManager, tmp_path: Path
    ) -> None:
        """Fallback creates output directory if it does not exist."""
        nested_dir = tmp_path / "a" / "b" / "c"
        result = await manager._create_fallback(nested_dir, duration=1.0, orientation="portrait")

        assert nested_dir.exists()
        assert result.path is not None
        assert result.path.exists()


class TestClose:
    """Tests for close() delegation."""

    @pytest.mark.asyncio
    async def test_close_delegates_to_clients(
        self, manager: VisualSourcingManager, mock_pexels: MagicMock, mock_wan: MagicMock
    ) -> None:
        """close() calls pexels.close() and wan.close()."""
        await manager.close()
        mock_pexels.close.assert_awaited_once()
        mock_wan.close.assert_awaited_once()


class TestEdgeCases:
    """Additional edge case tests."""

    @pytest.mark.asyncio
    async def test_pexels_exception_triggers_fallback_in_orchestrator(
        self,
        manager: VisualSourcingManager,
        mock_pexels: MagicMock,
        mock_wan: MagicMock,
        tmp_path: Path,
    ) -> None:
        """httpx.HTTPError in _source_for_scene triggers fallback in orchestrator."""
        import httpx

        mock_pexels.search_images.side_effect = httpx.HTTPError("connection failed")
        mock_pexels.search_videos.side_effect = httpx.HTTPError("connection failed")
        mock_wan.is_available.side_effect = httpx.HTTPError("connection failed")

        scenes = [_make_scene()]
        tts_results = [_make_tts_result(duration=3.0)]

        results = await manager.source_visuals_for_scenes(scenes, tts_results, tmp_path)

        assert len(results) == 1
        assert results[0].asset.type == VisualSourceType.SOLID_COLOR

    @pytest.mark.asyncio
    async def test_asset_duration_overwritten_by_tts_duration(
        self,
        manager: VisualSourcingManager,
        mock_pexels: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Asset duration is set to TTS duration regardless of original."""
        asset = _make_asset()  # has duration=5.0
        mock_pexels.search_images.return_value = [asset]

        scenes = [_make_scene()]
        tts_results = [_make_tts_result(duration=8.5)]

        results = await manager.source_visuals_for_scenes(scenes, tts_results, tmp_path)

        assert results[0].asset.duration == 8.5
        assert results[0].duration == 8.5

    @pytest.mark.asyncio
    async def test_custom_reuse_types_config(
        self,
        mock_http_client: MagicMock,
        mock_pexels: MagicMock,
        mock_wan: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Custom reuse_previous_visual_types config is respected."""
        config = VisualConfig(reuse_previous_visual_types=["cta", "conclusion"])
        mgr = VisualSourcingManager(
            http_client=mock_http_client,
            config=config,
            pexels_client=mock_pexels,
            wan_video_source=mock_wan,
        )

        asset = _make_asset()
        mock_pexels.search_images.return_value = [asset]

        scenes = [
            _make_scene(scene_type=SceneType.CONTENT),
            _make_scene(scene_type=SceneType.CONCLUSION),
        ]
        tts_results = [
            _make_tts_result(index=0, duration=5.0, start_offset=0.0),
            _make_tts_result(index=1, duration=3.0, start_offset=5.0),
        ]

        results = await mgr.source_visuals_for_scenes(scenes, tts_results, tmp_path)

        assert len(results) == 2
        # CONCLUSION reused previous asset
        assert results[1].asset.source == results[0].asset.source
        assert mock_pexels.search_images.call_count == 1

    @pytest.mark.asyncio
    async def test_metadata_score_none_passes_threshold(
        self,
        manager: VisualSourcingManager,
        mock_pexels: MagicMock,
        mock_wan: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Asset with metadata_score=None passes threshold (no score = allow)."""
        # Create a real file so is_downloaded returns True
        downloaded_file = tmp_path / "downloaded.jpg"
        downloaded_file.write_bytes(b"fake-image")
        asset = _make_asset(metadata_score=None, path=downloaded_file)  # type: ignore[arg-type]
        # Manually set to None since helper defaults to float
        asset.metadata_score = None
        mock_pexels.search_images.return_value = [asset]
        mock_pexels.search_videos.return_value = []
        mock_wan.is_available.return_value = False

        result = await manager._source_for_scene(
            keyword="test",
            duration=5.0,
            output_dir=tmp_path / "scene_000",
            orientation="portrait",
        )

        # None metadata_score skips threshold check — search relevance is trusted
        assert result.type != VisualSourceType.SOLID_COLOR
