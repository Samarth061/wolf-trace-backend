# Shadow Bureau: Implementation Status

Documentation of what is implemented, project structure, and what remains to be built.

---

## Project Structure

```
shadow-bureau-backend/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app, lifespan, CORS
│   ├── config.py               # Pydantic settings (API keys, env)
│   ├── event_bus.py            # Event publishing/subscription
│   ├── graph_state.py          # In-memory graph (nodes, edges, connection manager)
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── graph.py            # NodeType, EdgeType, GraphNode, GraphEdge
│   │   ├── report.py           # Report, ReportCreate, ReportOut
│   │   ├── alert.py            # Alert models, AlertStatus
│   │   └── case.py             # CaseCreate, CaseOut, EvidenceCreate, EvidenceOut, EdgeCreate, EdgeOut
│   │
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── reports.py          # POST /report, GET /reports
│   │   ├── cases.py            # GET /cases, GET /cases/{id}
│   │   ├── alerts.py           # POST /alerts/draft, /approve, GET /alerts
│   │   └── ws.py               # /ws/caseboard, /ws/alerts
│   │
│   ├── pipelines/
│   │   ├── __init__.py
│   │   ├── orchestrator.py     # Event handlers, knowledge source registration
│   │   ├── blackboard_controller.py  # Priority queue, cooldowns, triggers
│   │   ├── forensics.py        # ELA, pHash, EXIF, TwelveLabs
│   │   ├── network.py          # Claim extraction, fact check, search queries
│   │   ├── clustering.py       # Temporal/geographic/semantic similarity
│   │   ├── forensics_xref.py   # TwelveLabs search on claims
│   │   ├── classifier.py       # Semantic roles (originator, amplifier, etc.)
│   │   ├── recluster_debunk.py # Debunk count updates
│   │   └── case_synthesizer.py # Case narrative, origin, spread map
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── ai.py               # Unified AI layer (Backboard → Gemini fallback)
│   │   ├── backboard_client.py # 4 assistants, threads, memory
│   │   ├── graph_db.py         # Neo4j AuraDB singleton, get_session dependency
│   │   ├── graph_queries.py   # Cypher: create_case, add_evidence
│   │   ├── gemini.py           # Fallback: claims, alert, search
│   │   ├── factcheck.py        # Google Fact Check API
│   │   ├── twelvelabs.py       # Video index, search, summarize
│   │   └── elevenlabs.py      # TTS for alerts
│   │
│   ├── forensics/
│   │   ├── __init__.py
│   │   └── ela.py              # ELA heatmap, pHash, EXIF extraction
│   │
│   └── utils/
│       ├── __init__.py
│       ├── ids.py              # Case ID, report ID, alert ID generation
│       └── audit.py            # In-memory audit log (deque)
│
├── docs/
│   ├── HOW_IT_WORKS.md        # Architecture, data flow, graph model
│   ├── IMPLEMENTATION_STATUS.md  # This file
│   ├── TESTING.md             # curl/websocat test guide
│   └── temp.md                # Original Backboard spec (implemented)
│
├── tasks/
│   ├── todo.md                # Task checklist
│   └── lessons.md             # Workflow patterns
│
├── pyproject.toml
├── uv.lock
├── Dockerfile
├── .env.example
└── README.md
```

---

## Implemented

### 1. Core Infrastructure

| Component | Status | Notes |
|-----------|--------|-------|
| FastAPI app | ✅ Done | CORS, lifespan, health endpoint |
| Event bus | ✅ Done | `@on` decorator, `emit`, handlers |
| Graph state | ✅ Done | In-memory nodes/edges, `broadcast_graph_update` |
| Blackboard controller | ✅ Done | Priority queue, triggers, cooldowns, dedup |
| Config / env | ✅ Done | Pydantic settings, graceful fallbacks |

### 2. Models & API

| Component | Status | Notes |
|-----------|--------|-------|
| Report, graph, alert models | ✅ Done | Pydantic schemas |
| POST /api/report | ✅ Done | Returns case_id, report_id |
| GET /api/reports | ✅ Done | List all reports |
| GET /api/cases | ✅ Done | List cases with counts |
| GET /api/cases/{id} | ✅ Done | Full graph snapshot |
| POST /api/cases | ✅ Done | Create case in Neo4j (MERGE on case_id) |
| POST /api/cases/{id}/evidence | ✅ Done | Add evidence to Neo4j, linked via CONTAINS |
| POST /api/cases/{id}/edges | ✅ Done | Red String: link nodes (RELATED), emits `edge:created` |
| GET /api/cases/{id}/graph | ✅ Done | Full graph from Neo4j, React Flow format |
| POST /api/alerts/draft | ✅ Done | AI draft from case context |
| POST /api/alerts/approve | ✅ Done | Publish, broadcast, optional TTS |
| GET /api/alerts | ✅ Done | Public feed |
| WS /ws/caseboard | ✅ Done | Snapshots + graph_update stream |
| WS /ws/alerts | ✅ Done | new_alert broadcast |

### 3. Pipelines (Knowledge Sources)

| Pipeline | Priority | Status | Notes |
|----------|----------|--------|-------|
| clustering | CRITICAL | ✅ Done | Temporal + geo + semantic signals |
| forensics | HIGH | ✅ Done | ELA, pHash, EXIF, TwelveLabs |
| network | MEDIUM | ✅ Done | Claims, fact check, search queries |
| recluster_debunk | HIGH | ✅ Done | Debunk count on report nodes |
| forensics_xref | MEDIUM | ✅ Done | TwelveLabs search on claims |
| classifier | LOW | ✅ Done | Originator, amplifier, mutator, unwitting_sharer |
| case_synthesizer | BACKGROUND | ✅ Done | Narrative, origin, spread map, confidence |

### 4. External Services

| Service | Status | Notes |
|---------|--------|-------|
| Backboard.io | ✅ Done | 4 assistants, threads, memory |
| Gemini | ✅ Done | Fallback when Backboard unavailable |
| Neo4j AuraDB | ✅ Done | Singleton driver, verify on startup, `get_session()` FastAPI dependency |
| Google Fact Check | ✅ Done | Called per claim |
| TwelveLabs | ✅ Done | Video index/search/summarize |
| ElevenLabs | ✅ Done | TTS for alerts |

### 5. Backboard Multi-Agent Integration

| Agent | Status | Integration |
|-------|--------|-------------|
| Claim Analyst | ✅ Done | `ai.extract_claims` → network pipeline |
| Fact Checker | ⚠️ Partial | Implemented in `ai.fact_check_claims` but **not called** by network |
| Alert Composer | ✅ Done | `ai.compose_alert` → alerts router |
| Case Synthesizer | ✅ Done | `case_synthesizer` pipeline → graph nodes |

| Feature | Status | Notes |
|---------|--------|-------|
| Assistants creation (startup) | ✅ Done | Idempotent via `get_or_create_assistants` |
| Case threads (per assistant) | ✅ Done | `create_case_thread` on first use |
| Cross-case memory | ✅ Done | `add_memory` after synthesis; `recall_memory` in Claim Analyst |
| JSON parsing (strip fences) | ✅ Done | `_parse_json` / `_parse_claims_json` |

### 6. Forensics

| Feature | Status |
|---------|--------|
| Image: pHash | ✅ Done |
| Image: EXIF | ✅ Done |
| Image: ELA heatmap | ✅ Done |
| pHash comparison (REPOST_OF, MUTATION_OF) | ✅ Done |
| Video: TwelveLabs index/search/summarize | ✅ Done |

---

## Not Implemented / Partial

### 1. Backboard Fact Checker Not in Network Pipeline

**Spec:** Google Fact Check API results should be fed *into* the Fact Checker agent, which rates claims (VERIFIED, UNVERIFIED, LIKELY_FALSE, DEBUNKED) using shared thread context.

**Current:** Network pipeline calls Google Fact Check API directly and creates `FactCheck` nodes. The `ai.fact_check_claims` function exists but is **never invoked**.

**To implement:** In `network.py`, after updating the report with claims:
- Call `ai.fact_check_claims(claims, case_id, thread_ids)` (ensure threads exist)
- Optionally merge/compare Fact Check API results with agent verdicts
- Update report node or create structured output from agent

---

### 2. Shared Thread per Case vs Per-Assistant Threads

**Spec:** One Backboard thread per case shared by all agents.

**Current:** One thread **per assistant** per case (`_case_threads[case_id]` → `{claim_analyst: tid, fact_checker: tid, ...}`).

**Impact:** Agents do not share context across threads. The Claim Analyst and Fact Checker would need to pass context explicitly, or the architecture would need to align with Backboard SDK capabilities.

---

### 3. Alert Draft Without Case Threads

**Spec:** Alert Composer reads the full case thread.

**Current:** `ai.compose_alert` uses `get_thread_ids(case_id)`. If no report has been processed (e.g. officer drafts alert before network runs), threads are empty and the system falls back to Gemini with a snapshot-based context string.

**To implement:** Create case threads on-demand in the alerts router when drafting, if Backboard is available and threads are missing.

---

### 4. Auth Removed

| Component | Status |
|-----------|--------|
| JWT login | **Removed** (not needed for hackathon) |
| Officer route protection | None (all routes public) |
| Public vs officer endpoints | All public |

---

### 5. Storage

| Component | Status |
|-----------|--------|
| In-memory state | ✅ Done |
| Neo4j AuraDB driver | ✅ Done (optional; env: NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD) |
| Neo4j Case + Evidence | ✅ Done | create_case, add_evidence in graph_queries.py; CONTAINS edges |
| Neo4j in-memory sync | ❌ Not implemented (report flow still in-memory only) |
| Audit log | In-memory deque (max 10k); no persistence |

---

### 6. Testing & Verification

| Item | Status |
|------|--------|
| Manual curl/websocat tests | Documented in TESTING.md |
| Automated tests | ❌ None |
| WS /ws/caseboard graph_update | Marked unverified in todo.md |

---

### 7. Minor Gaps

| Item | Notes |
|------|-------|
| TTS audio URL | Placeholder `/api/alerts/{id}/audio`; not served |
| Backboard SDK sync vs async | `send_to_agent` etc. are async; if SDK is sync, may need `asyncio.to_thread()` |
| Model routing | Spec mentioned routing simple vs complex tasks; currently fixed models per agent |

---

## Summary Table

| Area | Implemented | Partial | Not Done |
|------|-------------|---------|----------|
| Core API & routes | ✅ | — | — |
| Blackboard + pipelines | ✅ | — | — |
| Backboard 4 agents | 3/4 wired | Fact Checker | — |
| External services | ✅ | — | — |
| Auth | Removed (not needed) | — | — |
| Persistence | — | — | DB, audit |
| Automated tests | — | — | All |

---

## Handoff for AI Agents

**See [AGENTS.md](../AGENTS.md)** (project root) and **[HANDOFF.md](HANDOFF.md)** for Claude Code / AI takeover instructions.

---

## Quick Reference: Key Files

| Purpose | File |
|---------|------|
| Backboard client & agents | `app/services/backboard_client.py` |
| Neo4j AuraDB | `app/services/graph_db.py` |
| Neo4j Cypher queries | `app/services/graph_queries.py` |
| AI routing (Backboard vs Gemini) | `app/services/ai.py` |
| Network pipeline (claims, fact check) | `app/pipelines/network.py` |
| Case synthesis | `app/pipelines/case_synthesizer.py` |
| Pipeline orchestration | `app/pipelines/orchestrator.py` |
| Architecture doc | `docs/HOW_IT_WORKS.md` |
| Flow doc | `docs/FLOW.md` |
| Test guide | `docs/TESTING.md` |
| AI handoff | `AGENTS.md`, `docs/HANDOFF.md` |
