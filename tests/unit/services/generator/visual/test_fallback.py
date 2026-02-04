"""Unit tests for fallback visual generator."""

import pytest

from app.services.generator.visual.base import VisualAsset, VisualSourceType
from app.services.generator.visual.fallback import FallbackGenerator


class TestFallbackGeneratorInit:
    """Tests for FallbackGenerator initialization."""

    def test_default_values(self):
        """Test default initialization values."""
        generator = FallbackGenerator()

        assert generator._default_color == "#1a1a2e"
        assert generator._default_gradient == ["#1a1a2e", "#16213e"]

    def test_custom_values(self):
        """Test custom initialization values."""
        generator = FallbackGenerator(
            default_color="#FFFFFF",
            default_gradient=["#FF0000", "#00FF00", "#0000FF"],
        )

        assert generator._default_color == "#FFFFFF"
        assert generator._default_gradient == ["#FF0000", "#00FF00", "#0000FF"]


class TestFallbackGeneratorSearch:
    """Tests for FallbackGenerator.search method."""

    @pytest.fixture
    def generator(self):
        return FallbackGenerator()

    @pytest.mark.asyncio
    async def test_search_returns_solid_color_first(self, generator):
        """Test that search returns solid color asset first."""
        results = await generator.search("any query")

        assert len(results) >= 1
        assert results[0].type == VisualSourceType.SOLID_COLOR

    @pytest.mark.asyncio
    async def test_search_returns_gradient_second(self, generator):
        """Test that search returns gradient asset second."""
        results = await generator.search("any query", max_results=2)

        assert len(results) == 2
        assert results[1].type == VisualSourceType.GRADIENT

    @pytest.mark.asyncio
    async def test_search_ignores_query(self, generator):
        """Test that query is ignored."""
        results1 = await generator.search("nature")
        results2 = await generator.search("abstract")

        # Both should return same types
        assert results1[0].type == results2[0].type

    @pytest.mark.asyncio
    async def test_search_respects_max_results(self, generator):
        """Test that max_results is respected."""
        results = await generator.search("query", max_results=1)

        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_search_portrait_orientation(self, generator):
        """Test search with portrait orientation."""
        results = await generator.search("query", orientation="portrait")

        assert results[0].width == 1080
        assert results[0].height == 1920

    @pytest.mark.asyncio
    async def test_search_landscape_orientation(self, generator):
        """Test search with landscape orientation."""
        results = await generator.search("query", orientation="landscape")

        assert results[0].width == 1920
        assert results[0].height == 1080

    @pytest.mark.asyncio
    async def test_search_square_orientation(self, generator):
        """Test search with square orientation."""
        results = await generator.search("query", orientation="square")

        assert results[0].width == 1080
        assert results[0].height == 1080

    @pytest.mark.asyncio
    async def test_search_assets_have_source_id(self, generator):
        """Test that returned assets have source IDs."""
        results = await generator.search("query", max_results=2)

        for result in results:
            assert result.source_id is not None
            assert result.source == "fallback"


class TestFallbackGeneratorDownload:
    """Tests for FallbackGenerator.download method."""

    @pytest.fixture
    def generator(self):
        return FallbackGenerator()

    @pytest.mark.asyncio
    async def test_download_solid_color(self, generator, tmp_path):
        """Test downloading (generating) solid color image."""
        asset = VisualAsset(
            type=VisualSourceType.SOLID_COLOR,
            color="#FF0000",
            width=100,
            height=100,
            source="fallback",
            source_id="test_solid",
        )

        result = await generator.download(asset, tmp_path)

        assert result.path is not None
        assert result.path.exists()
        assert result.path.suffix == ".png"

    @pytest.mark.asyncio
    async def test_download_gradient(self, generator, tmp_path):
        """Test downloading (generating) gradient image."""
        asset = VisualAsset(
            type=VisualSourceType.GRADIENT,
            gradient_colors=["#FF0000", "#0000FF"],
            width=100,
            height=100,
            source="fallback",
            source_id="test_gradient",
        )

        result = await generator.download(asset, tmp_path)

        assert result.path is not None
        assert result.path.exists()
        assert result.path.suffix == ".png"

    @pytest.mark.asyncio
    async def test_download_unsupported_type_raises(self, generator, tmp_path):
        """Test that unsupported type raises ValueError."""
        asset = VisualAsset(
            type=VisualSourceType.STOCK_IMAGE,
            source="fallback",
            source_id="test",
        )

        with pytest.raises(ValueError, match="Unsupported fallback type"):
            await generator.download(asset, tmp_path)

    @pytest.mark.asyncio
    async def test_download_creates_output_dir(self, generator, tmp_path):
        """Test that download creates output directory if needed."""
        nested_dir = tmp_path / "nested" / "dir"
        asset = VisualAsset(
            type=VisualSourceType.SOLID_COLOR,
            color="#FF0000",
            width=100,
            height=100,
            source="fallback",
            source_id="test_solid",
        )

        result = await generator.download(asset, nested_dir)

        assert nested_dir.exists()
        assert result.path is not None


class TestFallbackGeneratorCreateSolid:
    """Tests for FallbackGenerator.create_solid method."""

    @pytest.fixture
    def generator(self):
        return FallbackGenerator()

    def test_create_solid(self, generator, tmp_path):
        """Test creating solid color image."""
        asset = generator.create_solid("#FF0000", 100, 100, tmp_path)

        assert asset.type == VisualSourceType.SOLID_COLOR
        assert asset.path is not None
        assert asset.path.exists()
        assert asset.color == "#FF0000"
        assert asset.width == 100
        assert asset.height == 100

    def test_create_solid_different_sizes(self, generator, tmp_path):
        """Test creating solid images with different sizes."""
        asset = generator.create_solid("#00FF00", 1080, 1920, tmp_path)

        assert asset.width == 1080
        assert asset.height == 1920


class TestFallbackGeneratorCreateGradient:
    """Tests for FallbackGenerator.create_gradient method."""

    @pytest.fixture
    def generator(self):
        return FallbackGenerator()

    def test_create_gradient_vertical(self, generator, tmp_path):
        """Test creating vertical gradient image."""
        asset = generator.create_gradient(
            ["#FF0000", "#0000FF"],
            100,
            100,
            tmp_path,
            direction="vertical",
        )

        assert asset.type == VisualSourceType.GRADIENT
        assert asset.path is not None
        assert asset.path.exists()
        assert asset.gradient_colors == ["#FF0000", "#0000FF"]
        assert asset.metadata["direction"] == "vertical"

    def test_create_gradient_horizontal(self, generator, tmp_path):
        """Test creating horizontal gradient image."""
        asset = generator.create_gradient(
            ["#FF0000", "#0000FF"],
            100,
            100,
            tmp_path,
            direction="horizontal",
        )

        assert asset.metadata["direction"] == "horizontal"

    def test_create_gradient_three_colors(self, generator, tmp_path):
        """Test creating gradient with three colors."""
        colors = ["#FF0000", "#00FF00", "#0000FF"]
        asset = generator.create_gradient(colors, 100, 100, tmp_path)

        assert asset.gradient_colors == colors


class TestFallbackGeneratorHelpers:
    """Tests for FallbackGenerator helper methods."""

    @pytest.fixture
    def generator(self):
        return FallbackGenerator()

    def test_hex_to_rgb_white(self, generator):
        """Test converting white hex to RGB."""
        rgb = generator._hex_to_rgb("#FFFFFF")

        assert rgb == (255, 255, 255)

    def test_hex_to_rgb_black(self, generator):
        """Test converting black hex to RGB."""
        rgb = generator._hex_to_rgb("#000000")

        assert rgb == (0, 0, 0)

    def test_hex_to_rgb_red(self, generator):
        """Test converting red hex to RGB."""
        rgb = generator._hex_to_rgb("#FF0000")

        assert rgb == (255, 0, 0)

    def test_hex_to_rgb_without_hash(self, generator):
        """Test converting hex without hash prefix."""
        rgb = generator._hex_to_rgb("00FF00")

        assert rgb == (0, 255, 0)

    def test_interpolate_colors_single(self, generator):
        """Test interpolation with single color."""
        colors = [(255, 0, 0)]
        result = generator._interpolate_colors(colors, 0.5)

        assert result == (255, 0, 0)

    def test_interpolate_colors_two_start(self, generator):
        """Test interpolation at start (t=0)."""
        colors = [(255, 0, 0), (0, 0, 255)]
        result = generator._interpolate_colors(colors, 0.0)

        assert result == (255, 0, 0)

    def test_interpolate_colors_two_end(self, generator):
        """Test interpolation at end (t=1)."""
        colors = [(255, 0, 0), (0, 0, 255)]
        result = generator._interpolate_colors(colors, 1.0)

        assert result == (0, 0, 255)

    def test_interpolate_colors_two_middle(self, generator):
        """Test interpolation at middle (t=0.5)."""
        colors = [(0, 0, 0), (100, 100, 100)]
        result = generator._interpolate_colors(colors, 0.5)

        assert result == (50, 50, 50)

    def test_get_dimensions_portrait(self, generator):
        """Test getting portrait dimensions."""
        width, height = generator._get_dimensions("portrait")

        assert width == 1080
        assert height == 1920

    def test_get_dimensions_landscape(self, generator):
        """Test getting landscape dimensions."""
        width, height = generator._get_dimensions("landscape")

        assert width == 1920
        assert height == 1080

    def test_get_dimensions_square(self, generator):
        """Test getting square dimensions."""
        width, height = generator._get_dimensions("square")

        assert width == 1080
        assert height == 1080
