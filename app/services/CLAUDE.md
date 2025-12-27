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

### Key Components

- **Source Factory** (`sources/factory.py`): Creates source instances from config
  - `create_source(source_name, overrides)` - Factory function for all source types
  - `collect_from_sources(sources, overrides)` - Collect from multiple sources

- **Topic Clusterer** (`clusterer.py`): Groups similar topics across sources
  - Semantic similarity using TF-IDF + cosine similarity
  - Cluster merging for multi-source topics
  - Helper functions: `cluster_topics()`, `get_best_from_clusters()`

- **Filter** (`filter.py`): Unified include/exclude filtering
  - Matches against title and terms
  - Case-insensitive matching

- **Korean Web Scraper Base** (`sources/korean_scraper_base.py`): Base class for Korean community scrapers
  - Shared methods: `_parse_number()`, `_parse_korean_relative_date()`, `_parse_date()`
  - Common `_to_raw_topic()` conversion
  - Used by: Clien, DCInside, FMKorea, Ruliweb

## RAG System

**Current**: Hybrid search (70% semantic + 30% BM25) via ParadeDB pg_search

Key components:
- `ContentEmbedder` - BGE-M3 embeddings with metadata tags
- `RAGRetriever` - Hybrid search (semantic + BM25) with query expansion
- `BM25Search` - ParadeDB pg_search for keyword matching
- `RAGReranker` - BGE-Reranker + MMR diversity
- `ScriptGenerator` - Full pipeline with quality gates

**Quality Gates**: style_score >= 0.7, hook_score >= 0.5

### RAG TODOs

- [ ] Performance tuning for larger corpus

## Generator Pipeline

**Flow**: Script → TTS → Subtitles → Visuals → FFmpeg → Thumbnail

Visual sourcing priority: stock_video → stock_image → ai_image → fallback

### Scene Model

Scene types: `HOOK`, `INTRO`, `CONTENT`, `EXAMPLE`, `COMMENTARY`, `REACTION`, `CONCLUSION`, `CTA`

Visual styles: `NEUTRAL` (facts), `PERSONA` (opinions), `EMPHASIS` (conclusions)

Key scene attributes:
- `tts_text`: Pre-processed text for TTS (pronunciation fixed)
- `subtitle_segments`: Word-level timing for karaoke subtitles
- `visual_hint`: Search keywords for visual matching
- `transition_in`/`transition_out`: Transition effects (FADE, CUT, SLIDE, etc.)

### Config Externalization

Video generator configs are now in YAML:
- `config/defaults.yaml` - Ken Burns zoom, video extensions, quality thresholds
- `config/language/korean.yaml` - Subtitle segmentation rules

### Generator TODOs

- [ ] A/B testing for video variations

## Configuration

### Config Validators (`app/config/validators.py`)

Shared validation utilities for Pydantic models:
- `validate_weights_sum()` - Ensure weights sum to 1.0
- `validate_range_list()` - Validate list values are in range, dedupe, sort
- `normalize_string_list()` - Lowercase string lists
- `normalize_string()` - Lowercase single strings

### Config Loading (`app/core/config_loader.py`)

Global config loading with caching:
- `load_defaults()` - Load `config/defaults.yaml`
- `load_language_config("korean")` - Load `config/language/korean.yaml`
- `load_quality_config()` - Load quality section from `defaults.yaml`
- `clear_config_cache()` - Clear all cached configs

## Common Patterns

### Async Service Pattern

```python
class MyService:
    def __init__(self, redis: Redis[Any], config: MyConfig):
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
