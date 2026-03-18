# Channel-Driven Demo Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor `scripts/demo_pipeline.py` to load a channel config YAML, collect real topics from Reddit/RSS (no API keys needed), normalize them with LLM, and feed real data into the script generator — so the generated video reflects actual current content instead of LLM hallucinations.

**Architecture:** The demo pipeline will: (1) load a channel config YAML that defines persona, sources, and content settings; (2) use the existing source factory (`collect_from_sources`) to fetch real topics from Reddit + RSS; (3) normalize the best topic with LLM (translate, classify, summarize); (4) pass the real topic data + persona config into script generation; (5) the rest of the pipeline (TTS → subtitles → visuals → Remotion) stays the same. No database needed — everything runs in-memory.

**Tech Stack:** Python 3.11, YAML configs, httpx (HTTPClient), feedparser, Edge TTS, Remotion

---

## Task 1: Create Demo Channel Config YAML

**Files:**
- Create: `config/channels/demo_tech.yaml`

**Step 1: Write the channel config**

```yaml
# config/channels/demo_tech.yaml
# Demo channel config — Korean tech shorts
# Uses only free sources (Reddit, RSS) — no API keys needed

channel:
  id: "demo-tech"
  name: "테크 데모"
  description: "기술 뉴스 쇼츠 데모 채널"

persona:
  name: "테크브로"
  tagline: "뻔한 소리 없이 핵심만"
  voice:
    gender: "male"
    service: "edge-tts"
    voice_id: "ko-KR-InJoonNeural"
    settings:
      speed: 1.05
      pitch: 0
  communication:
    tone: "friendly"
    formality: "semi-formal"
    speech_patterns:
      sentence_endings: ["~해요", "~거든요", "~인 거죠"]
      connectors: ["근데", "사실", "그래서"]
      emphasis_words: ["진짜", "솔직히", "핵심은"]
    avoid_patterns:
      words: ["혁신적인", "패러다임", "시너지"]
      styles: ["과도한 감탄사"]
  perspective:
    core_values: ["실용성", "솔직함", "효율"]
    contrarian_views: ["AI 만능론에 회의적", "복잡한 것보다 단순한 해결책 선호"]
  visual_style:
    accent_color: "#FF6B6B"
    secondary_color: "#4ECDC4"

topic_collection:
  target_language: ko
  sources:
    - "reddit"
    - "hn_rss"
  source_overrides:
    reddit:
      params:
        subreddits: ["programming", "technology", "MachineLearning"]
        sort: "hot"
        time: "day"
      filters:
        min_score: 50
      limit: 10
    hn_rss:
      params:
        feed_url: "https://hnrss.org/frontpage?count=10"
        name: "Hacker News"
      limit: 10

filtering:
  include: []  # accept all — demo mode
  exclude: ["nsfw", "hiring", "who is hiring"]

content:
  format: "shorts"
  target_duration: 30
  video_template: "korean_shorts_standard"
```

**Step 2: Verify YAML loads correctly**

```bash
uv run python -c "
import yaml
from pathlib import Path
cfg = yaml.safe_load(Path('config/channels/demo_tech.yaml').read_text())
print('Channel:', cfg['channel']['name'])
print('Persona:', cfg['persona']['name'])
print('Sources:', cfg['topic_collection']['sources'])
print('Template:', cfg['content']['video_template'])
"
```

Expected: Prints channel name, persona, sources, template.

**Step 3: Commit**

```bash
git add config/channels/demo_tech.yaml
git commit -m "feat(config): add demo_tech channel config for demo pipeline"
```

---

## Task 2: Write Failing Test for Channel-Driven Collection

**Files:**
- Create: `tests/unit/scripts/test_demo_pipeline.py`
- Test: `tests/unit/scripts/__init__.py`

**Step 1: Create test directory and init file**

```bash
mkdir -p tests/unit/scripts
touch tests/unit/scripts/__init__.py
```

**Step 2: Write the failing test**

The test verifies that the demo pipeline can:
1. Load a channel config
2. Build a PersonaConfig from YAML
3. Select the best topic from collected RawTopics
4. Generate script with real topic data + persona

```python
# tests/unit/scripts/test_demo_pipeline.py
"""Tests for channel-driven demo pipeline helpers."""

import yaml
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config.persona import PersonaConfig
from app.services.collector.base import RawTopic


class TestLoadChannelConfig:
    """Test channel config loading."""

    def test_demo_tech_config_loads(self) -> None:
        """demo_tech.yaml loads and has required sections."""
        config_path = Path("config/channels/demo_tech.yaml")
        assert config_path.exists(), "demo_tech.yaml must exist"

        cfg = yaml.safe_load(config_path.read_text())
        assert "channel" in cfg
        assert "persona" in cfg
        assert "topic_collection" in cfg
        assert "content" in cfg

    def test_persona_config_from_yaml(self) -> None:
        """PersonaConfig can be constructed from channel YAML."""
        config_path = Path("config/channels/demo_tech.yaml")
        cfg = yaml.safe_load(config_path.read_text())

        persona = PersonaConfig(**cfg["persona"])
        assert persona.name == "테크브로"
        assert persona.voice.voice_id == "ko-KR-InJoonNeural"
        assert persona.communication.tone == "friendly"


class TestTopicSelection:
    """Test topic selection from collected raw topics."""

    def test_pick_best_topic_by_score(self) -> None:
        """pick_best_topic returns highest-scored topic."""
        from scripts.demo_pipeline import pick_best_topic

        topics = [
            RawTopic(
                source_id="1",
                source_url="https://example.com/a",
                title="Low score topic",
                metrics={"score": 10, "comments": 5},
            ),
            RawTopic(
                source_id="2",
                source_url="https://example.com/b",
                title="High score topic",
                metrics={"score": 500, "comments": 100},
            ),
            RawTopic(
                source_id="3",
                source_url="https://example.com/c",
                title="Medium score topic",
                metrics={"score": 100, "comments": 30},
            ),
        ]

        best = pick_best_topic(topics)
        assert best.title == "High score topic"

    def test_pick_best_topic_empty_returns_none(self) -> None:
        """pick_best_topic returns None for empty list."""
        from scripts.demo_pipeline import pick_best_topic

        assert pick_best_topic([]) is None
```

**Step 3: Run test to verify it fails**

```bash
uv run pytest tests/unit/scripts/test_demo_pipeline.py -v
```

Expected: FAIL — `demo_tech.yaml` not found, `pick_best_topic` not importable.

---

## Task 3: Implement Channel Config Loading + Topic Selection

**Files:**
- Modify: `scripts/demo_pipeline.py` (complete rewrite)

This is the main implementation step. The demo pipeline becomes:

```
Load Channel Config → Collect Topics (Reddit/RSS) → Normalize Best Topic
→ Generate Script (with persona + real data) → TTS → Subtitles → Visuals → Remotion
```

**Step 1: Rewrite `scripts/demo_pipeline.py`**

Key changes:
1. `load_channel_config(path)` — loads YAML, returns dict
2. `pick_best_topic(topics)` — selects highest engagement topic
3. `collect_topics(config)` — uses `collect_from_sources()` factory
4. `normalize_topic(raw, llm, pm)` — uses `TopicNormalizer`
5. `main()` — orchestrates the full pipeline using channel config

The pipeline flow:
```python
# Phase 0: Load config
channel_config = load_channel_config(config_path)
persona = PersonaConfig(**channel_config["persona"])

# Phase 1: Collect real topics
raw_topics = await collect_topics(channel_config["topic_collection"])

# Phase 2: Pick best + normalize
best_raw = pick_best_topic(raw_topics)
normalized = await normalize_topic(best_raw, llm_client, prompt_manager)

# Phase 3: Generate script with real data + persona
result = await generator.generate(
    topic_title=normalized.title_translated or normalized.title_original,
    topic_summary=normalized.summary,
    topic_terms=normalized.terms,
    persona=persona,
    target_duration=content_config.get("target_duration", 30),
)

# Phase 4-6: TTS, Subtitles, Visuals, Remotion (same as before, but uses persona voice settings)
```

**Important details:**
- TTS voice_id and speed come from `persona.voice` instead of hardcoded values
- Video template comes from `content.video_template` instead of hardcoded
- Target duration comes from `content.target_duration`
- Fallback still works: if collection fails or returns empty, uses FALLBACK_SCENES

**Step 2: Run tests**

```bash
uv run pytest tests/unit/scripts/test_demo_pipeline.py -v
```

Expected: All pass.

**Step 3: Run lint**

```bash
uv run ruff check scripts/demo_pipeline.py
```

Expected: Clean.

**Step 4: Commit**

```bash
git add scripts/demo_pipeline.py tests/unit/scripts/
git commit -m "feat(demo): channel config driven pipeline with real topic collection

- Load channel config YAML (persona, sources, content settings)
- Collect real topics from Reddit + HN RSS (no API keys)
- Normalize best topic with LLM (translate, classify)
- Pass persona + real data to script generator
- TTS voice/speed from persona config
- Fallback to hardcoded scenes if collection fails"
```

---

## Task 4: E2E Smoke Test

**Step 1: Run the full pipeline**

```bash
uv run python scripts/demo_pipeline.py
```

Expected output:
- Phase 0: "Loaded channel: 테크 데모"
- Phase 1: "Collected N topics from reddit, hn_rss"
- Phase 2: "Selected topic: [real title]" + "Normalized: [korean title]"
- Phase 3: "LLM script generated: N scenes"
- Phase 4-6: Same as before
- Final: Video at `/tmp/bsforge_demo/final_video.mp4`

**Step 2: Verify video content is from real source**

The video's headline and scenes should be about a REAL topic from Reddit/HN, not a generic "AI coding assistant" topic.

**Step 3: Run full test suite**

```bash
uv run pytest tests/unit/ -v --tb=short
```

Expected: All existing tests still pass + new tests pass.

---

## Summary of Files Changed

| File | Action | Description |
|------|--------|-------------|
| `config/channels/demo_tech.yaml` | Create | Demo channel config (persona, Reddit/RSS sources, content settings) |
| `scripts/demo_pipeline.py` | Rewrite | Channel config driven pipeline with real topic collection |
| `tests/unit/scripts/__init__.py` | Create | Test package init |
| `tests/unit/scripts/test_demo_pipeline.py` | Create | Tests for config loading, topic selection |

## Key Design Decisions

1. **No database** — Everything in-memory. Sources → normalize → script, no persistence needed for demo.
2. **Reddit + HN RSS only** — Both free, no API keys, high-quality tech topics.
3. **Fallback preserved** — If network fails or no topics found, falls back to hardcoded scenes.
4. **Persona drives everything** — Voice, style, perspective all come from channel config.
5. **`pick_best_topic` is simple** — Sort by `metrics.score + metrics.comments`, pick top. No ML scoring needed for demo.
