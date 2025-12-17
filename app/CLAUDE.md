# app/CLAUDE.md - Code Conventions

## Python Style

```python
# Type hints everywhere
async def generate_script(
    topic: Topic,
    config: GenerationConfig,
) -> GeneratedScript:
    ...

# Pydantic for data models
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

## Naming Conventions

- Files: `snake_case.py`
- Classes: `PascalCase`
- Functions/Variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Private: `_leading_underscore`

## Import Rules

```python
# 1. Standard library
import asyncio
from pathlib import Path

# 2. Third-party
from fastapi import Depends
from pydantic import BaseModel

# 3. Local
from app.core.config import settings
from app.models import Topic
```

- All imports at module top level (no function-level imports)
- Solve circular imports by design (fix dependency direction)
- Use `TYPE_CHECKING` for type-only imports

## Exception Handling

All exceptions inherit from `BSForgeError` in `app/core/exceptions.py`:

```python
from app.core.exceptions import RecordNotFoundError, ExternalAPIError

# Raise with context
raise RecordNotFoundError(model="Topic", record_id="abc-123")

# Chain additional context
raise ExternalAPIError(
    service="Pexels",
    message="Rate limited",
    status_code=429,
).with_context(endpoint="/videos/search")
```

**Hierarchy**:
- `DatabaseError` → `RecordNotFoundError`, `RecordAlreadyExistsError`
- `ConfigError` → `ConfigValidationError`, `ConfigNotFoundError`
- `ServiceError` → `ExternalAPIError`, `RateLimitError`
- `ContentError` → `ContentGenerationError`, `UnsafeContentError`
- `VideoError` → `TTSError`, `VideoRenderError`

## Dependency Injection

Uses `dependency-injector` with ASP.NET Core-style lifecycles:

```python
# FastAPI endpoints
from app.core.container import get_redis, get_db_session

@router.get("/items")
async def get_items(
    redis: AsyncRedis = Depends(get_redis),
    db: AsyncSession = Depends(get_db_session),
):
    ...

# Services - inject via constructor
class TopicDeduplicator:
    def __init__(self, redis: AsyncRedis):
        self.redis = redis

# Instantiate via container
from app.core.container import container
deduplicator = container.deduplicator()

# Celery tasks - use TaskScope
from app.core.container import TaskScope

@celery_app.task
def process_topic():
    with TaskScope() as scope:
        service = scope.some_service()
        ...
```

**Container Structure**:
- `InfrastructureContainer`: Redis, Database, VectorDB (Singletons)
- `ConfigContainer`: Pydantic config models (Singletons)
- `ServiceContainer`: Business services (Factories)

## Type Hints (Strict)

```python
# Generic types must have parameters
def get_items() -> dict[str, Any]: ...  # Good
def get_items() -> dict: ...            # Bad

# Union types - use hasattr check
content_block = response.content[0]
if not hasattr(content_block, "text"):
    raise ValueError(f"Unexpected: {type(content_block)}")
text = content_block.text

# TYPE_CHECKING for circular imports
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.services.rag.classifier import ContentClassifier
```

## Prompt Templates

All prompts in `app/prompts/templates/*.yaml`:
- Model configuration per template (`model`, `max_tokens`, `temperature`)
- Use Mako template syntax
- No hardcoded prompts in code
