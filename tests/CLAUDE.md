# tests/CLAUDE.md - Testing Conventions

## Test Structure

```
tests/
├── unit/           # Unit tests (mocked dependencies)
│   └── services/   # Service-specific tests
├── e2e/            # End-to-end tests
│   ├── conftest.py # Shared fixtures & DTO factories
│   ├── test_video_generation.py
│   ├── test_content_collection.py
│   └── test_full_pipeline.py
└── conftest.py     # Root fixtures
```

## Running Tests

```bash
# All tests
/home/vscode/.local/bin/uv run pytest

# Unit tests only
/home/vscode/.local/bin/uv run pytest tests/unit/

# E2E tests only
/home/vscode/.local/bin/uv run pytest tests/e2e/

# Specific module
/home/vscode/.local/bin/uv run pytest tests/unit/services/test_collector.py

# With coverage
/home/vscode/.local/bin/uv run pytest --cov=app --cov-report=html

# Verbose output
/home/vscode/.local/bin/uv run pytest -v
```

## Coverage Requirements

- **Minimum**: 80% overall
- **Core business logic**: 90%+

## Shared Fixtures (E2E)

Available in `tests/e2e/conftest.py`:

- `temp_output_dir` - Temporary directory (auto-cleanup)
- `skip_without_ffmpeg` - Skip if FFmpeg not installed
- `create_raw_topic()` - Factory for RawTopic DTOs
- `create_normalized_topic()` - Factory for NormalizedTopic DTOs
- `create_scored_topic()` - Factory for ScoredTopic DTOs

## Mocking External Services

Tests use mocked LLM/external services (no API keys needed):

```python
from unittest.mock import AsyncMock, patch

@patch("app.infrastructure.llm.get_llm_client")
async def test_generation(mock_client):
    mock_client.return_value.complete = AsyncMock(
        return_value=LLMResponse(content="mocked", ...)
    )
    # Test code
```

## DI Container Override

```python
from app.core.container import override_redis

def test_with_mock_redis():
    mock_redis = AsyncMock()
    with override_redis(mock_redis):
        # All Redis access uses mock
        ...
```

## E2E Test Categories

| File | Description |
|------|-------------|
| `test_video_generation.py` | TTS, subtitles, visuals, thumbnails, FFmpeg |
| `test_content_collection.py` | Normalization, dedup, filter, score |
| `test_full_pipeline.py` | Persona-based, batch generation, RAG |

## Prerequisites

- FFmpeg installed (DevContainer includes by default)
- No external API keys required for tests
