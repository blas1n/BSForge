# CLAUDE.md - BSForge Project Context

## Project Overview

**BSForge** is an AI-powered YouTube Shorts automation system. Core philosophy: "Config-driven multi-channel factory" - change config, spin up a new channel.

- **Goals**: AI Engineer Portfolio + Monetization
- **Stack**: Python 3.11+ / FastAPI / PostgreSQL 16 + pgvector / Redis 7 / Celery / React

## Quick Commands

```bash
# Package manager: uv (NOT pip)
/home/vscode/.local/bin/uv run pytest          # Run tests
/home/vscode/.local/bin/uv run ruff check app/ # Lint
/home/vscode/.local/bin/uv run mypy app/       # Type check
```

## Project Structure

```
app/
├── config/          # Channel config models (Pydantic)
├── core/            # Settings, DI container, database, exceptions
├── infrastructure/  # External clients (LLM, pgvector)
├── models/          # SQLAlchemy ORM models
├── prompts/         # Prompt templates (YAML) - includes model config
├── services/        # Business logic (collector, rag, generator w/ tts/visual/bgm)
└── workers/         # Celery tasks

config/              # YAML configs (channels/, sources/, templates/)
tests/               # Unit & E2E tests
architecture/        # Design documents (02~08-*.md)
```

## Development Principles

1. **100% DevContainer**: All deps inside Docker, no host setup
2. **uv-based**: Use `/home/vscode/.local/bin/uv`, NOT pip
3. **Incremental**: Create files only when needed
4. **Test First**: 80%+ coverage, Google-style docstrings
5. **Type Safe**: All code must have type hints, no `# type: ignore`

## Key Architecture

- **Config-Driven**: Everything via YAML (channels, personas, sources)
- **Persona RAG**: Hybrid search (70% semantic + 30% BM25) + MMR
- **Review Pipeline**: Topic -> Script -> Video -> Upload (auto/manual/hybrid)
- **LLM**: LiteLLM unified interface. Model defined per prompt template in `app/prompts/templates/*.yaml`

## Development Phases

Branch-based incremental development:

| Phase | Branch | Status | Description |
|-------|--------|--------|-------------|
| 1-2 | `feature/foundation` | Done | DevContainer, Config system, DI Container |
| 3 | `feature/topic-collection` | Done | Topic collection (DTOs, Sources, Scoring) |
| 4 | `feature/rag-system` | Done | Persona RAG (Embedding, Retrieval, Generation) |
| 5 | `feature/video-generation` | Done | Video pipeline (TTS, Subtitles, FFmpeg, Scene) |
| 6 | `feature/upload-analytics` | Next | YouTube upload, Analytics sync |
| 7 | `feature/ab-testing` | - | A/B testing for optimization |
| 8 | `feature/review-system` | - | Review queue management |
| 9 | `feature/api-layer` | - | FastAPI endpoints |
| 10 | `feature/workers` | - | Celery task management |
| 11 | `feature/dashboard` | - | React UI |

**Current**: Phase 5 Completed. Next: Phase 6 (Upload & Analytics)

## Database Tables by Phase

- **Phase 3**: `channels`, `personas`, `sources`, `topics`
- **Phase 4**: `scripts`, `content_chunks` (pgvector HNSW index)
- **Phase 5**: `videos`
- **Phase 6**: `uploads`, `performances`, `series` (TODO)
- **Phase 7**: `experiments`, `experiment_assignments` (TODO)

## Subdirectory Context

Auto-loaded when working in these directories:
- [app/CLAUDE.md](app/CLAUDE.md) - Code conventions, DI, exceptions
- [app/services/CLAUDE.md](app/services/CLAUDE.md) - Service implementation patterns
- [tests/CLAUDE.md](tests/CLAUDE.md) - Testing conventions

## Skills

Use skills for post-task verification (invoke with `/skill-name`):
- `code-quality` - Run ruff + mypy checks, fix common issues
- `pre-commit` - Full pre-commit checklist before git commit

## Reference Documents

- [architecture/06-database-schema.md](architecture/06-database-schema.md) - Full DB schema
- [architecture/03-persona-rag.md](architecture/03-persona-rag.md) - RAG system design
- [architecture/04-video-generation.md](architecture/04-video-generation.md) - Video pipeline
