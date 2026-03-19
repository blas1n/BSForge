"""Unit tests for WanVideoSource."""

import base64
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config.video import WanConfig
from app.services.generator.visual.base import VisualAsset, VisualSourceType
from app.services.generator.visual.wan_video_source import WanVideoSource


@pytest.fixture
def wan_config() -> WanConfig:
    return WanConfig(
        service_url="http://wan:7861",
        enabled=True,
        timeout=30.0,
        default_duration_seconds=5.0,
        default_fps=16,
        base_width=480,
        base_height=832,
    )


@pytest.fixture
def mock_http_client() -> MagicMock:
    client = MagicMock()
    client.get = AsyncMock()
    client.post = AsyncMock()
    return client


@pytest.fixture
def source(mock_http_client, wan_config) -> WanVideoSource:
    return WanVideoSource(http_client=mock_http_client, config=wan_config)


class TestIsAvailable:
    """Tests for WanVideoSource.is_available()."""

    @pytest.mark.asyncio
    async def test_returns_false_when_disabled(self, mock_http_client):
        config = WanConfig(enabled=False)
        source = WanVideoSource(http_client=mock_http_client, config=config)

        result = await source.is_available()

        assert result is False
        mock_http_client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_true_when_service_healthy(self, source, mock_http_client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "ok",
            "device": "cuda",
            "pipeline_loaded": True,
            "model_id": "Wan-AI/Wan2.2-T2V-1.3B",
        }
        mock_http_client.get.return_value = mock_response

        result = await source.is_available()

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_service_returns_non_ok(self, source, mock_http_client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "loading"}
        mock_http_client.get.return_value = mock_response

        result = await source.is_available()

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_connection_error(self, source, mock_http_client):
        mock_http_client.get.side_effect = ConnectionError("refused")

        result = await source.is_available()

        assert result is False

    @pytest.mark.asyncio
    async def test_uses_cached_result_on_second_call(self, source, mock_http_client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_http_client.get.return_value = mock_response

        await source.is_available()
        await source.is_available()

        # Second call should use cache
        assert mock_http_client.get.call_count == 1

    @pytest.mark.asyncio
    async def test_force_check_bypasses_cache(self, source, mock_http_client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_http_client.get.return_value = mock_response

        await source.is_available()
        await source.is_available(force_check=True)

        assert mock_http_client.get.call_count == 2


class TestGenerate:
    """Tests for WanVideoSource.generate()."""

    @pytest.fixture(autouse=True)
    def mock_available(self, source):
        source._service_available = True

    @pytest.mark.asyncio
    async def test_returns_empty_when_service_unavailable(self, mock_http_client, wan_config):
        source = WanVideoSource(http_client=mock_http_client, config=WanConfig(enabled=False))

        results = await source.generate("sunset over mountains")

        assert results == []

    @pytest.mark.asyncio
    async def test_generate_returns_ai_video_assets(self, source, mock_http_client):
        video_b64 = base64.b64encode(b"fake mp4 data").decode()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "video": video_b64,
            "duration_seconds": 5.0,
            "width": 480,
            "height": 832,
            "fps": 16,
            "seed": 12345,
            "num_frames": 81,
        }
        mock_response.raise_for_status = MagicMock()
        mock_http_client.post.return_value = mock_response

        results = await source.generate("dramatic city skyline", count=1)

        assert len(results) == 1
        asset = results[0]
        assert asset.type == VisualSourceType.AI_VIDEO
        assert asset.source == "wan_video"
        assert asset.duration == 5.0
        assert asset.width == 480
        assert asset.height == 832
        assert asset.metadata["video_base64"] == video_b64
        assert asset.metadata["seed"] == 12345

    @pytest.mark.asyncio
    async def test_generate_multiple_clips(self, source, mock_http_client):
        def make_response(seed_val: int) -> MagicMock:
            r = MagicMock()
            r.json.return_value = {
                "video": base64.b64encode(b"data").decode(),
                "duration_seconds": 5.0,
                "width": 480,
                "height": 832,
                "fps": 16,
                "seed": seed_val,
            }
            r.raise_for_status = MagicMock()
            return r

        mock_http_client.post.side_effect = [make_response(1), make_response(2)]

        results = await source.generate("nature", count=2)

        assert len(results) == 2
        assert mock_http_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_generate_uses_portrait_dimensions_by_default(self, source, mock_http_client):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "video": base64.b64encode(b"d").decode(),
            "seed": 1,
            "duration_seconds": 5.0,
            "width": 480,
            "height": 832,
            "fps": 16,
        }
        mock_response.raise_for_status = MagicMock()
        mock_http_client.post.return_value = mock_response

        await source.generate("test", count=1, orientation="portrait")

        call_json = mock_http_client.post.call_args.kwargs["json"]
        assert call_json["width"] == 480
        assert call_json["height"] == 832

    @pytest.mark.asyncio
    async def test_generate_landscape_swaps_dimensions(self, source, mock_http_client):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "video": base64.b64encode(b"d").decode(),
            "seed": 1,
            "duration_seconds": 5.0,
            "width": 832,
            "height": 480,
            "fps": 16,
        }
        mock_response.raise_for_status = MagicMock()
        mock_http_client.post.return_value = mock_response

        await source.generate("test", count=1, orientation="landscape")

        call_json = mock_http_client.post.call_args.kwargs["json"]
        assert call_json["width"] == 832
        assert call_json["height"] == 480

    @pytest.mark.asyncio
    async def test_generate_skips_failed_clips(self, source, mock_http_client):
        mock_http_client.post.side_effect = RuntimeError("GPU OOM")

        results = await source.generate("test", count=1)

        assert results == []
        assert source._service_available is False

    @pytest.mark.asyncio
    async def test_generate_uses_seed_increments(self, source, mock_http_client):
        def make_response() -> MagicMock:
            r = MagicMock()
            r.json.return_value = {
                "video": base64.b64encode(b"d").decode(),
                "seed": 100,
                "duration_seconds": 5.0,
                "width": 480,
                "height": 832,
                "fps": 16,
            }
            r.raise_for_status = MagicMock()
            return r

        mock_http_client.post.side_effect = [make_response(), make_response()]

        await source.generate("test", count=2, seed=100)

        calls = mock_http_client.post.call_args_list
        assert calls[0].kwargs["json"]["seed"] == 100
        assert calls[1].kwargs["json"]["seed"] == 101


class TestSearch:
    """Tests for WanVideoSource.search() (delegates to generate)."""

    @pytest.mark.asyncio
    async def test_search_delegates_to_generate(self, source):
        source.generate = AsyncMock(return_value=[])

        await source.search("city skyline", max_results=2, orientation="portrait")

        source.generate.assert_called_once()
        call_kwargs = source.generate.call_args.kwargs
        assert call_kwargs["prompt"] == "city skyline"
        assert call_kwargs["count"] == 2
        assert call_kwargs["orientation"] == "portrait"

    @pytest.mark.asyncio
    async def test_search_uses_min_duration(self, source):
        source.generate = AsyncMock(return_value=[])

        await source.search("test", min_duration=8.0)

        call_kwargs = source.generate.call_args.kwargs
        assert call_kwargs["duration_seconds"] == 8.0

    @pytest.mark.asyncio
    async def test_search_min_duration_floor_is_3(self, source):
        source.generate = AsyncMock(return_value=[])

        await source.search("test", min_duration=1.0)

        call_kwargs = source.generate.call_args.kwargs
        assert call_kwargs["duration_seconds"] >= 3.0


class TestDownload:
    """Tests for WanVideoSource.download()."""

    def _make_asset(self, video_b64: str | None = None) -> VisualAsset:
        return VisualAsset(
            type=VisualSourceType.AI_VIDEO,
            source="wan_video",
            source_id="wan_12345",
            metadata={"video_base64": video_b64} if video_b64 else {},
        )

    @pytest.mark.asyncio
    async def test_download_saves_mp4(self, source, tmp_path):
        video_data = b"fake mp4 content"
        video_b64 = base64.b64encode(video_data).decode()
        asset = self._make_asset(video_b64)

        result = await source.download(asset, tmp_path)

        assert result.path is not None
        assert result.path.exists()
        assert result.path.suffix == ".mp4"
        assert result.path.read_bytes() == video_data

    @pytest.mark.asyncio
    async def test_download_filename_contains_source_id(self, source, tmp_path):
        video_b64 = base64.b64encode(b"data").decode()
        asset = self._make_asset(video_b64)

        result = await source.download(asset, tmp_path)

        assert "wan_12345" in result.path.name

    @pytest.mark.asyncio
    async def test_download_clears_base64_from_metadata(self, source, tmp_path):
        video_b64 = base64.b64encode(b"data").decode()
        asset = self._make_asset(video_b64)

        result = await source.download(asset, tmp_path)

        assert "video_base64" not in result.metadata

    @pytest.mark.asyncio
    async def test_download_raises_when_no_video_data(self, source, tmp_path):
        asset = self._make_asset(None)

        with pytest.raises(ValueError, match="no video data"):
            await source.download(asset, tmp_path)

    @pytest.mark.asyncio
    async def test_download_creates_output_dir(self, source, tmp_path):
        nested_dir = tmp_path / "nested" / "output"
        video_b64 = base64.b64encode(b"data").decode()
        asset = self._make_asset(video_b64)

        await source.download(asset, nested_dir)

        assert nested_dir.exists()

    @pytest.mark.asyncio
    async def test_download_skips_if_already_exists(self, source, tmp_path):
        video_b64 = base64.b64encode(b"original").decode()
        asset = self._make_asset(video_b64)

        # Create file manually first
        existing = tmp_path / "wan_wan_12345.mp4"
        existing.write_bytes(b"already there")

        result = await source.download(asset, tmp_path)

        # Should return immediately without overwriting
        assert result.path.read_bytes() == b"already there"


class TestEvaluate:
    """Tests for WanVideoSource.evaluate()."""

    @pytest.fixture(autouse=True)
    def mock_available(self, source):
        source._service_available = True

    @pytest.mark.asyncio
    async def test_evaluate_returns_score(self, source, mock_http_client, tmp_path):
        video_file = tmp_path / "test.mp4"
        video_file.write_bytes(b"fake video")

        mock_response = MagicMock()
        mock_response.json.return_value = {"score": 0.75}
        mock_response.raise_for_status = MagicMock()
        mock_http_client.post.return_value = mock_response

        score = await source.evaluate(video_file, "sunset")

        assert score == pytest.approx(0.75)

    @pytest.mark.asyncio
    async def test_evaluate_returns_none_when_unavailable(self, mock_http_client, wan_config):
        source = WanVideoSource(http_client=mock_http_client, config=WanConfig(enabled=False))
        result = await source.evaluate(Path("/tmp/test.mp4"), "test")

        assert result is None

    @pytest.mark.asyncio
    async def test_evaluate_returns_none_on_file_not_found(self, source, tmp_path):
        missing = tmp_path / "nonexistent.mp4"

        result = await source.evaluate(missing, "test")

        assert result is None

    @pytest.mark.asyncio
    async def test_evaluate_returns_none_on_api_error(self, source, mock_http_client, tmp_path):
        video_file = tmp_path / "test.mp4"
        video_file.write_bytes(b"data")
        mock_http_client.post.side_effect = RuntimeError("API error")

        result = await source.evaluate(video_file, "test")

        assert result is None
        assert source._service_available is False


class TestGetDimensions:
    """Tests for WanVideoSource._get_dimensions()."""

    def test_portrait_dimensions(self, source):
        w, h = source._get_dimensions("portrait")
        assert w == 480
        assert h == 832

    def test_landscape_swaps(self, source):
        w, h = source._get_dimensions("landscape")
        assert w == 832
        assert h == 480

    def test_square_uses_smaller_side(self, source):
        w, h = source._get_dimensions("square")
        assert w == h == 480  # min(480, 832)


class TestEnhancePrompt:
    """Tests for WanVideoSource._enhance_prompt()."""

    def test_portrait_includes_vertical_hint(self, source: WanVideoSource) -> None:
        result = source._enhance_prompt("city street", "portrait")
        assert "vertical 9:16" in result
        assert "city street" in result

    def test_landscape_includes_horizontal_hint(self, source: WanVideoSource) -> None:
        result = source._enhance_prompt("ocean sunset", "landscape")
        assert "horizontal widescreen" in result

    def test_includes_cinematic_keywords(self, source: WanVideoSource) -> None:
        result = source._enhance_prompt("tech office", "portrait")
        assert "cinematic lighting" in result
        assert "professional film quality" in result

    def test_original_prompt_preserved(self, source: WanVideoSource) -> None:
        result = source._enhance_prompt("코딩하는 사람", "portrait")
        assert "코딩하는 사람" in result
