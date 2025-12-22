# 🔥 BSForge

**AI-Powered YouTube Shorts Factory**

> Change the config, spin up a new channel.

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 🎯 Overview

BSForge is an **end-to-end pipeline for automated YouTube Shorts content creation and publishing**.

```
Topic Collection → Script Generation → Video Production → Optimal Upload → Analytics → Feedback Loop
```

### ✨ Key Features

- **🔄 Multi-Channel**: Config-driven infinite scalability
- **🎭 Persona RAG**: Consistent voice and perspective per channel
- **📊 Auto-Series Detection**: Identify high-performing content patterns automatically
- **⏰ Optimal Timing**: YouTube Analytics-based upload scheduling
- **🛡️ AI Content Filter**: Risk detection and review pipeline
- **🧪 A/B Testing**: Data-driven optimization for underperforming channels
- **🔁 Self-Improving**: Automatic fine-tuning data collection

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                       BSForge System                         │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐        │
│  │ Config  │→ │ Collect │→ │  RAG    │→ │ Filter  │        │
│  │ Layer   │  │ Topics  │  │ Script  │  │ Content │        │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘        │
│       │            │            │            │              │
│       ▼            ▼            ▼            ▼              │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐        │
│  │ Channel │  │ Source  │  │ Persona │  │ Review  │        │
│  │ Persona │  │ Parser  │  │ Vector  │  │ Queue   │        │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘        │
│                                                             │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐        │
│  │ Video   │→ │ Upload  │→ │Analytics│→ │Feedback │        │
│  │ Generate│  │Schedule │  │ Sync    │  │ Loop    │        │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘        │
└─────────────────────────────────────────────────────────────┘
```

See [architecture/](./architecture/) for detailed design documents.

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|------------|
| **Language** | Python 3.11+ |
| **Package Manager** | uv + pyproject.toml |
| **Backend** | FastAPI |
| **Database** | PostgreSQL 16 + pgvector + Redis 7 |
| **Vector Search** | pgvector (HNSW index) |
| **Embedding** | BGE-M3 (HuggingFace) |
| **LLM** | LiteLLM (Anthropic, OpenAI, Gemini) |
| **TTS** | Edge TTS / ElevenLabs |
| **BGM** | yt-dlp (YouTube audio extraction) |
| **Video** | FFmpeg |
| **Queue** | Celery + Redis |
| **Dashboard** | React + TypeScript |
| **Environment** | Docker + DevContainer (100% isolated) |

---

## 🚀 Quick Start

### Prerequisites

- **Docker Desktop** (for DevContainer)
- **VSCode** with Dev Containers extension

That's it! Everything else is handled automatically.

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/bsforge.git
cd bsforge

# 2. Open in VSCode
code .

# 3. Reopen in DevContainer
# VSCode will prompt: "Reopen in Container" → Click it
# Or use Command Palette: "Dev Containers: Reopen in Container"

# 4. Wait for automatic setup (first time only)
# - uv installation
# - Package installation
# - Database initialization
# - Pre-commit hooks

# 5. Start developing!
make dev
```

### What Happens Automatically

When you open the DevContainer:
1. ✅ PostgreSQL 16 starts
2. ✅ Redis 7 starts
3. ✅ uv gets installed
4. ✅ All Python dependencies install via `uv pip install -e ".[dev]"`
5. ✅ Pre-commit hooks configure
6. ✅ VSCode extensions activate

**No manual setup. No host pollution. 100% isolated.**

### Channel Setup

```bash
# Create channel configuration
cp config/examples/channel.example.yaml config/channels/my-channel.yaml
# Edit with your channel settings

# Register the channel (once implemented)
python -m app.cli channel register my-channel
```

### Development Commands

```bash
make dev            # Start FastAPI server
make worker         # Start Celery worker
make test           # Run tests
make lint           # Run linters
make format         # Format code
make migrate        # Create migration
make upgrade        # Apply migrations
```

---

## 📁 Project Structure

```
bsforge/
├── app/
│   ├── api/                   # FastAPI routers
│   ├── config/                # Channel config models (Pydantic)
│   │   ├── channel.py         # ChannelInfo, YouTubeConfig
│   │   ├── persona.py         # PersonaConfig, VoiceConfig
│   │   ├── content.py         # ContentConfig, ScoringConfig
│   │   └── operation.py       # OperationConfig, ReviewGates
│   ├── core/                  # Core utilities
│   │   ├── config.py          # App settings (env-based)
│   │   ├── config_loader.py   # YAML config loader
│   │   ├── database.py        # SQLAlchemy setup
│   │   ├── redis.py           # Redis client
│   │   ├── logging.py         # Logging setup
│   │   └── exceptions.py      # Custom exceptions
│   ├── models/                # SQLAlchemy ORM models
│   │   ├── base.py            # Base mixins
│   │   └── ...                # (created per feature)
│   ├── schemas/               # API request/response schemas
│   │   └── ...                # (Pydantic, to be added)
│   ├── services/
│   │   ├── collector/         # Topic collection
│   │   ├── rag/               # Persona RAG
│   │   ├── generator/         # Video generation (TTS, visual, bgm, ffmpeg)
│   │   ├── uploader/          # YouTube upload (Phase 6)
│   │   └── analyzer/          # Analytics (Phase 6)
│   ├── workers/               # Celery tasks
│   └── main.py                # FastAPI app
├── config/
│   ├── examples/              # Example configs (public)
│   ├── channels/              # Channel configs (private)
│   └── sources/               # Source configs (private)
├── dashboard/                 # React frontend
├── architecture/              # Design documents
├── tests/
│   ├── unit/
│   │   ├── config/            # Config model tests
│   │   ├── core/              # Core utility tests
│   │   └── ...
│   └── integration/
├── alembic/                   # DB migrations
├── .devcontainer/             # DevContainer setup
├── .env.example
├── .gitignore
├── CLAUDE.md                  # Claude Code context
├── pyproject.toml             # Package config (uv)
└── README.md
```

---

## 📖 Documentation

| Document | Description |
|----------|-------------|
| [PROJECT_PLAN.md](./PROJECT_PLAN.md) | Project planning document |
| [CLAUDE.md](./CLAUDE.md) | Development context for Claude Code |
| [architecture/](./architecture/) | System design documents |

### Architecture Documents

| File | Description |
|------|-------------|
| [02-topic-collection.md](./architecture/02-topic-collection.md) | Topic collection pipeline |
| [03-persona-rag.md](./architecture/03-persona-rag.md) | Persona RAG system |
| [04-video-generation.md](./architecture/04-video-generation.md) | Video generation pipeline |
| [05-upload-scheduling.md](./architecture/05-upload-scheduling.md) | Upload & optimal timing |
| [06-database-schema.md](./architecture/06-database-schema.md) | Database schema |
| [07-review-dashboard.md](./architecture/07-review-dashboard.md) | Review dashboard |
| [08-ab-testing.md](./architecture/08-ab-testing.md) | A/B testing system |

---

## 🎨 Pipeline Overview

### 1️⃣ Topic Collection
- Aggregate topics from domestic/international communities, news, and social media
- Normalize → Deduplicate → Score
- Priority queue based on channel relevance

### 2️⃣ Script Generation (Persona RAG) ✅
- **Hybrid search**: Semantic (70% via pgvector HNSW) + BM25 (30% keyword)
- **Reranking**: BGE-Reranker for precision
- **MMR diversity**: λ=0.7 for balanced relevance and diversity
- **Content classification**: Configurable patterns + optional LLM (Claude Haiku)
- **Quality gates**: style_score ≥ 0.7, hook_score ≥ 0.5
- Reflect high-performing content style from history

### 3️⃣ Video Generation ✅
- **Scene-based system**: SceneType (HOOK, CONTENT, COMMENTARY, REACTION, etc.)
- **Visual differentiation**: NEUTRAL (facts) vs PERSONA (opinions) styling
- **Fact→Opinion transitions**: Flash effect for AI persona commentary
- TTS: Edge TTS (free) / ElevenLabs (premium) with word-level timestamps
- Visuals: Pexels stock → AI image → Fallback (priority-based)
- FFmpeg composition + ASS subtitles with karaoke effects
- **BGM system**: YouTube-sourced royalty-free music with yt-dlp

### 4️⃣ Upload & Scheduling
- YouTube Analytics-based optimal time analysis
- Auto-generated metadata (title, description, tags)
- Scheduled publishing

### 5️⃣ Feedback Loop
- Automatic performance collection
- High-performing content → Fine-tuning dataset
- Auto-detect series patterns

### 6️⃣ A/B Testing
- Run experiments when channel underperforms
- Test hooks, titles, thumbnails, voice, timing
- Statistical significance analysis (t-test, ANOVA)
- Auto-apply winning variants to config

---

## 🔒 Privacy & Security

This project follows **open source code, private data** principles.

### Public (Included in Git)
- ✅ All source code
- ✅ Architecture documents
- ✅ Example configs (`*.example.*`)

### Private (Excluded from Git)
- ❌ API keys / credentials
- ❌ Channel configs / personas
- ❌ Collected data / analytics
- ❌ Generated content
- ❌ Fine-tuning datasets

---

## 🧪 Testing

```bash
# Run all tests
make test

# Or directly with pytest (using uv in DevContainer)
/home/vscode/.local/bin/uv run pytest

# Unit tests only
/home/vscode/.local/bin/uv run pytest tests/unit/

# E2E tests only
/home/vscode/.local/bin/uv run pytest tests/e2e/

# Run with coverage
/home/vscode/.local/bin/uv run pytest --cov=app --cov-report=html

# Verbose output
/home/vscode/.local/bin/uv run pytest -v
```

### E2E Test Structure

```
tests/e2e/
├── conftest.py              # Shared fixtures & DTO factories
├── test_video_generation.py # Video pipeline tests (TTS, subtitles, FFmpeg)
├── test_content_collection.py # Topic collection tests (normalize, filter, score)
└── test_full_pipeline.py    # End-to-end pipeline tests
```

| File | Description | Key Tests |
|------|-------------|-----------|
| `test_video_generation.py` | Video pipeline | TTS (Edge TTS), subtitles (ASS/SRT), visual fallback, thumbnail, FFmpeg composition |
| `test_content_collection.py` | Topic collection | Normalization, deduplication, filtering, scoring, full pipeline |
| `test_full_pipeline.py` | End-to-end | Persona-based script generation, topic-to-video pipeline |

**Shared Fixtures** (`conftest.py`):
- `temp_output_dir`: Temporary directory for test outputs (auto-cleanup)
- `skip_without_ffmpeg`: Skip tests requiring FFmpeg
- `create_raw_topic()`: Factory for RawTopic DTOs
- `create_normalized_topic()`: Factory for NormalizedTopic DTOs
- `create_scored_topic()`: Factory for ScoredTopic DTOs

**Prerequisites**:
- FFmpeg must be installed for video composition tests
- DevContainer includes FFmpeg by default
- Tests use mocked LLM/external services (no API keys needed)

**Testing Philosophy**:
- ✅ Minimum 80% coverage (90%+ for core logic)
- ✅ Google-style docstrings required
- ✅ Tests must pass before merging to main

---

## 🐳 DevContainer Architecture

This project uses **100% isolated DevContainer environment**:

```
.devcontainer/
├── devcontainer.json        # Container configuration
├── docker-compose.yml       # PostgreSQL + Redis services
└── scripts/
    └── post-create.sh       # Auto-setup script (uv, deps, hooks)
```

**Philosophy**: No external dependencies. Everything runs inside Docker.

```bash
# All services in DevContainer
PostgreSQL 16  → localhost:5432
Redis 7        → localhost:6379
FFmpeg         → Pre-installed in container
Python 3.11+   → With uv package manager
```

---

## 🤝 Contributing

### Development Workflow

1. Fork the repository
2. Clone and open in DevContainer (auto-installs everything)
3. Create your feature branch (`git checkout -b feature/your-feature`)
4. Implement feature with tests + docstrings
5. Run tests: `make test` (must pass with 80%+ coverage)
6. Run linters: `make lint` (must pass)
7. Commit and push your changes
8. Open a Pull Request

### Code Standards

- ✅ **Type hints**: Required for all function signatures
- ✅ **Docstrings**: Google style, required for all public functions/classes
- ✅ **Tests**: 80%+ coverage minimum
- ✅ **Formatting**: black + ruff (enforced by pre-commit)
- ✅ **Linting**: ruff + mypy (must pass)

---

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgments

- [LiteLLM](https://litellm.ai/) - Unified LLM Interface
- [HuggingFace](https://huggingface.co/) - Embedding Models
- [FFmpeg](https://ffmpeg.org/) - Video Processing
- [FastAPI](https://fastapi.tiangolo.com/) - Web Framework

---

## 📬 Contact

For questions about the codebase, please check the [CLAUDE.md](./CLAUDE.md) and architecture documents first.

---

**Built with ❤️ for AI Engineers**
