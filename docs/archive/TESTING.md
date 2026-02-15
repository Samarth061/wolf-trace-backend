# How to Test Shadow Bureau Backend

## Prerequisites

1. **Start the server**
   ```bash
   uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

2. **Optional:** `websocat` for WebSocket testing
   ```bash
   # Install: cargo install websocat  OR  brew install websocat
   ```

---

## 1. Health Check

```bash
curl -s http://localhost:8000/health
# Expected: {"status":"ok"}
```

---

## 2. Submit a Report

```bash
curl -X POST http://localhost:8000/api/report \
  -H "Content-Type: application/json" \
  -d '{
    "text_body": "Threatening video circulating near the library",
    "location": {"lat": 35.7847, "lng": -78.6821, "building": "D.H. Hill Library"},
    "media_url": "https://example.com/upload123.jpg",
    "anonymous": true
  }'
```

**Expected:** `201` with `case_id` (e.g. `CASE-MIDNIGHT-CIPHER-4821`) and `report_id`.

---

## 3. List Reports

```bash
curl -s http://localhost:8000/api/reports
```

**Expected:** JSON array of reports (includes the one you just submitted).

---

## 4. List Cases

```bash
curl -s http://localhost:8000/api/cases
```

**Expected:** Array of cases with `case_id`, `report_count`, `node_count`, `edge_count`.

---

## 4b. Create Case (Neo4j)

Requires Neo4j configured. Creates a Case node in Neo4j:

```bash
curl -X POST http://localhost:8000/api/cases \
  -H "Content-Type: application/json" \
  -d '{"case_id": "CASE-NEO4J-001", "title": "Library Incident", "description": "Reported suspicious activity"}'
```

**Expected:** `201` with `id`, `title`, `description`, `created_at`.

---

## 4c. Add Evidence to Case (Neo4j)

Requires the case to exist in Neo4j (create via 4b first). Links Evidence to Case via CONTAINS:

```bash
curl -X POST http://localhost:8000/api/cases/CASE-NEO4J-001/evidence \
  -H "Content-Type: application/json" \
  -d '{
    "id": "ev-001",
    "type": "photo",
    "content": "Photo of entrance",
    "url": "https://example.com/evidence.jpg",
    "timestamp": "2026-02-14T12:00:00"
  }'
```

**Expected:** `200` with `id`, `type`, `content`, `url`, `timestamp`.

---

## 4d. Get Case Graph (Neo4j, React Flow)

Fetches the full graph for a case from Neo4j, formatted for React Flow:

```bash
curl -s http://localhost:8000/api/cases/CASE-NEO4J-001/graph | jq .
```

**Expected:** `{ nodes: [...], edges: [...], case_id: "..." }`. Each node has `id`, `position: {x, y}`, `data: { label, nodeType, type, content, ... }`. Each edge has `id`, `source`, `target`, `type`.

---

## 4e. Red String: Link Two Nodes (Neo4j)

Creates a RELATED edge between two Node nodes. Emits `edge:created` for AI analysis.

```bash
curl -X POST http://localhost:8000/api/cases/CASE-NEO4J-001/edges \
  -H "Content-Type: application/json" \
  -d '{
    "source_id": "ev-001",
    "target_id": "ev-002",
    "type": "SUSPECTED_LINK",
    "note": "Witness A mentioned witness B"
  }'
```

**Expected:** `200` with `source_id`, `target_id`, `type`, `note`, `created_at`.

---

## 5. Get Case Graph Snapshot

Use a `case_id` from step 2 or 4:

```bash
curl -s http://localhost:8000/api/cases/CASE-MIDNIGHT-CIPHER-4821
```

**Expected:** `case_id`, `nodes`, `edges` arrays.

---

## 6. Draft an Alert

```bash
curl -X POST http://localhost:8000/api/alerts/draft \
  -H "Content-Type: application/json" \
  -d '{"case_id": "CASE-MIDNIGHT-CIPHER-4821", "officer_notes": "Verify with campus security"}'
```

**Expected:** `draft_text`, `status`, `location_summary`.

---

## 7. Approve & Publish Alert

```bash
curl -X POST http://localhost:8000/api/alerts/approve \
  -H "Content-Type: application/json" \
  -d '{
    "case_id": "CASE-MIDNIGHT-CIPHER-4821",
    "final_text": "Campus Safety Notice: We are investigating a reported incident near D.H. Hill Library. Avoid the area. Check official channels for updates.",
    "status": "Investigating"
  }'
```

**Expected:** Published alert with `id`, `text`, `status`.

---

## 8. Public Alert Feed

```bash
curl -s http://localhost:8000/api/alerts
```

**Expected:** Array of published alerts.

---

## 9. WebSocket: Caseboard

Connect to receive graph updates:

```bash
websocat ws://localhost:8000/ws/caseboard
```

**On connect:** You receive `{"type":"snapshots","payload":[...]}` with all case snapshots.

**Tip:** In another terminal, submit a report (step 2). You should see `graph_update` messages stream in with `add_node`, `add_edge`, `update_node` actions.

---

## 10. WebSocket: Alerts

```bash
websocat ws://localhost:8000/ws/alerts
```

**Tip:** In another terminal, approve an alert (step 7). You should receive `{"type":"new_alert","alert":{...}}`.

---

## Quick Smoke Test (One-Liner)

```bash
curl -s http://localhost:8000/health && \
curl -s -X POST http://localhost:8000/api/report -H "Content-Type: application/json" -d '{"text_body":"Test tip","anonymous":true}' | jq .case_id
```

---

## API Keys (Optional)

Without API keys, the backend uses mock data. To test real AI/API behavior, set in `.env`:

- `BACKBOARD_API_KEY` — multi-agent AI (Claim Analyst, Alert Composer, etc.)
- `GEMINI_API_KEY` — claim extraction, alert draft (fallback)
- `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD` — Neo4j AuraDB. On startup, look for `Neo4j connection verified (RETURN 1 OK)` in logs.
- `FACTCHECK_API_KEY` or `GEMINI_API_KEY` — fact checking
- `TWELVELABS_*` — video analysis
- `ELEVENLABS_*` — TTS for alerts
