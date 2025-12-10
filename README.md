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
| **Backend** | FastAPI (Python 3.11+) |
| **Database** | PostgreSQL + Redis |
| **Vector DB** | Chroma → Pinecone |
| **Embedding** | BGE-M3 (HuggingFace) |
| **LLM** | Claude API (LangChain) |
| **TTS** | Edge TTS / ElevenLabs |
| **Video** | FFmpeg |
| **Queue** | Celery + Redis |
| **Dashboard** | React + TypeScript |

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- FFmpeg
- Node.js 18+ (for Dashboard)

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/bsforge.git
cd bsforge

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your API keys

# Run database migrations
alembic upgrade head

# Start the server
uvicorn app.main:app --reload
```

### Channel Setup

```bash
# Create channel configuration
cp config/examples/channel.example.yaml config/channels/my-channel.yaml
# Edit with your channel settings

# Register the channel
python -m app.cli channel register my-channel
```

---

## 📁 Project Structure

```
bsforge/
├── app/
│   ├── api/              # FastAPI routers
│   ├── core/             # Config, dependencies
│   ├── models/           # SQLAlchemy models
│   ├── schemas/          # Pydantic schemas
│   ├── services/
│   │   ├── collector/    # Topic collection
│   │   ├── rag/          # Persona RAG
│   │   ├── generator/    # Video generation
│   │   ├── uploader/     # YouTube upload
│   │   └── analyzer/     # Analytics
│   ├── workers/          # Celery tasks
│   └── main.py
├── config/
│   ├── examples/         # Example configs (public)
│   ├── channels/         # Channel configs (private)
│   └── sources/          # Source configs (private)
├── dashboard/            # React frontend
├── architecture/         # Design documents
├── tests/
├── alembic/              # DB migrations
├── .env.example
├── .gitignore
├── CLAUDE.md             # Claude Code context
├── requirements.txt
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

### 2️⃣ Script Generation (Persona RAG)
- Hybrid search: Semantic (70%) + BM25 (30%)
- Reranking + MMR for diversity
- Reflect high-performing content style from history

### 3️⃣ Video Generation
- TTS: Edge TTS (free) / ElevenLabs (premium)
- Visuals: Pexels stock / DALL-E generation
- FFmpeg composition + subtitles

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
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific module
pytest tests/services/test_collector.py
```

---

## 🐳 Docker

```bash
# Build
docker-compose build

# Run
docker-compose up -d

# View logs
docker-compose logs -f
```

---

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgments

- [LangChain](https://langchain.com/) - LLM Framework
- [HuggingFace](https://huggingface.co/) - Embedding Models
- [FFmpeg](https://ffmpeg.org/) - Video Processing
- [FastAPI](https://fastapi.tiangolo.com/) - Web Framework

---

## 📬 Contact

For questions about the codebase, please check the [CLAUDE.md](./CLAUDE.md) and architecture documents first.

---

**Built with ❤️ for AI Engineers**
