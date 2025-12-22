"""Font discovery and resolution using fontconfig.

This module provides font lookup functionality using the fontconfig-py library,
eliminating the need for hardcoded font paths.
"""

from functools import lru_cache

import fontconfig

from app.core.logging import get_logger

logger = get_logger(__name__)


@lru_cache(maxsize=32)
def find_font(query: str) -> dict[str, str] | None:
    """Find font using fontconfig pattern matching.

    Uses fontconfig to resolve font queries to actual file paths.
    Results are cached for performance.

    Args:
        query: Fontconfig pattern string. Examples:
            - ':lang=ko:weight=bold' (Korean bold font)
            - ':lang=ja:weight=regular' (Japanese regular font)
            - 'Noto Sans CJK KR:weight=bold' (specific font family)
            - 'sans-serif' (generic family)
            - 'monospace:weight=bold' (generic with weight)

    Returns:
        Dict with 'family', 'file', 'style' keys, or None if not found.

    Example:
        >>> find_font(':lang=ko:weight=bold')
        {'family': 'Noto Sans CJK KR', 'file': '/path/to/font.otf', 'style': 'Bold'}
    """
    try:
        result = fontconfig.match(query)
        if result and result.get("file"):
            logger.debug(f"Font resolved: '{query}' -> {result['file']}")
            return result
    except Exception as e:
        logger.warning(f"Font lookup failed: {query}, error: {e}")

    logger.debug(f"Font not found: {query}")
    return None


def find_font_path(query: str) -> str | None:
    """Find font file path using fontconfig.

    Convenience wrapper that returns just the file path.

    Args:
        query: Fontconfig pattern string.

    Returns:
        Font file path, or None if not found.
    """
    result = find_font(query)
    return result["file"] if result else None


def find_font_by_name(font_name: str, fallback: str = "sans-serif:weight=bold") -> str:
    """Find font by name with automatic weight detection.

    Parses font names like 'Pretendard-Bold' to extract family and weight.

    Args:
        font_name: Font name, optionally with weight suffix (e.g., 'Pretendard-Bold')
        fallback: Fallback fontconfig query if font not found.

    Returns:
        Path to font file, or fallback if not found.
    """
    # Parse weight from font name
    weight = "regular"
    family = font_name

    weight_suffixes = {
        "-Bold": "bold",
        "-Regular": "regular",
        "-Light": "light",
        "-Medium": "medium",
        "-Black": "black",
    }

    for suffix, w in weight_suffixes.items():
        if font_name.endswith(suffix):
            family = font_name[: -len(suffix)]
            weight = w
            break

    # Try exact match first
    result = find_font(f"{family}:weight={weight}")
    if result:
        return result["file"]

    # Try original name as-is
    result = find_font(font_name)
    if result:
        return result["file"]

    # Fallback
    fallback_result = find_font(fallback)
    if fallback_result:
        path = fallback_result["file"]
    else:
        path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    logger.warning(f"Font '{font_name}' not found, using fallback: {path}")
    return path


def clear_font_cache() -> None:
    """Clear the font lookup cache.

    Call this if fonts are installed/removed at runtime.
    """
    find_font.cache_clear()
    logger.info("Font cache cleared")


__all__ = [
    "find_font",
    "find_font_path",
    "find_font_by_name",
    "clear_font_cache",
]
