# Development Guide

Setup, testing, and contribution guidelines for Shadow Bureau.

---

## Quick Start

### Prerequisites
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- (Optional) Neo4j AuraDB account
- (Optional) API keys: Gemini, Backboard, TwelveLabs, ElevenLabs

### Installation

```bash
# Clone and navigate
cd shadow-bureau-backend

# Install dependencies
uv sync

# Copy environment template
cp .env.example .env

# Add API keys (optional - graceful fallbacks)
nano .env
```

### Running the Server

```bash
# Development (with auto-reload)
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Production
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Verify:** http://localhost:8000/health

---

## Testing

### Automated Tests

```bash
# Run test script
./test_api.sh
```

**Expected:** 14/14 tests pass

### Manual Testing

#### 1. Interactive API Docs
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

#### 2. Health Check
```bash
curl http://localhost:8000/health | jq
```

**Expected:**
```json
{
  "status": "ok",
  "knowledge_sources": 7,
  "controller_running": true
}
```

#### 3. Submit Report
```bash
curl -X POST http://localhost:8000/api/report \
  -H "Content-Type: application/json" \
  -d '{
    "text_body": "Test report: Fire alarm at Hunt Library",
    "location": {"lat": 35.7847, "lng": -78.6821, "building": "Hunt Library"},
    "timestamp": "2026-02-14T14:00:00",
    "anonymous": true
  }' | jq
```

**Expected:** Returns `case_id` and `report_id`

#### 4. Check Pipeline Execution
```bash
# Get case snapshot
curl http://localhost:8000/api/cases/CASE-YOUR-ID | jq '.nodes | length'
```

**Expected:** Multiple nodes created (report + external sources)

#### 5. WebSocket Testing

**Browser Console:**
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/caseboard');
ws.onmessage = (e) => console.log('📨', JSON.parse(e.data));
```

**CLI (websocat):**
```bash
# Install: cargo install websocat
websocat ws://localhost:8000/ws/caseboard
```

**Expected:**
- Initial snapshots message
- Real-time `graph_update` messages

---

## Test Scenarios

### Scenario 1: Basic Report Flow
1. Submit report via `POST /api/report`
2. Wait 3 seconds for pipelines
3. Check `GET /api/cases/{case_id}` for nodes/edges
4. Verify claims extracted, semantic_role assigned

### Scenario 2: Clustering
1. Submit 2 reports with similar time/location
2. Check for `SIMILAR_TO` edge between them
3. Verify clustering pipeline ran

### Scenario 3: Alerts
1. Submit report
2. Draft alert via `POST /api/alerts/draft`
3. Approve via `POST /api/alerts/approve` (status: `"Confirmed"`)
4. Check `GET /api/alerts` for published alert

### Scenario 4: Neo4j (Optional)
1. Add Neo4j credentials to `.env`
2. Create case: `POST /api/cases`
3. Add evidence: `POST /api/cases/{id}/evidence`
4. Create link: `POST /api/cases/{id}/edges`
5. Fetch graph: `GET /api/cases/{id}/graph`

---

## Environment Variables

| Variable | Required | Purpose | Default/Fallback |
|----------|----------|---------|------------------|
| `GEMINI_API_KEY` | No | Claim extraction | Mock data |
| `BACKBOARD_API_KEY` | No | Multi-agent AI | Falls back to Gemini |
| `NEO4J_URI` | No | Graph database | In-memory only |
| `NEO4J_USERNAME` | No | Neo4j auth | - |
| `NEO4J_PASSWORD` | No | Neo4j auth | - |
| `FACTCHECK_API_KEY` | No | Fact checking | Empty results |
| `TWELVELABS_API_KEY` | No | Video analysis | Empty results |
| `TWELVELABS_INDEX_ID` | No | Video index | - |
| `ELEVENLABS_API_KEY` | No | Text-to-speech | No audio |
| `ELEVENLABS_VOICE_ID` | No | TTS voice | - |
| `CORS_ORIGINS` | No | CORS config | `localhost:3000,5173` |

**Note:** All services degrade gracefully when keys are missing.

---

## Project Structure

```
shadow-bureau-backend/
├── app/
│   ├── main.py                # FastAPI app, lifespan
│   ├── config.py              # Environment settings
│   ├── event_bus.py           # Event pub/sub
│   ├── graph_state.py         # In-memory graph
│   ├── models/                # Pydantic models
│   ├── routers/               # API endpoints
│   ├── pipelines/             # Knowledge sources
│   ├── services/              # External integrations
│   ├── forensics/             # Image/video analysis
│   └── utils/                 # Helpers
├── docs/                      # Documentation
├── .env.example               # Environment template
├── pyproject.toml             # Dependencies
└── test_api.sh                # Test script
```

---

## Development Workflow

### Adding a New Endpoint

1. **Define Model** in `app/models/`
   ```python
   from pydantic import BaseModel

   class MyRequest(BaseModel):
       field: str
   ```

2. **Create Route** in `app/routers/`
   ```python
   @router.post("/my-endpoint")
   async def my_endpoint(req: MyRequest):
       return {"result": "ok"}
   ```

3. **Register Router** in `app/main.py`
   ```python
   app.include_router(my_router.router)
   ```

4. **Test** via Swagger UI

### Adding a Knowledge Source

1. **Create Pipeline** in `app/pipelines/my_pipeline.py`
   ```python
   async def run_my_pipeline(payload: dict):
       # Process
       pass
   ```

2. **Register** in `app/pipelines/orchestrator.py`
   ```python
   ctrl.register(
       name="my_pipeline",
       priority=Priority.MEDIUM,
       trigger_types=["node:report"],
       handler=my_pipeline.run_my_pipeline,
       cooldown_seconds=2.0,
   )
   ```

3. **Test** by triggering the event

### Adding an Event Handler

1. **Define Handler** in relevant module
   ```python
   from app.event_bus import on

   @on("MyEvent")
   async def handle_my_event(payload: dict):
       # Process
       pass
   ```

2. **Emit Event** where needed
   ```python
   from app.event_bus import emit

   await emit("MyEvent", {"data": "..."})
   ```

---

## Debugging

### Enable Debug Logging
```python
# In app/main.py
logging.basicConfig(level=logging.DEBUG)
```

### Check Pipeline Execution
Watch server console for:
```
INFO: Knowledge source clustering started for CASE-...
INFO: Knowledge source network started for CASE-...
```

### Inspect Graph State
```bash
# Get case snapshot
curl http://localhost:8000/api/cases/{case_id} | jq
```

### Check Controller Status
```bash
curl http://localhost:8000/health | jq '.knowledge_sources, .controller_running'
```

---

## Performance

### Expected Metrics
| Operation | Time |
|-----------|------|
| Server startup | 2-5 sec |
| Report submission | < 500ms |
| Pipeline execution | 1-3 sec |
| WebSocket message | < 100ms |

### Optimization Tips
- Use Backboard for better AI quality
- Configure Neo4j for persistent storage
- Add Redis for caching (future)
- Implement connection pooling (future)

---

## Troubleshooting

### Server won't start
```bash
# Check Python version
python3 --version  # Need 3.11+

# Reinstall dependencies
uv sync --reinstall
```

### Import errors
```bash
# Verify syntax
python3 -m py_compile app/main.py
```

### Pipelines not running
- Check server logs for errors
- Verify controller status via `/health`
- Check event bus is started

### WebSocket connection fails
- Ensure server is running
- Check CORS settings
- Verify WebSocket URL (ws:// not http://)

---

## Contributing

### Code Style
- Follow PEP 8
- Use type hints
- Write docstrings for public functions
- Keep functions focused and small

### Commit Messages
```
feat: Add new endpoint for X
fix: Resolve issue with Y pipeline
docs: Update API reference
refactor: Simplify Z logic
```

### Pull Request Process
1. Create feature branch
2. Make changes
3. Test locally
4. Update documentation
5. Submit PR with description

---

## References

- **Architecture:** [docs/ARCHITECTURE.md](ARCHITECTURE.md)
- **API Docs:** [docs/API.md](API.md)
- **Status:** [docs/STATUS.md](STATUS.md)
- **AI Handoff:** [AGENTS.md](../AGENTS.md)
