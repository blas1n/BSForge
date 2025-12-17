# app/services/CLAUDE.md - Service Implementation Patterns

## Service Structure

Each service domain has its own directory:

```
services/
├── collector/    # Topic collection pipeline
├── rag/          # Persona RAG system
└── generator/    # Video generation
```

## Adding New Services

### New Source (collector)

1. Create in `app/services/collector/sources/`
2. Implement `BaseSource` interface
3. Register in source factory
4. Add config in `config/examples/`

### New TTS Provider (generator)

1. Create in `app/services/generator/tts/`
2. Implement `BaseTTSEngine` interface
3. Register in TTS factory
4. Add env vars to `.env.example`

## Collector Pipeline

**Flow**: Source → Normalize → Deduplicate → Filter → Score → Queue

- `RawTopic` → `NormalizedTopic` → `ScoredTopic`
- Uses Redis for deduplication and priority queue
- Global pool for shared sources (HN, YouTube Trends)

## RAG System

**Current**: Semantic search only (pgvector)
**Planned**: Hybrid search (70% semantic + 30% BM25) - BM25 not yet implemented

Key components:
- `ContentEmbedder` - BGE-M3 embeddings with metadata tags
- `RAGRetriever` - Semantic search with query expansion
- `RAGReranker` - BGE-Reranker + MMR diversity
- `ScriptGenerator` - Full pipeline with quality gates

**Quality Gates**: style_score >= 0.7, hook_score >= 0.5

### RAG TODOs

- [ ] Implement BM25 keyword search
- [ ] Hybrid search combining semantic + BM25
- [ ] Performance tuning for larger corpus

## Generator Pipeline

**Flow**: Script → TTS → Subtitles → Visuals → FFmpeg → Thumbnail

Visual sourcing priority: stock_video → stock_image → ai_image → fallback

Scene types: HOOK, INTRO, CONTENT, EXAMPLE, COMMENTARY, REACTION, CONCLUSION, CTA

Visual styles: NEUTRAL (facts), PERSONA (opinions), EMPHASIS (conclusions)

### Generator TODOs

- [ ] BGM (Background Music) system
- [ ] Audio mixing with configurable volume
- [ ] License-aware music selection

## Common Patterns

### Async Service Pattern

```python
class MyService:
    def __init__(self, redis: AsyncRedis, config: MyConfig):
        self.redis = redis
        self.config = config

    async def process(self, item: Item) -> Result:
        # Implementation
        ...
```

### Factory Pattern

```python
class EngineFactory:
    _instances: dict[str, Engine] = {}

    @classmethod
    def get(cls, provider: str) -> Engine:
        if provider not in cls._instances:
            cls._instances[provider] = cls._create(provider)
        return cls._instances[provider]
```

### Pipeline Pattern

```python
async def run_pipeline(input: Input) -> Output:
    step1_result = await self.step1.process(input)
    step2_result = await self.step2.process(step1_result)
    return await self.step3.process(step2_result)
```
