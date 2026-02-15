# How Shadow Bureau Works

A technical overview of the backend architecture, data flow, and key components.

> **See also:** [FLOW.md](FLOW.md) for elaborative end-to-end flow documentation (startup, report submission, pipeline execution, reactive chains, alerts).

---

## Blackboard Architecture

Shadow Bureau uses the **Blackboard pattern** for reactive, multi-source analysis:

1. **Blackboard** = `graph_state.py` — the shared in-memory graph (nodes, edges)
2. **Knowledge Sources** = pipelines that read/write the blackboard: clustering, forensics, network, forensics_xref, classifier, recluster_debunk
3. **Controller** = `BlackboardController` — watches graph mutations via `notify(event_type, payload)`, schedules knowledge sources by priority with cooldowns and dedup

Every graph mutation (add_node, add_edge, update_node) triggers `broadcast_graph_update`, which also notifies the controller. The controller enqueues matching knowledge sources and executes them by priority (CRITICAL → HIGH → MEDIUM → LOW → BACKGROUND).

---

## High-Level Architecture

```
                    ┌─────────────────────────────────────────────────────────┐
                    │                     FastAPI App                          │
                    │  (lifespan: event bus + Blackboard controller)           │
                    └─────────────────────────────────────────────────────────┘
                                              │
        ┌─────────────────────────────────────┼─────────────────────────────────────┐
        │                                     │                                     │
        ▼                                     ▼                                     ▼
┌───────────────┐                   ┌─────────────────┐                   ┌───────────────┐
│   Public API   │                   │  Officer API    │                   │  WebSockets   │
│ POST /report  │                   │ GET /reports    │                   │ /ws/caseboard │
│ GET /alerts   │                   │ GET /cases      │                   │ /ws/alerts    │
│               │                   │ POST /alerts/*  │                   │               │
└───────┬───────┘                   └────────┬────────┘                   └───────┬───────┘
        │                                     │                                     │
        └─────────────────────────────────────┼─────────────────────────────────────┘
                                              │
                    ┌─────────────────────────┼─────────────────────────┐
                    │                         ▼                         │
                    │              ┌─────────────────────┐               │
                    │              │   Blackboard (Graph) │               │
                    │              │  nodes + edges      │◄──────────────┼── notify()
                    │              │  ConnectionManager  │               │
                    │              └──────────┬──────────┘               │
                    │                         │ broadcasts               │
                    │  ┌──────────────────────┴──────────────────────┐   │
                    │  │       BlackboardController (PriorityQueue)   │   │
                    │  │  CRITICAL: clustering                        │   │
                    │  │  HIGH: forensics, recluster_debunk            │   │
                    │  │  MEDIUM: network, forensics_xref             │   │
                    │  │  LOW: classifier                             │   │
                    │  └──────────────────────┬──────────────────────┘   │
                    │                         │                         │
                    └─────────────────────────┼─────────────────────────┘
                                              │
                                    Knowledge Sources (pipelines)
```

---

## Report Flow: Tip Submission to Case Board

When a student submits a tip via `POST /api/report`:

### 1. Report Ingestion

1. Backend generates a **noir-themed case ID** (e.g. `CASE-MIDNIGHT-CIPHER-7203`) and a unique report ID.
2. A **Report node** is created in the in-memory graph with the tip data (text, location, media URL, etc.).
3. The report is stored and linked to the case.
4. A `graph_update` is broadcast to all `/ws/caseboard` clients so the dashboard updates in real time.
5. A **ReportReceived** event is emitted to the event bus.
6. The API returns 201 with `case_id` and `report_id`.

### 2. Blackboard Controller & Knowledge Sources

When the report node is added, `broadcast_graph_update` notifies the controller with `node:report`. The controller evaluates registered knowledge sources:

| Priority | Source | Triggers | Condition |
|----------|--------|----------|-----------|
| CRITICAL | clustering | node:report, edge:repost_of, edge:mutation_of | — |
| HIGH | forensics | node:report | media_url exists |
| HIGH | recluster_debunk | edge:debunked_by | — |
| MEDIUM | network | node:report | — |
| MEDIUM | forensics_xref | update:report | claims exist |
| LOW | classifier | edge:similar_to, edge:repost_of, edge:mutation_of, edge:debunked_by, node:fact_check, node:external_source | — |

Sources run by priority. Each has a cooldown (1–3 seconds per case) and a max of 10 re-triggers per case to prevent infinite loops.

**Reactive chains:**
- Network writes claims → `update:report` → forensics_xref (TwelveLabs search for claim-specific content), classifier
- Forensics writes pHash match → `edge:repost_of` / `edge:mutation_of` → clustering re-runs, classifier
- Fact check writes debunk → `edge:debunked_by` → recluster_debunk (updates debunk count), classifier

### 3. Pipeline 1: Forensic Scanner

**Goal:** Analyze media and link duplicates or variants.

- **Images:** Fetches the image, computes perceptual hash (pHash), EXIF (GPS, device, timestamp), and ELA heatmap if supported.
- **Videos:** Uses TwelveLabs to index (Marengo), search, and summarize (Pegasus).
- **pHash comparison:** Compares the new media’s hash with all existing `MediaVariant` nodes:
  - **0–5:** Exact copy → `REPOST_OF` edge
  - **6–15:** Modified → `MUTATION_OF` edge
  - **>15:** No edge
- Adds `MediaVariant` nodes and edges to the graph and broadcasts updates.

### 4. Pipeline 2: Network Crawler

**Goal:** Extract claims, fact-check them, and suggest search queries.

1. **Claim extraction (Gemini):** Extracts claims with confidence and category, misinformation flags, and suggested verifications.
2. **Report node update:** Attaches claims, urgency, misinformation_flags, suggested_verifications to the report node.
3. **Fact checking:** For each claim, calls the Google Fact Check API and creates `FactCheck` nodes linked by `DEBUNKED_BY` edges.
4. **Search queries:** Uses Gemini to generate 2–3 search queries for related content; creates `ExternalSource` nodes with `SIMILAR_TO` edges.

### 5. Pipeline 3: Clustering

**Goal:** Link similar reports to the same incident.

Combines three signals with weights:

| Signal      | Weight | Rule                           |
|------------|--------|--------------------------------|
| Temporal   | 0.3    | Within 30 minutes              |
| Geographic | 0.3    | Within 200 m (haversine)       |
| Semantic   | 0.4    | Keyword overlap                |

If the combined score ≥ 0.4, a `SIMILAR_TO` edge is created between the two report nodes.

### 6. Additional Knowledge Sources

- **forensics_xref:** When a report node is updated with claims, searches TwelveLabs for claim-specific video content.
- **recluster_debunk:** When a `DEBUNKED_BY` edge is added, updates report nodes with debunk count.
- **classifier:** Assigns semantic roles to report nodes: Originator (earliest), Amplifier (REPOST_OF), Mutator (MUTATION_OF), Unwitting Sharer (no outgoing edges to external sources).

---

## Graph Model

### Node Types

| Type             | Description                                  |
|------------------|----------------------------------------------|
| `report`         | Student tip (text, location, claims, etc.). May have `semantic_role` (originator, amplifier, mutator, unwitting_sharer), `debunk_count`. |
| `media_variant`  | Analyzed image/video (pHash, EXIF, summary)  |
| `fact_check`     | Fact-check result (rating, reviewer, URL)   |
| `external_source`| Related content query (search_query, status)|

### Edge Types

| Type          | Meaning                     |
|---------------|-----------------------------|
| `similar_to`  | Related by time/geo/semantics |
| `repost_of`   | Exact copy (pHash 0–5)     |
| `mutation_of` | Modified version (pHash 6–15) |
| `debunked_by` | Claim → fact check         |
| `amplified_by`| Reshare without modification |

---

## Officer Workflow: Alerts

1. **Draft:** `POST /api/alerts/draft` with `case_id`. Gemini generates a public safety alert from case context and officer notes.
2. **Approve:** `POST /api/alerts/approve` with `case_id`, `final_text`, `status`. Publishes the alert, stores it, and broadcasts `{type: "new_alert", alert: {...}}` to `/ws/alerts`.
3. **TTS (optional):** If ElevenLabs is configured, generates speech from the alert text (audio URL is placeholdered for now).

---

## WebSockets

| Endpoint       | Purpose                                                                 |
|----------------|-------------------------------------------------------------------------|
| `/ws/caseboard`| On connect: sends all case snapshots. Then streams `graph_update` messages (add_node, add_edge, update_node) in real time. |
| `/ws/alerts`   | Streams `new_alert` messages when officers publish alerts.             |

The `ConnectionManager` maintains separate sets for caseboard and alert clients. Dead connections are removed when a send fails.

---

## External Services

All services degrade safely when API keys are missing: mock data is returned, logs warn, and the app keeps running.

| Service    | Purpose                         | Fallback                        |
|-----------|----------------------------------|---------------------------------|
| **Backboard.io** | Multi-agent AI: Claim Analyst, Fact Checker, Alert Composer, Case Synthesizer. Persistent case threads, cross-case memory. | Falls back to Gemini |
| **Gemini**| Claim extraction, alert composition, search queries (fallback when Backboard unavailable) | Mock claims, generic alert text |
| **Neo4j AuraDB** | Graph database for persistence (optional). Singleton driver in `graph_db.py`, FastAPI dependency `GraphDatabase.get_session()`. Verified on startup with `RETURN 1`. | Driver not initialized if env vars missing |
| **Google Fact Check** | Verify claims              | Empty results                  |
| **TwelveLabs** | Video index (Marengo), search, summarize (Pegasus) | Empty results        |
| **ElevenLabs** | Text-to-speech for alerts   | No audio                       |

### Backboard Multi-Agent Architecture

When `BACKBOARD_API_KEY` is set, the system uses 4 specialized Backboard assistants:

- **Claim Analyst** — Extracts claims from report text, flags misinformation patterns
- **Fact Checker** — Rates claims (VERIFIED, UNVERIFIED, LIKELY_FALSE, DEBUNKED)
- **Alert Composer** — Drafts public safety alerts from full case context (Claude)
- **Case Synthesizer** — Produces narrative, origin analysis, spread map, confidence score

Each case gets persistent threads per assistant. Cross-case memory stores key findings for pattern recognition.

---

## Storage & State

- **In-memory:** Reports, nodes, and edges live in Python dicts and lists.
- **Neo4j AuraDB:** Optional. When `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD` are set, a singleton driver connects on startup. Use `Depends(GraphDatabase.get_session)` to inject a session. **Case creation** (`POST /api/cases`), **evidence ingestion** (`POST /api/cases/{id}/evidence`), and **Red String** (`POST /api/cases/{id}/edges`) persist to Neo4j. Evidence nodes are linked to Case via `CONTAINS` edges. Manual links between nodes create `RELATED` edges and emit `edge:created` on the event bus for AI analysis. **Graph fetch** (`GET /api/cases/{id}/graph`) returns the full case graph from Neo4j in React Flow format (nodes with `id`, `position`, `data`; edges with `id`, `source`, `target`, `type`).
- **Audit log:** In-memory deque (max 10k entries) for actions like `report_submitted`, `alert_drafted`, `alert_approved`.

**Note:** All routes are public (no authentication required for hackathon).
