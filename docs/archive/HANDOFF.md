# Shadow Bureau: Technical Handoff for Claude Code

Comprehensive handoff documentation so an AI agent can seamlessly take over development.

---

## 1. Project Context

- **Name:** Shadow Bureau: Dead Drop
- **Domain:** Campus safety intelligence
- **Stack:** FastAPI, Python 3.11+, uv, Neo4j AuraDB, Backboard.io, Gemini, TwelveLabs, ElevenLabs
- **Patterns:** Blackboard architecture, event-driven pipelines, dual graph (in-memory + Neo4j)

---

## 2. Data Flow Summary

### Report Flow (In-Memory)
1. `POST /api/report` → Create Report node → `broadcast_graph_update` → Controller enqueues pipelines
2. Pipelines (by priority): clustering, forensics, network, forensics_xref, recluster_debunk, classifier, case_synthesizer
3. Network: Backboard Claim Analyst extracts claims → Fact Check API → ExternalSource nodes
4. WebSocket broadcasts `graph_update` to `/ws/caseboard`

### Case Flow (Neo4j)
1. `POST /api/cases` → `create_case` (MERGE Case)
2. `POST /api/cases/{id}/evidence` → `add_evidence` (CREATE Evidence, CONTAINS edge)
3. `POST /api/cases/{id}/edges` → `create_link` (MERGE RELATED edge) → `emit("edge:created", ...)`
4. `GET /api/cases/{id}/graph` → `get_case_graph` → React Flow format

---

## 3. Event Bus

**Location:** `app/event_bus.py`

**Usage:**
```python
from app.event_bus import on, emit

@on("edge:created")
async def handle_edge_created(payload: dict):
    # payload: { case_id, source, target, relation }
    pass

await emit("edge:created", {"case_id": "...", "source": {...}, "target": {...}, "relation": {...}})
```

**Critical:** Handlers are registered via `@on` at import time. Import the module that defines handlers **before** `start_event_bus()` (see `main.py` — `orchestrator` is imported early).

**Known events:** `ReportReceived`, `edge:created`

---

## 4. Neo4j Schema

| Node Label | Properties | Created By |
|------------|------------|------------|
| Case | id, title, description, created_at | `create_case` |
| Evidence:Node | id, type, content, url, timestamp | `add_evidence` |
| Inference | (future) | — |

| Relationship | Properties | Meaning |
|--------------|------------|---------|
| CONTAINS | — | Case → Evidence |
| RELATED | type, note, created_at, manual | Node → Node (Red String) |

**Cypher functions:** `app/services/graph_queries.py` — `create_case`, `add_evidence`, `create_link`, `get_case_graph`

---

## 5. Blackboard Controller

**Location:** `app/pipelines/blackboard_controller.py`, registration in `app/pipelines/orchestrator.py`

**Event types:** `node:report`, `edge:repost_of`, `edge:debunked_by`, `update:report`, etc.

**Priorities:** CRITICAL (0) → HIGH (1) → MEDIUM (2) → LOW (3) → BACKGROUND (4)

**To add a knowledge source:** In `orchestrator.py`, call `ctrl.register(name, priority, trigger_types, handler, condition?, cooldown_seconds)`.

---

## 6. API Contracts

### POST /api/cases
**Body:** `{ case_id, title?, description? }`  
**Response:** `{ id, title, description, created_at }`

### POST /api/cases/{id}/evidence
**Body:** `{ id, type?, content?, url?, timestamp? }`  
**Response:** `{ id, type, content, url, timestamp }`

### POST /api/cases/{id}/edges
**Body:** `{ source_id, target_id, type?, note? }` — type default `SUSPECTED_LINK`  
**Response:** `{ source_id, target_id, type, note?, created_at? }`  
**Side effect:** `emit("edge:created", {...})`

### GET /api/cases/{id}/graph
**Response:** `{ nodes, edges, case_id }`  
**Nodes:** `{ id, position: {x,y}, data: { label, nodeType, type?, content?, url?, timestamp? } }`  
**Edges:** `{ id, source, target, type, data?: { note } }`

---

## 7. Pydantic Models

**Location:** `app/models/`

- `report.py`: ReportCreate, ReportOut, Location
- `alert.py`: AlertDraftRequest, AlertDraftResponse, AlertApproveRequest, AlertOut, AlertStatus
- `case.py`: CaseCreate, CaseOut, EvidenceCreate, EvidenceOut, EdgeCreate, EdgeOut
- `graph.py`: NodeType, EdgeType, GraphNode, GraphEdge

---

## 8. Where to Add New Features

| Feature | Where |
|---------|-------|
| New API route | `app/routers/*.py` |
| New Neo4j query | `app/services/graph_queries.py` |
| New event handler | New module imported in `main.py` before event bus start |
| New pipeline / knowledge source | `app/pipelines/`, register in `orchestrator.py` |
| New config | `app/config.py`, `.env.example` |

---

## 9. Running & Testing

```bash
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Smoke test:** `docs/TESTING.md` sections 1–4d.  
**OpenAPI:** `http://localhost:8000/docs`

---

## 10. Checklist for Claude Code

When taking over:

1. [ ] Read `AGENTS.md` (root)
2. [ ] Skim `docs/IMPLEMENTATION_STATUS.md` for gaps
3. [ ] Review `docs/FLOW.md` for data flow
4. [ ] Check `docs/TESTING.md` for verification steps
5. [ ] Run the server, run smoke tests
6. [ ] Implement `@on("edge:created")` handler for AI analysis (first recommended task)
7. [ ] Update docs when making changes
