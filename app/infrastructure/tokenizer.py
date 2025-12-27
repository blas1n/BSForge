"""Multilingual tokenizer using uniseg and stopwordsiso.

Language-agnostic approach: no language detection needed.
- uniseg implements Unicode Annex #29 for word boundary detection
- All language stopwords are merged for filtering

Note: CJK languages may not have perfect word segmentation since they
require dictionary-based segmentation. However, for topic clustering
purposes, this is acceptable as the goal is grouping similar topics.

Usage:
    from app.infrastructure.tokenizer import tokenize_without_stopwords

    tokens = tokenize_without_stopwords("BTS 방탄소년단 Grammy 2024")
    # Returns: ['bts', '방탄소년단', 'grammy', '2024']
"""

import stopwordsiso
from uniseg.wordbreak import words

# Merged stopwords from all supported languages (cached)
_all_stopwords: set[str] | None = None


def _get_all_stopwords() -> set[str]:
    """Get merged stopwords from all supported languages.

    Caches the result for performance - stopwords are loaded once.

    Returns:
        Set of stopwords from all supported languages.
    """
    global _all_stopwords
    if _all_stopwords is None:
        _all_stopwords = set()
        # Merge stopwords from all available languages
        for lang in stopwordsiso.langs():
            _all_stopwords.update(stopwordsiso.stopwords(lang))
    return _all_stopwords


def _is_word_token(token: str) -> bool:
    """Check if token is a meaningful word (not whitespace/punctuation).

    Args:
        token: Token to check.

    Returns:
        True if token contains at least one alphanumeric character.
    """
    return any(c.isalnum() for c in token)


def tokenize(text: str, min_length: int = 2) -> list[str]:
    """Tokenize text using Unicode Annex #29 word boundaries.

    Handles all Unicode scripts including mixed-language text.
    CJK languages may have character-by-character segmentation
    rather than word-level, but this is acceptable for clustering.

    Args:
        text: Text to tokenize.
        min_length: Minimum token length (default: 2).

    Returns:
        List of tokens (lowercased, filtered by min_length).
    """
    # uniseg.wordbreak.words() yields word tokens based on UAX #29
    tokens = [token.lower().strip() for token in words(text) if _is_word_token(token)]
    return [t for t in tokens if len(t) >= min_length]


def tokenize_without_stopwords(text: str, min_length: int = 2) -> list[str]:
    """Tokenize and filter stopwords from all languages.

    Args:
        text: Text to tokenize.
        min_length: Minimum token length (default: 2).

    Returns:
        List of tokens with stopwords removed.
    """
    tokens = tokenize(text, min_length)
    stopwords = _get_all_stopwords()
    return [t for t in tokens if t not in stopwords]


__all__ = [
    "tokenize",
    "tokenize_without_stopwords",
]
