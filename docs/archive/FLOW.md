# Shadow Bureau: Complete Flow Documentation

Elaborative documentation of the end-to-end data flow, from application startup through report submission, pipeline execution, and officer workflows.

---

## Table of Contents

1. [Application Startup](#1-application-startup)
2. [Report Submission Flow](#2-report-submission-flow)
3. [Blackboard Controller & Event Propagation](#3-blackboard-controller--event-propagation)
4. [Pipeline Execution (Knowledge Sources)](#4-pipeline-execution-knowledge-sources)
5. [Reactive Chains & Cascading Updates](#5-reactive-chains--cascading-updates)
6. [Officer Workflow: Alerts](#6-officer-workflow-alerts)
7. [WebSocket Real-Time Updates](#7-websocket-real-time-updates)
8. [Data Flow Diagrams](#8-data-flow-diagrams)

---

## 1. Application Startup

```
main.py lifespan
    │
    ├─► start_event_bus()
    │       Creates asyncio.Queue, starts _dispatch_loop task
    │       Event handlers registered via @on("ReportReceived") etc.
    │
    ├─► get_or_create_assistants()  [if BACKBOARD_API_KEY set]
    │       Lists existing Backboard assistants by name
    │       Creates missing: Claim Analyst, Fact Checker, Alert Composer, Case Synthesizer
    │       Stores in _assistants dict
    │
    ├─► GraphDatabase.get_instance() + verify_connection()  [if NEO4J_URI set]
    │       Singleton Neo4j driver (AuraDB)
    │       Runs "RETURN 1" to verify connection
    │       Logs success or failure
    │
    ├─► register_knowledge_sources()
    │       Creates BlackboardController
    │       Registers 8 knowledge sources with priorities and triggers (see §4)
    │
    ├─► set_controller(controller)
    │       Injects controller into graph_state for notify() calls
    │
    └─► controller.start()
            Spawns asyncio task running controller.run() loop
            Loop: await queue.get() → execute_task → repeat

    [On shutdown]
    └─► graph_db.close()
            Shuts down Neo4j driver
```

**Key files:** `app/main.py`, `app/event_bus.py`, `app/services/backboard_client.py`, `app/services/graph_db.py`, `app/pipelines/orchestrator.py`, `app/graph_state.py`

---

## 2. Report Submission Flow

When a student submits a tip via `POST /api/report`:

### Step-by-Step

| Step | Action | File / Component |
|------|--------|------------------|
| 1 | Request body parsed as `ReportCreate` (text_body, location, media_url, etc.) | `routers/reports.py` |
| 2 | Generate noir-themed `case_id` (e.g. `CASE-MIDNIGHT-CIPHER-7203`) | `utils/ids.py` |
| 3 | Generate unique `report_id` | `utils/ids.py` |
| 4 | Build `report_data` dict: text_body, location, timestamp, media_url, anonymous, status, created_at | `routers/reports.py` |
| 5 | Create `Report` node via `create_and_add_node(NodeType.REPORT, case_id, report_data, node_id=report_id)` | `graph_state.py` |
| 6 | Node stored in `_nodes`, returned as `report_node` | `graph_state.py` |
| 7 | `broadcast_graph_update("add_node", report_node.model_dump())` | `graph_state.py` |
| 8 | **WebSocket:** All `/ws/caseboard` clients receive `{type: "graph_update", action: "add_node", payload: {...}}` | `graph_state.py` → `ConnectionManager` |
| 9 | **Controller:** `notify("node:report", payload)` enqueues matching knowledge sources | `graph_state.py` → `BlackboardController` |
| 10 | `add_report(case_id, report_id, report_data, report_node_id)` stores in `_reports` and `_case_reports` | `graph_state.py` |
| 11 | `log_action(...)` appends to audit deque | `utils/audit.py` |
| 12 | `emit("ReportReceived", {case_id, report_id, report_node_id, report_data})` | `event_bus.py` |
| 13 | Return 201 with `ReportOut` (case_id, report_id, text_body, etc.) | `routers/reports.py` |

### Payload Structure

The `add_node` payload (and thus the controller `notify` payload) has:

```json
{
  "id": "report_id_or_generated",
  "node_type": "report",
  "case_id": "CASE-MIDNIGHT-CIPHER-7203",
  "data": {
    "text_body": "...",
    "location": {"lat": 35.78, "lng": -78.68, "building": "Library"},
    "timestamp": "2026-02-14T12:00:00",
    "media_url": "https://...",
    "anonymous": true,
    "status": "processing"
  },
  "created_at": "..."
}
```

---

## 3. Blackboard Controller & Event Propagation

### Event Type Derivation

Every `broadcast_graph_update(action, payload)` triggers:

1. WebSocket broadcast to caseboard clients
2. `event_type = _event_type_from_action(action, payload)`:
   - `add_node` → `node:{node_type}` (e.g. `node:report`, `node:fact_check`)
   - `add_edge` → `edge:{edge_type}` (e.g. `edge:similar_to`, `edge:debunked_by`)
   - `update_node` → `update:{node_type}` (e.g. `update:report`)

3. `_controller.notify(event_type, payload)`

### Controller Logic

```
notify(event_type, payload)
    │
    ├─► Extract case_id from payload; if missing, return
    ├─► If trigger_count[case_id] >= 10, return (anti-loop)
    │
    └─► For each registered knowledge source:
            if can_fire(event_type, payload):
                - event_type in trigger_types
                - condition(payload) is True (if condition exists)
                - case_id present
                - Not already active (source:case_id not in active_tasks)
                - Cooldown elapsed since last run for this case
                ► Enqueue QueuedTask(priority, sequence, source_name, case_id, event_type, payload)
                ► Add to active_tasks, increment trigger_count
```

### Priority Order

Tasks are processed by `(priority, sequence)`. Lower priority number = higher precedence:

| Priority | Value | Sources |
|----------|-------|---------|
| CRITICAL | 0 | clustering |
| HIGH | 1 | forensics, recluster_debunk |
| MEDIUM | 2 | network, forensics_xref |
| LOW | 3 | classifier |
| BACKGROUND | 4 | case_synthesizer |

---

## 4. Pipeline Execution (Knowledge Sources)

### 4.1 Clustering (CRITICAL)

**Triggers:** `node:report`, `edge:repost_of`, `edge:mutation_of`  
**Cooldown:** 2s  
**Condition:** case_id and (node_type==report OR report_data OR edge_type)

**Flow:**

1. Get `report_node_id`, `report_data` from payload (for edge triggers, use first report node in case)
2. Parse report timestamp and location
3. For each existing report (excluding same case/report):
   - **Temporal score (0.3):** 1.0 if within 30 min, else decay
   - **Geographic score (0.3):** 1.0 if within 200 m (haversine), else decay
   - **Semantic score (0.4):** Jaccard-like keyword overlap (words > 3 chars)
4. If combined score ≥ 0.4: create `SIMILAR_TO` edge (report → other_report)
5. `broadcast_graph_update("add_edge", edge)` → triggers classifier

---

### 4.2 Forensics (HIGH)

**Triggers:** `node:report`  
**Condition:** `media_url` exists in payload  
**Cooldown:** 2s

**Flow:**

1. Fetch `case_id`, `report_node_id`, `media_url` from payload
2. **If image** (not .mp4/.mov/etc.):
   - `analyze_media_from_url(media_url)` → pHash, EXIF, ELA
   - Create `MediaVariant` node with phash, exif, ela_available, media_url
   - Compare pHash (hamming distance) to all existing MediaVariants:
     - 0–5: create `REPOST_OF` edge (report → media_variant)
     - 6–15: create `MUTATION_OF` edge
   - Broadcast add_node, add_edge
   - **Side effect:** `edge:repost_of` / `edge:mutation_of` → clustering re-runs
3. **If video:**
   - TwelveLabs: index (Marengo), search, summarize (Pegasus)
   - Create MediaVariant with summary, add edges, broadcast

---

### 4.3 Network (MEDIUM)

**Triggers:** `node:report`  
**Cooldown:** 1s

**Flow:**

1. Get report text, location, timestamp from payload
2. **Claim extraction:**
   - If Backboard available: create case thread, recall memory, send to Claim Analyst agent, parse JSON
   - Else: `gemini.extract_claims(report_text)`
   - Extracted: claims[], urgency, misinformation_flags, suggested_verifications
3. **Update report node** with claims, urgency, etc. → `broadcast_graph_update("update_node", ...)`
   - Triggers: `update:report` → forensics_xref, case_synthesizer (if claims exist)
4. **Fact checking (per claim):**
   - `factcheck.search_claims(statement)` (Google Fact Check API)
   - For each result (top 3): create `FactCheck` node, `DEBUNKED_BY` edge (report → fact_check)
   - Broadcast add_node, add_edge → triggers recluster_debunk, classifier
5. **Search queries:**
   - `gemini.generate_search_queries(claims)` → 2–3 queries
   - Create `ExternalSource` nodes with `SIMILAR_TO` edges
   - Broadcast → triggers classifier

---

### 4.4 Forensics XRef (MEDIUM)

**Triggers:** `update:report`  
**Condition:** Report has `claims` in data  
**Cooldown:** 3s

**Flow:**

1. Get report node; verify it has claims
2. For top 2 claims: `twelvelabs.search_videos(statement)`
3. For each result (top 2): create `ExternalSource` (platform: twelvelabs), `SIMILAR_TO` edge
4. Broadcast → triggers classifier

---

### 4.5 Recluster Debunk (HIGH)

**Triggers:** `edge:debunked_by`  
**Cooldown:** 1s

**Flow:**

1. Get all edges for case
2. Count `DEBUNKED_BY` edges per source_id (report nodes)
3. Update each report node with `debunk_count`
4. Broadcast update_node → triggers classifier

---

### 4.6 Classifier (LOW)

**Triggers:** `edge:similar_to`, `edge:repost_of`, `edge:mutation_of`, `edge:debunked_by`, `node:fact_check`, `node:external_source`  
**Cooldown:** 2s

**Flow:**

1. Get all report nodes for case
2. For each node, determine `semantic_role`:
   - Has `MUTATION_OF` out → **Mutator**
   - Has `REPOST_OF` out → **Amplifier**
   - Earliest timestamp among reports → **Originator**
   - No external/similar edges → **Unwitting Sharer**
3. `update_node(id, {semantic_role})`, broadcast

---

### 4.7 Case Synthesizer (BACKGROUND)

**Triggers:** `update:report`  
**Condition:** Report has claims  
**Cooldown:** 5s

**Flow:**

1. Ensure Backboard available and case threads exist (create if needed)
2. Build case context from graph snapshot (nodes + data)
3. Send to Case Synthesizer agent: "Synthesize the full case"
4. Parse JSON: narrative, origin_analysis, spread_map, confidence_assessment, recommended_action
5. Update all report nodes in case with: case_narrative, origin_analysis, spread_map, confidence_score, recommended_action
6. Broadcast update_node
7. **Memory:** `add_memory("claim_analyst", "Case X: narrative...")` for cross-case learning

---

## 5. Reactive Chains & Cascading Updates

```
Report added (node:report)
    │
    ├─► clustering    [CRITICAL]  → may add SIMILAR_TO edge
    │       └─► edge:similar_to → classifier
    │
    ├─► forensics    [HIGH]       → if media_url
    │       └─► add MediaVariant, REPOST_OF/MUTATION_OF
    │       └─► edge:repost_of / edge:mutation_of → clustering, classifier
    │
    └─► network      [MEDIUM]     → extract claims, fact-check, search
            └─► update_node (claims) → update:report
            └─► forensics_xref [MEDIUM]  → TwelveLabs search on claims
            └─► case_synthesizer [BACKGROUND] → narrative, origin, spread map
            │
            └─► add FactCheck nodes, DEBUNKED_BY edges
                └─► edge:debunked_by → recluster_debunk, classifier
                └─► recluster_debunk → update debunk_count → update:report → classifier
            │
            └─► add ExternalSource nodes, SIMILAR_TO edges
                └─► node:external_source → classifier
```

**Anti-loop safeguards:**
- Max 10 triggers per case per controller run
- Cooldowns (1–5 s) per source per case
- Active task tracking (same source:case cannot run concurrently)

---

## 6. Officer Workflow: Alerts

### 6.1 Draft Alert (`POST /api/alerts/draft`)

```
Request: { case_id, officer_notes? }
    │
    ├─► get_case_snapshot(case_id) → nodes, edges
    ├─► Build context string from nodes (up to 10)
    ├─► ai.compose_alert(context, officer_notes, case_id)
    │       │
    │       ├─► If Backboard + case_id:
    │       │       threads = get_thread_ids(case_id)
    │       │       if alert_composer thread exists:
    │       │           send_to_agent("alert_composer", tid, "Draft alert...")
    │       │           parse JSON → alert_text
    │       │       else: fallback
    │       │
    │       └─► Else: gemini.compose_alert(context, officer_notes)
    │
    ├─► log_action("system", "alert_drafted", case_id)
    └─► Return { case_id, draft_text, status, location_summary }
```

### 6.2 Red String: Link Nodes (`POST /api/cases/{case_id}/edges`)

Creates a RELATED edge between two Node nodes (e.g. Evidence). Triggers AI analysis.

```
Request: { source_id, target_id, type?, note? }
    │
    ├─► graph_queries.create_link(session, case_id, edge_data)
    │       MATCH (a:Node {id: source_id}), (b:Node {id: target_id})
    │       MERGE (a)-[r:RELATED {type}]->(b)
    │       SET r.created_at, r.note, r.manual = true
    │       RETURN a, b, r
    │
    └─► emit("edge:created", { case_id, source, target, relation })
            Event bus dispatches to @on("edge:created") handlers (AI analysis phase)
```

### 6.3 Approve Alert (`POST /api/alerts/approve`)

```
Request: { case_id, final_text, status }
    │
    ├─► Generate alert_id
    ├─► If ElevenLabs configured: text_to_speech(final_text) → audio bytes
    │       (audio_url placeholder: /api/alerts/{id}/audio — not yet served)
    ├─► Build alert_data: id, case_id, text, status, audio_url, created_at
    ├─► Append to _alerts list
    ├─► log_action("system", "alert_approved", case_id, alert_id)
    ├─► connection_manager.broadcast_alert({ type: "new_alert", alert: alert_data })
    └─► Return AlertOut
```

### 6.3 Public Alert Feed (`GET /api/alerts`)

Returns all published alerts from in-memory `_alerts` list.

---

## 7. WebSocket Real-Time Updates

### 7.1 `/ws/caseboard`

```
Client connects
    │
    ├─► connection_manager.connect_caseboard(websocket)
    ├─► get_all_snapshots() → list of { case_id, nodes, edges }
    ├─► send_json({ type: "snapshots", payload: snapshots })
    │
    └─► Loop: receive_text() (keepalive; client can send pings)

Whenever broadcast_graph_update() is called anywhere:
    └─► All caseboard clients receive:
        { type: "graph_update", action: "add_node"|"add_edge"|"update_node", payload: {...}, timestamp }
```

### 7.2 `/ws/alerts`

```
Client connects
    │
    ├─► connection_manager.connect_alert(websocket)
    └─► Loop: receive_text()

Whenever alert is approved:
    └─► All alert clients receive:
        { type: "new_alert", alert: { id, case_id, text, status, ... } }
```

---

## 8. Data Flow Diagrams

### End-to-End: Report to Case Board

```
┌─────────────┐     POST /report      ┌─────────────────┐
│   Student   │ ─────────────────────►│  reports router │
└─────────────┘                       └────────┬────────┘
                                               │
                                               ▼
                                    ┌──────────────────────┐
                                    │ create_and_add_node   │
                                    │ (Report)              │
                                    └──────────┬───────────┘
                                               │
                    ┌──────────────────────────┼──────────────────────────┐
                    │                          │                          │
                    ▼                          ▼                          ▼
          ┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
          │ broadcast_graph │       │ add_report()     │       │ emit(ReportRcvd) │
          │ _update         │       │ log_action       │       └─────────────────┘
          └────────┬────────┘       └─────────────────┘
                   │
        ┌──────────┴──────────┐
        ▼                     ▼
┌───────────────┐    ┌──────────────────┐
│ WS caseboard  │    │ BlackboardCtrl  │
│ clients       │    │ notify()         │
└───────────────┘    └────────┬────────┘
                              │
                              ▼
                    ┌─────────────────────┐
                    │ Priority Queue      │
                    │ clustering          │
                    │ forensics           │
                    │ network             │
                    │ forensics_xref      │
                    │ recluster_debunk    │
                    │ classifier          │
                    │ case_synthesizer    │
                    └─────────┬───────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
        add nodes       add edges      update nodes
              │               │               │
              └───────────────┴───────────────┘
                              │
                              ▼
                    broadcast_graph_update
                              │
                              ▼
                    WS clients + controller (recursive)
```

### AI Layer Flow (Claims & Alerts)

```
report text
    │
    ▼
┌─────────────────────────────────────────────────────┐
│ ai.extract_claims()                                  │
│   BACKBOARD_API_KEY?                                 │
│     Yes → create_case_thread → recall_memory         │
│         → send_to_agent("claim_analyst", ...)       │
│         → parse JSON                                 │
│     No  → gemini.extract_claims()                    │
└─────────────────────────────────────────────────────┘
    │
    ▼
claims[], urgency, misinformation_flags, suggested_verifications
    │
    ├─► report node update
    ├─► Google Fact Check API → FactCheck nodes
    └─► gemini.generate_search_queries → ExternalSource nodes


case context + officer_notes
    │
    ▼
┌─────────────────────────────────────────────────────┐
│ ai.compose_alert()                                   │
│   BACKBOARD + thread_ids?                            │
│     Yes → send_to_agent("alert_composer", ...)      │
│         → Claude, parse JSON                         │
│     No  → gemini.compose_alert()                     │
└─────────────────────────────────────────────────────┘
    │
    ▼
draft_text (alert body)
```

---

## Related Documentation

- **[HOW_IT_WORKS.md](HOW_IT_WORKS.md)** — Architecture overview, graph model, external services
- **[IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)** — What's built vs. pending
- **[TESTING.md](TESTING.md)** — curl and WebSocket test procedures
