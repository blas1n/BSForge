# CLAUDE.md - BSForge Project Context

## Project Overview

**BSForge** is an AI-powered YouTube Shorts automation system that generates and uploads content automatically. The core philosophy is "Config-driven multi-channel factory" - change config, spin up a new channel.

### Goals
1. **Primary**: AI Engineer Portfolio (demonstrate E2E ML pipeline skills)
2. **Secondary**: Monetization (views, ads revenue)

### Tech Stack
- **Language**: Python 3.11+
- **Backend**: FastAPI
- **Database**: PostgreSQL + Redis
- **Vector DB**: Chroma (dev) → Pinecone (prod)
- **LLM**: Claude API via LangChain
- **Embedding**: BGE-M3 (HuggingFace)
- **TTS**: Edge TTS (free) / ElevenLabs (premium)
- **Video**: FFmpeg
- **Queue**: Celery + Redis
- **Dashboard**: React + TypeScript

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
│   ├── core/
│   │   ├── config.py         # Settings (pydantic-settings)
│   │   ├── database.py       # SQLAlchemy setup
│   │   ├── redis.py          # Redis client
│   │   └── security.py       # JWT, auth
│   ├── models/               # SQLAlchemy ORM models
│   │   ├── channel.py
│   │   ├── topic.py
│   │   ├── script.py
│   │   ├── video.py
│   │   ├── upload.py
│   │   └── ...
│   ├── schemas/              # Pydantic schemas
│   │   ├── channel.py
│   │   ├── topic.py
│   │   └── ...
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
System automatically detects high-performing content patterns and suggests series based on:
- Keyword clustering
- Category overlap
- Consecutive success (3+ videos, >5% engagement)

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

---

## Database Schema Overview

### Core Tables
1. **channels** - YouTube channel configs
2. **personas** - Channel personas (1:1 with channel)
3. **sources** - Topic sources (Reddit, HN, etc.)
4. **topics** - Collected topics
5. **scripts** - Generated scripts
6. **videos** - Generated videos
7. **uploads** - YouTube uploads
8. **performances** - Video analytics
9. **series** - Auto-detected series
10. **review_queue** - Review items
11. **content_chunks** - Vector DB references
12. **job_logs** - Task logs

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

### Vector Search
- Batch embeddings (32-64 texts)
- Cache embeddings for repeated queries
- Use approximate search in production

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
- `chroma_db/` - Vector store

### Public (Open Source)
- All source code
- Architecture docs
- Example configs (`*.example.*`)

---

## Useful Commands

```bash
# Start dev server
uvicorn app.main:app --reload

# Start Celery worker
celery -A app.workers worker -l info

# Start Celery beat (scheduler)
celery -A app.workers beat -l info

# Run specific task
python -m app.cli task run collect --channel-id xxx

# Generate embeddings for channel
python -m app.cli embeddings generate --channel-id xxx

# Sync YouTube analytics
python -m app.cli analytics sync --days 7
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

---

## Current Status

**Phase**: Design Complete, Implementation Starting

### Completed
- [x] Project planning
- [x] System architecture
- [x] All component designs
- [x] DB schema design
- [x] API design

### Next Steps
1. [ ] Project scaffolding (FastAPI + SQLAlchemy)
2. [ ] DB models & migrations
3. [ ] Config loader
4. [ ] Topic collection service
5. [ ] RAG system
6. [ ] Video generation
7. [ ] YouTube upload
8. [ ] Dashboard

---

## Contact

For questions about this codebase, check the architecture docs first.
