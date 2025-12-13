# CLAUDE.md - BSForge Project Context

## Project Overview

**BSForge** is an AI-powered YouTube Shorts automation system that generates and uploads content automatically. The core philosophy is "Config-driven multi-channel factory" - change config, spin up a new channel.

### Goals
1. **Primary**: AI Engineer Portfolio (demonstrate E2E ML pipeline skills)
2. **Secondary**: Monetization (views, ads revenue)

### Tech Stack
- **Language**: Python 3.11+
- **Package Manager**: uv + pyproject.toml
- **Backend**: FastAPI
- **Database**: PostgreSQL 16 + pgvector + Redis 7
- **Vector Search**: pgvector (PostgreSQL extension with HNSW index)
- **LLM**: Claude API via LangChain
- **Embedding**: BGE-M3 (HuggingFace)
- **TTS**: Edge TTS (free) / ElevenLabs (premium)
- **Video**: FFmpeg
- **Queue**: Celery + Redis
- **Dashboard**: React + TypeScript

---

## Development Principles

### 1. 100% Environment Isolation
- **All dependencies in DevContainer**: PostgreSQL, Redis, FFmpeg, Python packages
- **No external setup required**: DevContainer Open → Immediate development
- **Zero host pollution**: Everything runs inside Docker

### 2. Package Management
- **uv-based**: Fast, modern Python package installer
- **pyproject.toml only**: No requirements.txt
- **Auto-install on container open**: postCreateCommand handles everything

### 3. Incremental Construction
- **No upfront scaffolding**: Create files/folders only when needed
- **Models per feature**: DB models created alongside the feature that uses them
- **Branch-based development**: Each feature in its own branch

### 4. Testing & Documentation First
- **Minimum 80% coverage**: 90%+ for core business logic
- **Google-style docstrings**: Required for all functions/classes
- **Test before merge**: All PRs must pass tests

### 5. Branch Strategy
```
main (protected)
├── feature/foundation          → Base + DevContainer integration
├── feature/config-system       → YAML config loader
├── feature/topic-collection    → Topic collection (creates Channel, Source, Topic models)
├── feature/rag-system          → RAG (creates ContentChunk, Script models)
├── feature/video-generation    → Video gen (creates Video model)
├── feature/upload-analytics    → Upload (creates Upload, Performance, Series models)
├── feature/ab-testing          → A/B testing (creates Experiment models)
├── feature/review-system       → Review (creates ReviewQueue model)
├── feature/api-layer           → FastAPI endpoints
├── feature/workers             → Celery tasks (creates JobLog model)
└── feature/dashboard           → React UI
```

---

## Project Structure

```
bsforge/
├── app/
│   ├── api/                  # FastAPI routers
│   │   ├── v1/
│   │   │   ├── channels.py
│   │   │   ├── review.py
│   │   │   ├── stats.py
│   │   │   └── auth.py
│   │   └── deps.py           # Dependencies
│   ├── config/               # Channel config models (Pydantic)
│   │   ├── __init__.py       # ChannelConfig
│   │   ├── channel.py        # ChannelInfo, YouTubeConfig
│   │   ├── persona.py        # PersonaConfig, VoiceConfig, etc.
│   │   ├── content.py        # ContentConfig, ScoringConfig, etc.
│   │   └── operation.py      # OperationConfig, ReviewGates, etc.
│   ├── core/
│   │   ├── config.py         # App settings (pydantic-settings)
│   │   ├── config_loader.py  # YAML config loader & manager
│   │   ├── database.py       # SQLAlchemy setup
│   │   ├── redis.py          # Redis client
│   │   ├── logging.py        # Logging setup
│   │   └── exceptions.py     # Custom exceptions
│   ├── models/               # SQLAlchemy ORM models
│   │   ├── base.py           # UUIDMixin, TimestampMixin
│   │   ├── channel.py
│   │   ├── topic.py
│   │   ├── script.py
│   │   ├── video.py
│   │   ├── upload.py
│   │   └── ...
│   ├── schemas/              # API request/response schemas (Pydantic)
│   │   └── ...               # (to be added in API layer phase)
│   ├── services/
│   │   ├── collector/        # Topic collection
│   │   │   ├── sources/      # Source implementations
│   │   │   ├── normalizer.py
│   │   │   ├── deduplicator.py
│   │   │   └── scorer.py
│   │   ├── rag/              # Persona RAG system
│   │   │   ├── embedder.py
│   │   │   ├── retriever.py
│   │   │   ├── reranker.py
│   │   │   └── generator.py
│   │   ├── generator/        # Video generation
│   │   │   ├── tts.py
│   │   │   ├── subtitle.py
│   │   │   ├── visual.py
│   │   │   └── compositor.py
│   │   ├── uploader/         # YouTube upload
│   │   │   ├── youtube.py
│   │   │   ├── metadata.py
│   │   │   └── scheduler.py
│   │   ├── analyzer/         # Analytics
│   │   │   ├── performance.py
│   │   │   └── series.py
│   │   └── filter/           # Content filter
│   │       ├── keyword.py
│   │       └── llm.py
│   ├── workers/              # Celery tasks
│   │   ├── collect.py
│   │   ├── generate.py
│   │   ├── upload.py
│   │   └── sync.py
│   └── main.py               # FastAPI app
├── config/
│   ├── examples/             # Example configs (public)
│   ├── channels/             # Channel configs (gitignored)
│   └── sources/              # Source configs (gitignored)
├── dashboard/                # React frontend
├── architecture/             # Design documents
├── alembic/                  # DB migrations
├── tests/
├── scripts/                  # CLI utilities
└── docker/
```

---

## Key Design Decisions

### 1. Config-Driven Architecture
Everything is configurable via YAML files:
- Channel settings (topic scope, upload frequency)
- Persona (voice, tone, speaking patterns)
- Source weights and filters
- Operation mode (manual/auto review)

### 2. Persona RAG System
- **Hybrid Search**: Semantic (70%) + BM25 (30%)
- **Reranking**: BGE-Reranker for precision
- **MMR**: Diversity in retrieved chunks
- Maintains consistent voice/style per channel

### 3. Review Pipeline
Four review gates: Topic → Script → Video → Upload
Each can be: `auto`, `manual`, or `hybrid`

### 4. Series Auto-Detection
Two-part system for series management:

**SeriesMatcher** (Phase 3 - Implemented):
- Matches new topics to existing configured series
- Uses keyword/category overlap with configurable similarity threshold
- Provides score boost for matched series topics

**SeriesDetector** (Phase 6 - Deferred):
- Auto-detects high-performing content patterns from analytics data
- Requires Performance data from YouTube Analytics
- Clusters videos by keywords/categories
- Suggests new series when: 3+ videos, >5% engagement rate
- Creates `SeriesConfig` suggestions for user confirmation

### 5. A/B Testing System
When channel performance is low, run experiments to optimize:
- **Testable variables**: Hook style, title format, thumbnail, TTS voice, upload time, etc.
- **Statistical analysis**: Welch's t-test, confidence intervals, effect size
- **Auto-conclude**: When sufficient samples + significant results
- **Auto-apply**: Winner variant automatically applied to channel config

---

## Code Conventions

### Python Style
```python
# Use type hints everywhere
async def generate_script(
    topic: Topic,
    persona: Persona,
    config: GenerationConfig,
) -> GeneratedScript:
    ...

# Pydantic for all data models
class TopicCreate(BaseModel):
    title: str
    source_url: HttpUrl
    keywords: list[str] = []

# SQLAlchemy 2.0 style
class Topic(Base):
    __tablename__ = "topics"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
```

### Naming Conventions
- Files: `snake_case.py`
- Classes: `PascalCase`
- Functions/Variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Private: `_leading_underscore`

### Import Order
```python
# 1. Standard library
import asyncio
from datetime import datetime
from pathlib import Path

# 2. Third-party
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

# 3. Local
from app.core.config import settings
from app.models import Topic
from app.services.collector import TopicCollector
```

### Import Location
- **All imports must be at module top level**
- No function-level imports (hurts readability, IDE autocomplete)
- Solve circular imports by design (fix dependency direction)

### Error Handling
```python
# Use custom exceptions
class BSForgeError(Exception):
    """Base exception"""
    pass

class TopicNotFoundError(BSForgeError):
    """Topic not found"""
    pass

# Always log errors with context
logger.error(
    "Failed to generate script",
    extra={"topic_id": topic.id, "channel_id": channel.id},
    exc_info=True,
)
```

### Dependency Injection
Uses `dependency-injector` with ASP.NET Core-style lifecycles:
- **Singleton**: One instance for entire app (Redis, DB engine)
- **Scoped**: One instance per request/task (DB session)
- **Transient/Factory**: New instance each time (Services)

```python
# In FastAPI endpoints - use Depends
from app.core.container import get_redis, get_db_session

@router.get("/items")
async def get_items(
    redis: AsyncRedis = Depends(get_redis),
    db: AsyncSession = Depends(get_db_session),
):
    ...

# In services - inject via constructor
class TopicDeduplicator:
    def __init__(self, redis: AsyncRedis):
        self.redis = redis

# Instantiate services via container
from app.core.container import container

deduplicator = container.deduplicator()  # Redis auto-injected
scorer = container.scorer()

# In Celery tasks - use TaskScope
from app.core.container import TaskScope

@celery_app.task
def process_topic():
    with TaskScope() as scope:
        deduplicator = scope.deduplicator()
        ...

# In tests - use override
from app.core.container import override_redis

def test_something():
    mock_redis = AsyncMock()
    with override_redis(mock_redis):
        # All Redis access uses mock
        ...
```

Container structure:
- `InfrastructureContainer`: Redis, Database, VectorDB (Singletons)
- `ConfigContainer`: Pydantic config models (Singletons)
- `ServiceContainer`: Business services (Factories)
- `ApplicationContainer`: Root container with convenience accessors

---

## Code Quality Standards

### Required Tools
Before committing, always run:
```bash
ruff check app/         # Linting (must pass: 0 errors)
mypy app/               # Type checking (must pass: 0 errors)
pytest tests/           # Tests (must pass)
```

### Type Hints (Strict)
All code must have complete type annotations:

```python
# ✅ Good - Full type hints
def process_topic(
    topic_id: uuid.UUID,
    config: ProcessConfig,
) -> ProcessResult:
    ...

async def fetch_data(url: str) -> dict[str, Any]:
    ...

# ❌ Bad - Missing types
def process_topic(topic_id, config):
    ...
```

**Generic types must have parameters:**
```python
# ✅ Good
def get_items() -> dict[str, Any]: ...
def get_names() -> list[str]: ...

# ❌ Bad - Missing type parameters
def get_items() -> dict: ...
def get_names() -> list: ...
```

**Union types with external libraries:**
```python
# When accessing attributes on union types (e.g., anthropic API responses)
content_block = response.content[0]
if not hasattr(content_block, "text"):
    raise ValueError(f"Unexpected type: {type(content_block)}")
text = content_block.text  # Now safe to access
```

### Common Patterns

**TYPE_CHECKING for circular imports:**
```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.rag.classifier import ContentClassifier

class ScriptChunker:
    def __init__(self, classifier: "ContentClassifier | None" = None):
        ...
```

**Explicit casts for library limitations:**
```python
# Mako template returns Any
return str(rendered).strip()

# numpy array type inference
return similarities.astype(np.float64)  # type: ignore[no-any-return]
```

### Ruff Rules
Key rules enforced:
- `F401`: No unused imports
- `F821`: No undefined names
- `E501`: Line length ≤ 88 chars
- `I001`: Import sorting (isort)

### MyPy Configuration
Strict mode enabled. Common fixes:
| Error | Fix |
|-------|-----|
| `Missing type parameters for generic type` | Use `dict[str, Any]` not `dict` |
| `Function is missing a return type` | Add `-> ReturnType` or `-> None` |
| `Returning Any from function` | Use explicit `str()`, `float()` cast |
| `has no attribute` on union | Use `hasattr()` check or `isinstance()` |

### Pre-commit Checklist
- [ ] `ruff check app/` passes with 0 errors
- [ ] `mypy app/` passes with 0 errors
- [ ] All new functions have type hints
- [ ] All new functions have docstrings (Google style)
- [ ] No hardcoded prompts (use `app/prompts/templates/`)
- [ ] No hardcoded patterns (use config)

---

## Database Schema Overview

### Core Tables (Created Incrementally)

Models are created alongside the features that use them:

**Phase 3: Topic Collection**
- `channels` - YouTube channel configs
- `personas` - Channel personas (1:1 with channel)
- `sources` - Topic sources (Reddit, HN, etc.)
- `topics` - Collected topics

**Phase 4: RAG System** ✅ COMPLETED
- `scripts` - Generated scripts
  - hook, body, conclusion 섹션 분리
  - quality_passed, style_score, hook_score 등 품질 메트릭
  - status: GENERATED, REVIEWED, APPROVED, REJECTED, PRODUCED
- `content_chunks` - 벡터 검색용 청크
  - embedding: Vector(1024) - BGE-M3 임베딩
  - is_opinion, is_example, is_analogy - 콘텐츠 특성 (패턴/LLM 분류)
  - position: HOOK, BODY, CONCLUSION
  - HNSW 인덱스: `CREATE INDEX USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)`

**Phase 5: Video Generation**
- `videos` - Generated videos

**Phase 6: Upload & Analytics**
- `uploads` - YouTube uploads
- `performances` - Video analytics
- `series` - Auto-detected series

**Phase 7: A/B Testing**
- `experiments` - A/B test experiments
- `experiment_assignments` - Variant assignments

**Phase 8: Review System**
- `review_queue` - Review items

**Phase 10: Workers**
- `job_logs` - Task logs

### Key Relationships
```
Channel 1:1 Persona
Channel 1:N Topics
Channel M:N Sources (via channel_sources)
Topic 1:N Scripts
Script 1:N Videos
Video 1:1 Upload
Upload 1:1 Performance
Channel 1:N Series
Series 1:N Topics
```

See [architecture/06-database-schema.md](./architecture/06-database-schema.md) for complete schema.

---

## Common Tasks

### Adding a New Source
1. Create source class in `app/services/collector/sources/`
2. Implement `BaseSource` interface
3. Register in source factory
4. Add example config in `config/examples/`

### Adding a New TTS Provider
1. Create engine in `app/services/generator/tts/`
2. Implement `BaseTTSEngine` interface
3. Register in TTS factory
4. Add env vars to `.env.example`

### Creating a Migration
```bash
alembic revision --autogenerate -m "Add new_column to topics"
alembic upgrade head
```

### Running Tests
```bash
# All tests
pytest

# Specific module
pytest tests/services/test_collector.py

# With coverage
pytest --cov=app --cov-report=html
```

---

## Environment Variables

Critical env vars (see `.env.example` for full list):
- `DATABASE_URL` - PostgreSQL connection
- `REDIS_URL` - Redis connection
- `ANTHROPIC_API_KEY` - Claude API
- `GOOGLE_CLIENT_ID/SECRET` - YouTube OAuth
- `ELEVENLABS_API_KEY` - Premium TTS
- `PEXELS_API_KEY` - Stock visuals

---

## API Endpoints Overview

```
POST   /api/v1/auth/login
GET    /api/v1/channels
POST   /api/v1/channels
GET    /api/v1/channels/{id}

GET    /api/v1/review/queue
GET    /api/v1/review/queue/{id}
POST   /api/v1/review/queue/{id}/action

GET    /api/v1/stats/overview
GET    /api/v1/stats/channel/{id}

WS     /ws/{channel_id}  # Real-time notifications
```

---

## Performance Considerations

### Database
- Use `select_in_load` for relationships
- Index frequently queried columns (see schema doc)
- Use Redis for caching hot data

### Vector Search (pgvector + HNSW)
- **HNSW Index**: 1000x faster than brute force, 99%+ accuracy
  - Parameters: m=16 (connections per node), ef_construction=64 (build quality)
  - Approximate nearest neighbor search: O(log n) vs O(n)
- **Batch embeddings** (32 texts per batch for BGE-M3)
- **Hybrid search**: 70% semantic (vector) + 30% BM25 (keyword)
- **MMR diversity**: λ=0.7 balances relevance and diversity
- **Content classification**: Pattern-based (fast) + optional LLM (accurate)

### Video Generation
- Process in background (Celery)
- Stream large file uploads
- Clean up temp files

---

## Security Notes

### Gitignored (Private Data)
- `.env` - API keys
- `config/channels/` - Real channel configs
- `config/sources/` - Crawl targets
- `data/` - Collected data
- `datasets/` - Fine-tuning data
- `outputs/` - Generated content

### Public (Open Source)
- All source code
- Architecture docs
- Example configs (`*.example.*`)

---

## DevContainer Setup

### Automatic Environment Setup

**DevContainer Open → Ready to Code**

The DevContainer automatically:
1. Installs uv package manager
2. Installs all dependencies via `uv pip install -e ".[dev]"`
3. Sets up pre-commit hooks
4. Configures VSCode extensions

### Container Services
- **PostgreSQL 16**: Available at `localhost:5432`
- **Redis 7**: Available at `localhost:6379`
- **FFmpeg**: Pre-installed in container

### Configuration Files
- `.devcontainer/devcontainer.json` - Container config with postCreateCommand
- `.devcontainer/scripts/post-create.sh` - Auto-setup script
- `.devcontainer/docker-compose.yml` - PostgreSQL + Redis services

---

## Useful Commands

```bash
# Development (uses Makefile with uv)
make install-dev    # Install dependencies
make dev            # Start FastAPI dev server
make worker         # Start Celery worker
make beat           # Start Celery beat scheduler
make test           # Run tests
make lint           # Run linters (ruff, mypy)
make format         # Format code (black, ruff)

# Database migrations
make migrate msg="Add new feature"  # Create migration
make upgrade                        # Apply migrations

# Direct commands (if not using Makefile)
uv pip install -e ".[dev]"                    # Install deps
uvicorn app.main:app --reload                 # Dev server
celery -A app.workers.celery_app worker -l info  # Worker
pytest                                        # Tests
```

---

## Design Documents

Detailed designs are in `architecture/`:
- `02-topic-collection.md` - Topic collection pipeline
- `03-persona-rag.md` - RAG system design
- `04-video-generation.md` - Video generation pipeline
- `05-upload-scheduling.md` - Upload & optimal time
- `06-database-schema.md` - Full DB schema
- `07-review-dashboard.md` - Dashboard system
- `08-ab-testing.md` - A/B testing system

---

## Current Status & TODO

**Current Phase**: Phase 4 (RAG System) - Completed ✅

### Phase 1-2: Foundation (Completed)
- [x] Project scaffolding (FastAPI + SQLAlchemy)
- [x] DevContainer setup
- [x] Config system (Pydantic models, YAML loader)
- [x] DI Container (dependency-injector)
- [x] DB models (Channel, Source, Topic)
- [x] Core utilities (logging, exceptions, redis)

### Phase 3: Topic Collection (Completed)
- [x] 3.1 Base DTOs & Source interface (`RawTopic`, `NormalizedTopic`, `ScoredTopic`, `BaseSource`)
- [x] 3.2 Normalization (`TopicNormalizer` - translation, classification)
- [x] 3.3 Deduplication (`TopicDeduplicator` - hash-only for exact duplicate filtering)
- [x] 3.4 Filtering (`TopicFilter` - category/keyword include/exclude filters)
- [x] 3.5 Scoring (`TopicScorer` - multi-factor scoring)
- [x] 3.6 Queue Management (`TopicQueueManager` - Redis priority queue)
- [x] 3.7 Series Matcher (`SeriesMatcher` - topic-to-series matching)
- [x] 3.8 Source Implementations (Reddit, HN, RSS, YouTube, Google Trends, DCInside, Clien)
- [x] 3.9 Collection Scheduler (Celery-based scheduling)
- [x] 3.10 Hybrid Collection System (Global Pool + Scoped Sources)
  - [x] GlobalTopicPool (Redis-based shared pool for HN, Trends, YouTube)
  - [x] GlobalCollector task (collect once, share across channels)

### Phase 4: RAG System (Completed ✅)
- [x] 4.1 Database Models
  - [x] `Script` model (hook, body, conclusion, quality metrics, status)
  - [x] `ContentChunk` model (embedding, characteristics, position)
  - [x] Alembic migration with pgvector extension
  - [x] HNSW index for vector similarity search
- [x] 4.2 RAG Configuration (`app/config/rag.py`)
  - [x] EmbeddingConfig (BGE-M3 settings)
  - [x] RetrievalConfig (hybrid search, MMR, reranking)
  - [x] ChunkingConfig (patterns, LLM classification)
  - [x] QualityCheckConfig (quality gates)
  - [x] GenerationConfig (LLM settings)
- [x] 4.3 Vector Database Infrastructure
  - [x] PgVectorDB (pgvector implementation with HNSW)
  - [x] BGE-M3 embedding integration
- [x] 4.4 RAG Services
  - [x] ContentEmbedder (메타데이터 태그 추가, 배치 처리)
  - [x] RAGRetriever / SpecializedRetriever (하이브리드 검색, 쿼리 확장)
  - [x] RAGReranker (BGE-Reranker, MMR diversity)
  - [x] ContentClassifier (LLM 기반 분류, Claude Haiku)
  - [x] ScriptChunker (구조 기반 청킹, 설정 가능한 패턴)
  - [x] ContextBuilder (병렬 검색, Persona 통합)
  - [x] PromptBuilder (프롬프트 템플릿)
  - [x] ScriptGenerator (전체 파이프라인, 품질 게이트)
- [x] 4.5 DI Container Integration
  - [x] ConfigContainer with RAG configs
  - [x] ServiceContainer with RAG services
  - [x] ApplicationContainer convenience accessors

**Key Features**:
- **Hybrid Search**: 70% semantic (pgvector) + 30% BM25 (keyword)
- **HNSW Index**: 1000x faster vector search with 99%+ accuracy
- **Extensible Classification**: Configurable pattern matching + optional LLM (Claude Haiku)
- **Quality Gates**: style_score ≥ 0.7, hook_score ≥ 0.5, max 2 forbidden words
- **Multi-language Support**: Pattern configs support Korean, English, easily extensible

### Phase 5: Video Generation
- [ ] 5.1 TTS engine (Edge TTS / ElevenLabs)
- [ ] 5.2 Subtitle generator
- [ ] 5.3 Visual selector (stock video/image)
- [ ] 5.4 Video compositor (FFmpeg)

### Phase 6: Upload & Analytics
- [ ] 6.1 YouTube API integration
- [ ] 6.2 Metadata generator
- [ ] 6.3 Upload scheduler
- [ ] 6.4 Analytics sync
- [ ] 6.5 Series Detector (`SeriesDetector` - auto-detect series from performance data)
  - Clusters high-performing videos by keywords/categories
  - Requires 3+ videos with >5% engagement rate
  - Creates `SeriesConfig` suggestions for user confirmation
  - Location: `app/services/analyzer/series_detector.py`

### Phase 7-11: Later Phases
- [ ] Phase 7: A/B Testing system
- [ ] Phase 8: Review system
- [ ] Phase 9: API Layer (FastAPI endpoints)
- [ ] Phase 10: Workers (Celery tasks)
- [ ] Phase 11: Dashboard (React UI)

---

## Contact

For questions about this codebase, check the architecture docs first.
