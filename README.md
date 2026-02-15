# Wolf Trace Backend - Campus Intelligence API

**FastAPI backend for WolfTrace campus safety & disinformation detection platform**

Noir-themed intelligence system built for Hack NCState 2026 (Siren's Call track).

---

## 📚 Documentation

- **[AGENTS.md](AGENTS.md)** — AI handoff guide (read this first when taking over)
- **[CHANGELOG.md](CHANGELOG.md)** — Version history and recent changes
- **[Architecture](docs/ARCHITECTURE.md)** — System design, Blackboard pattern, graph model
- **[API Reference](docs/API.md)** — Complete endpoint documentation
- **[Development](docs/DEVELOPMENT.md)** — Setup, testing, contributing
- **[Status](docs/STATUS.md)** — Implementation status and roadmap

---

## 🚀 Quick Start

### Prerequisites
- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- GROQ API key (required)
- Neo4j AuraDB (optional - falls back to in-memory)

### Installation

```bash
# Install dependencies
uv sync

# Configure environment
cp .env.example .env
# Edit .env and add GROQ_API_KEY

# Run backend
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Backend runs on:** http://localhost:8000
**Interactive API Docs:** http://localhost:8000/docs
**Alternative Docs:** http://localhost:8000/redoc

---

## 🔑 Environment Variables

### Required

```bash
GROQ_API_KEY=gsk_...        # GROQ API for AI operations (required)
```

### Optional (Graceful Fallbacks)

```bash
# AI Services
BACKBOARD_API_KEY=...        # Multi-agent orchestration (Claim Analyst, Fact Checker, etc.)
GEMINI_API_KEY=...           # Fallback for vision/forensics (NOT used directly!)

# Database
NEO4J_URI=neo4j+s://...      # Neo4j AuraDB (falls back to in-memory)
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=...

# Verification & Media
FACTCHECK_API_KEY=...        # Google Fact Check Tools (falls back to GEMINI_API_KEY)
TWELVELABS_API_KEY=...       # Video deepfake detection
TWELVELABS_INDEX_ID=...

# Text-to-Speech
ELEVENLABS_API_KEY=...       # TTS for alerts
ELEVENLABS_VOICE_ID=...

# Configuration
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
MEDIA_BASE_URL=http://localhost:8000
```

---

## 🤖 AI Provider Configuration

**Default:** GROQ (fast, cost-effective, no quota issues)

### Current GROQ Models

| Purpose | Model | Speed | Context |
|---------|-------|-------|---------|
| Claim Extraction | `llama-3.3-70b-versatile` | 280 tok/s | 131K tokens |
| Forensic Analysis | `llama-3.3-70b-versatile` | 280 tok/s | 131K tokens |
| Alert Composition | `llama-3.1-8b-instant` | 560 tok/s | 131K tokens |
| Search Queries | `llama-3.1-8b-instant` | 560 tok/s | 131K tokens |

### Fallback Chain

```
1. GROQ (default for all operations)
   ↓ (if fails)
2. Backboard (uses their Gemini/Claude keys)
   ↓ (if fails)
3. Mock data (no external API required)
```

**Important:** Your `GEMINI_API_KEY` is **never called directly**. Backboard may use Gemini internally (their quota), avoiding your API limits.

---

## 🏗️ Project Structure

```
wolf-trace-backend/
├── app/
│   ├── main.py                 # FastAPI application entry point
│   ├── config.py               # Environment configuration (Pydantic Settings)
│   │
│   ├── routers/                # API endpoints
│   │   ├── cases.py           # Case CRUD, evidence upload, forensics
│   │   ├── alerts.py          # Alert drafting & publishing
│   │   └── reports.py         # Anonymous tip submission
│   │
│   ├── services/               # External AI/API integrations
│   │   ├── ai.py              # Unified AI layer (GROQ router)
│   │   ├── groq.py            # GROQ API client (Llama models)
│   │   ├── backboard_client.py # Backboard multi-agent system
│   │   ├── gemini.py          # Gemini fallback (rarely used)
│   │   ├── twelvelabs.py      # Video deepfake detection
│   │   ├── factcheck.py       # Google Fact Check Tools
│   │   └── elevenlabs.py      # Text-to-speech
│   │
│   ├── pipelines/              # Background processing (Blackboard pattern)
│   │   ├── blackboard_controller.py  # Orchestrator (priority queue)
│   │   ├── orchestrator.py    # Knowledge source registration
│   │   ├── forensics.py       # Image/video forensics pipeline
│   │   ├── network.py         # Claim extraction & fact-checking
│   │   ├── clustering.py      # Similar evidence detection
│   │   ├── forensics_xref.py  # Cross-reference forensic findings
│   │   └── case_synthesizer.py # Case summary generation
│   │
│   ├── forensics/              # Image/video analysis
│   │   ├── ela.py             # Error Level Analysis
│   │   ├── phash.py           # Perceptual hashing
│   │   └── exif.py            # EXIF metadata extraction
│   │
│   ├── models/                 # Pydantic data models
│   │   ├── graph.py           # Node, Edge, NodeType, EdgeType
│   │   ├── report.py          # Report model
│   │   └── evidence.py        # Evidence model
│   │
│   ├── graph_state.py          # Neo4j operations
│   ├── websocket_manager.py    # WebSocket connections manager
│   └── test_data.py            # Seed data for development
│
├── tests/                       # Test suite
│   ├── test_routers.py
│   ├── test_services.py
│   └── test_pipelines.py
│
├── docs/                        # Documentation
│   ├── ARCHITECTURE.md
│   ├── API.md
│   ├── DEVELOPMENT.md
│   └── STATUS.md
│
├── pyproject.toml               # Dependencies & project config (uv)
├── .env.example                 # Environment template
└── README.md                    # This file
```

---

## 📡 API Endpoints

### Cases

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/cases` | List all cases |
| POST | `/api/cases` | Create new case |
| GET | `/api/cases/{id}` | Get case details |
| GET | `/api/cases/{id}/graph` | Get knowledge graph (React Flow format) |

### Evidence

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/cases/{id}/evidence` | Upload evidence (image/video/text) |
| POST | `/api/cases/{id}/evidence/{id}/forensics` | Trigger forensic analysis |

### Graph Operations

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/cases/{id}/edges` | Create edge between nodes (Red String) |

### Alerts

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/alerts/draft` | Draft alert using GROQ |
| POST | `/api/alerts/approve` | Publish alert |
| GET | `/api/alerts` | Get public alert feed |

### Tips

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/report` | Submit anonymous tip |
| GET | `/api/reports` | List all reports |

### Media

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/upload` | Upload media file |
| GET | `/api/upload/{filename}` | Retrieve uploaded file |

### WebSocket

| Protocol | Endpoint | Description |
|----------|----------|-------------|
| WS | `/ws/caseboard` | Real-time graph updates |
| WS | `/ws/alerts` | Real-time alert stream |

**Full API Documentation:** http://localhost:8000/docs

---

## 🔄 Key Workflows

### 1. Evidence Upload & Forensics

```python
# 1. User uploads image via POST /api/cases/{id}/evidence
# Frontend sends:
{
  "media_url": "http://localhost:8000/api/upload/abc.png",
  "text_body": "Suspicious activity reported",
  "location": {"building": "Hunt Library"},
  "llm_provider": "groq"  # Set automatically by frontend
}

# 2. Backend creates node in Neo4j
node = create_node(NodeType.REPORT, case_id, data)

# 3. Blackboard triggers forensics pipeline
orchestrator.publish("node:report", {
  "case_id": case_id,
  "node_id": node.id,
  "data": node.data
})

# 4. Forensics pipeline executes:
#    - Backboard vision analyzes image → text description
#    - GROQ analyzes text description → ml_accuracy, scores
#    - Updates node with forensic results

# 5. WebSocket broadcasts update to frontend
await broadcast_graph_update("update_node", node)
```

### 2. Claim Extraction & Fact Checking

```python
# 1. Network pipeline triggers on text evidence
# 2. GROQ extracts claims (Llama 3.3 70B)
claims = await groq.extract_claims(report_text)
# Returns: {claims: [...], urgency: 0.8, misinformation_flags: [...]}

# 3. Google Fact Check Tools searches each claim
for claim in claims:
    fact_checks = await factcheck.search_claims(claim["statement"])

# 4. GROQ generates search queries (Llama 3.1 8B)
queries = await groq.generate_search_queries(claims)

# 5. Updates node with enriched data
update_node(node_id, {
    "claims": claims,
    "fact_checks": fact_checks,
    "search_queries": queries
})
```

### 3. Alert Drafting

```python
# 1. Officer requests alert draft
# POST /api/alerts/draft
{
  "case_id": "case-001",
  "officer_notes": "Confirmed incident, notify students"
}

# 2. GROQ composes alert (Llama 3.1 8B)
alert_text = await groq.compose_alert(case_context, officer_notes)

# Returns professional, fact-based alert text
# 3. Officer reviews & approves
# POST /api/alerts/approve

# 4. WebSocket broadcasts to all clients
await broadcast_alert(alert)
```

---

## 🧪 Testing

### Run Tests

```bash
# All tests
uv run pytest

# With coverage
uv run pytest --cov=app

# Specific test file
uv run pytest tests/test_routers.py

# Verbose output
uv run pytest -v
```

### Test Structure

```
tests/
├── test_routers.py         # API endpoint tests
├── test_services.py        # AI service integration tests
├── test_pipelines.py       # Blackboard pipeline tests
└── test_graph_state.py     # Neo4j graph tests
```

---

## 🐛 Debugging

### Enable Debug Logging

```python
# In main.py, add:
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Common Issues

**1. GROQ 400 Error - Model Decommissioned**
```
Error: The model `mixtral-8x7b-32768` has been decommissioned
```
**Fix:** Models updated to `llama-3.3-70b-versatile` and `llama-3.1-8b-instant`

**2. Pydantic Serialization Error - numpy.int64**
```
PydanticSerializationError: Unable to serialize unknown type: <class 'numpy.int64'>
```
**Fix:** Convert numpy types to Python int:
```python
distance = int(hamming_distance(hash1, hash2))
```

**3. Neo4j Connection Failed**
```
WARNING: Neo4j connection failed, using in-memory graph
```
**Fix:** Backend gracefully falls back - no action needed unless you need persistence

**4. Gemini Quota Error (429)**
```
Error 429: Resource exhausted
```
**Fix:** Ensure `GROQ_API_KEY` is set - GROQ should be handling all requests

---

## 🔐 Security

- **API Keys:** Never commit `.env` files (added to `.gitignore`)
- **CORS:** Configured via `CORS_ORIGINS` environment variable
- **File Uploads:** Validated file types, size limits enforced
- **Neo4j:** Use `neo4j+s://` for encrypted connections
- **Anonymous Tips:** No IP logging, no user tracking

---

## 📦 Dependencies

### Core
- **FastAPI** - Web framework
- **uvicorn** - ASGI server
- **pydantic** - Data validation
- **pydantic-settings** - Environment config

### AI & ML
- **groq** - GROQ API client
- **google-generativeai** - Gemini fallback
- **httpx** - HTTP client for API calls

### Database
- **neo4j** - Graph database driver

### Image/Video Processing
- **Pillow** - Image manipulation
- **imagehash** - Perceptual hashing
- **numpy** - Numerical operations

### WebSocket
- **python-multipart** - File upload handling
- **websockets** - WebSocket support

### Development
- **pytest** - Testing framework
- **pytest-cov** - Coverage reporting

**Full dependency list:** See `pyproject.toml`

---

## 🚀 Deployment

### Production Checklist

- [ ] Set `GROQ_API_KEY` in production environment
- [ ] Configure Neo4j AuraDB (or use in-memory)
- [ ] Set `CORS_ORIGINS` to production frontend URL
- [ ] Enable HTTPS (use reverse proxy like nginx)
- [ ] Configure file storage (S3/CloudFlare R2)
- [ ] Set up monitoring (Sentry, DataDog)
- [ ] Configure rate limiting
- [ ] Run with multiple workers: `uvicorn app.main:app --workers 4`

### Docker (Optional)

```dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml ./
RUN pip install uv && uv sync
COPY . .
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 📈 Performance

- **GROQ Speed:** 280-560 tokens/sec (significantly faster than Gemini)
- **WebSocket:** Real-time updates with <100ms latency
- **Blackboard:** Async pipeline processing (non-blocking)
- **Neo4j:** Indexed queries (<50ms for graph traversal)

---

## 🔧 Development

### Code Style

- **Formatter:** black (or ruff)
- **Linter:** ruff
- **Type Checking:** mypy (optional)

```bash
# Format code
ruff format .

# Lint code
ruff check .
```

### Adding New Endpoints

1. Create route in `app/routers/`
2. Add route to `app/main.py`
3. Update `docs/API.md`
4. Write tests in `tests/`

### Adding New AI Service

1. Create client in `app/services/`
2. Add routing logic in `app/services/ai.py`
3. Update environment variables in `config.py`
4. Document in README

---

## 📄 License

MIT License - See LICENSE file for details

---

## 👥 Support

For issues or questions:
1. Check [Documentation](docs/)
2. Review [API Reference](docs/API.md)
3. Open an issue on GitHub

---

**Version:** 1.0.0
**Last Updated:** February 2026
**Built for:** Hack NCState 2026 (Siren's Call track)
