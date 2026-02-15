# Shadow Bureau: Agent Handoff

**For Claude Code (or any AI) taking over this project.** Read this first.

---

## Project Overview

**Shadow Bureau: Dead Drop** is a noir-themed campus intelligence platform (Hack_NCState 2026, Siren's Call track). It ingests anonymous tips, analyzes them with AI pipelines, fact-checks claims, and supports officer workflows for drafting/publishing alerts. Two graph systems coexist:

1. **In-memory graph** (`graph_state.py`) — report tips, pipelines (clustering, forensics, network), Blackboard controller, WebSockets
2. **Neo4j AuraDB** — Case/Evidence/RELATED nodes for officer-driven case building and Red String linking

---

## Quick Start

```bash
cd shadow-bureau-backend
uv sync
cp .env.example .env   # Add API keys (see Environment below)
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Verify:** `curl -s http://localhost:8000/health`

---

## Architecture at a Glance

- **FastAPI** app with lifespan (event bus, Backboard assistants, Neo4j, Blackboard controller)
- **Event bus** (`event_bus.py`): `@on("EventName")` handlers, `emit("EventName", payload)` — async
- **Blackboard pattern**: `graph_state.broadcast_graph_update()` notifies controller → knowledge sources run by priority
- **Neo4j**: Singleton in `graph_db.py`, `Depends(GraphDatabase.get_session)` in routes
- **AI**: Backboard.io 4 agents (Claim Analyst, Fact Checker, Alert Composer, Case Synthesizer) with Gemini fallback

---

## Key Files (Edit These)

| Purpose | File |
|---------|------|
| App entry, lifespan | `app/main.py` |
| Report ingestion | `app/routers/reports.py` |
| Case/Evidence/Edges API | `app/routers/cases.py` |
| Neo4j Cypher queries | `app/services/graph_queries.py` |
| AI routing | `app/services/ai.py` |
| Network pipeline (claims, fact check) | `app/pipelines/network.py` |
| Blackboard controller & registration | `app/pipelines/orchestrator.py` |
| In-memory graph, WebSockets | `app/graph_state.py` |
| Config | `app/config.py` |

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/report` | Submit tip → in-memory graph, pipelines |
| GET | `/api/reports` | List reports |
| GET | `/api/cases` | List cases (in-memory) |
| POST | `/api/cases` | Create case in Neo4j |
| GET | `/api/cases/{id}` | Case snapshot (in-memory) |
| GET | `/api/cases/{id}/graph` | Case graph from Neo4j (React Flow format) |
| POST | `/api/cases/{id}/evidence` | Add evidence to Neo4j (CONTAINS) |
| POST | `/api/cases/{id}/edges` | Red String: link nodes (RELATED), emits `edge:created` |
| POST | `/api/alerts/draft` | Draft alert (AI) |
| POST | `/api/alerts/approve` | Publish alert |
| GET | `/api/alerts` | Public feed |
| WS | `/ws/caseboard` | Graph updates |
| WS | `/ws/alerts` | New alerts |

---

## Environment (.env)

| Variable | Purpose |
|----------|---------|
| `BACKBOARD_API_KEY` | Multi-agent AI (optional; falls back to Gemini) |
| `GEMINI_API_KEY` | Fallback AI |
| `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD` | Neo4j AuraDB |
| `FACTCHECK_API_KEY` | Google Fact Check |
| `TWELVELABS_API_KEY`, `TWELVELABS_INDEX_ID` | Video analysis |
| `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID` | TTS |
| `CORS_ORIGINS` | Comma-separated origins |

All services degrade gracefully when keys are missing.

---

## Conventions

1. **Docs**: Update `docs/` when changing behavior. See `docs/IMPLEMENTATION_STATUS.md`, `docs/HOW_IT_WORKS.md`, `docs/FLOW.md`, `docs/TESTING.md`.
2. **Event bus**: Handlers must be imported before `start_event_bus()` so `@on` registers.
3. **Neo4j**: Use `graph_queries.py` for Cypher; routes use `Depends(GraphDatabase.get_session)`.
4. **Pydantic**: Request/response models in `app/models/`.

---

## Implemented vs Pending

### Implemented
- Report flow, pipelines, Backboard agents, Neo4j Case/Evidence/Edges, graph fetch for React Flow
- WebSockets, alerts, audit log

### Pending / Partial
- **Fact Checker agent** not wired: `ai.fact_check_claims` exists but is not called in `network.py`
- **edge:created handler** — event is emitted on Red String link; no `@on("edge:created")` handler yet (planned: AI analysis)
- **Inference nodes** — Cypher references `m:Inference`; label not yet used
- **Neo4j ↔ in-memory sync** — Report flow writes only to in-memory graph
- **Automated tests** — None
- **TTS audio URL** — Placeholder only

**Note:** Auth system was removed (not needed for hackathon). All routes are public.

---

## Recommended Next Steps

1. **Implement `edge:created` handler** — When user links two nodes via Red String, run AI analysis on the new link. Register `@on("edge:created")` in a new module (e.g. `app/pipelines/edge_analysis.py`).
2. **Wire Fact Checker agent** — In `network.py`, after claim extraction, call `ai.fact_check_claims(claims, case_id, thread_ids)` and merge with Fact Check API results.
3. **Create Inference nodes** — When AI infers a connection, create `(m:Inference:Node {id, type, content})` and `CONTAINS` or `RELATED` edges in Neo4j.
4. **Sync report flow to Neo4j** — Optionally persist report nodes/cases to Neo4j when created via `POST /api/report`.
5. **Add automated tests** — pytest for routers, graph_queries, pipelines.

---

## Documentation Index

| Doc | Purpose |
|-----|---------|
| `AGENTS.md` | This file — AI handoff guide |
| `README.md` | Quick start, overview |
| `CHANGELOG.md` | Version history, recent changes |
| `docs/ARCHITECTURE.md` | System design, Blackboard pattern, graph model |
| `docs/API.md` | Complete API reference |
| `docs/DEVELOPMENT.md` | Setup, testing, contributing |
| `docs/STATUS.md` | Implementation status, pending features |
