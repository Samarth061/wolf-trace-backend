# Shadow Bureau: Dead Drop — Backend

Noir-themed campus intelligence platform for Hack_NCState 2026 (Siren's Call track).

**[AGENTS.md](AGENTS.md)** — AI handoff guide. **Read this first when taking over.**
**[CHANGELOG.md](CHANGELOG.md)** — Version history and recent changes.
**[Architecture](docs/ARCHITECTURE.md)** — System design, Blackboard pattern, graph model.
**[API Reference](docs/API.md)** — Complete endpoint documentation.
**[Development](docs/DEVELOPMENT.md)** — Setup, testing, contributing.
**[Status](docs/STATUS.md)** — Implementation status and roadmap.

## Quick Start

```bash
# Install and run (requires uv: https://docs.astral.sh/uv/)
uv sync

# Copy env and add API keys (optional - graceful fallbacks when missing)
cp .env.example .env

# Run
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/report` | Submit anonymous tip |
| GET | `/api/reports` | List all reports |
| GET | `/api/cases` | List cases |
| POST | `/api/cases` | Create case (Neo4j) |
| GET | `/api/cases/{id}` | Case graph snapshot (in-memory) |
| GET | `/api/cases/{id}/graph` | Case graph from Neo4j (React Flow format) |
| POST | `/api/cases/{id}/evidence` | Upload evidence (Neo4j, linked via CONTAINS) |
| POST | `/api/cases/{id}/edges` | Red String: link two nodes (RELATED edge, emits `edge:created`) |
| POST | `/api/alerts/draft` | Draft alert (Gemini) |
| POST | `/api/alerts/approve` | Publish alert |
| GET | `/api/alerts` | Public alert feed |
| WS | `/ws/caseboard` | Graph updates stream |
| WS | `/ws/alerts` | New alerts stream |

## Environment

- `BACKBOARD_API_KEY` — Multi-agent AI (Claim Analyst, Fact Checker, Alert Composer, Case Synthesizer). Falls back to Gemini if unset.
- `GEMINI_API_KEY` — Fallback for claim extraction, alert composition, search queries
- `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD` — Neo4j AuraDB (optional). Verified on startup with `RETURN 1`.
- `FACTCHECK_API_KEY` — Google Fact Check Tools (falls back to GEMINI if unset)
- `TWELVELABS_API_KEY`, `TWELVELABS_INDEX_ID` — Video indexing/search
- `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID` — TTS for alerts
- `CORS_ORIGINS`
# wolftrace
