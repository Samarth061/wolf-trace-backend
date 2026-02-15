# Backend Integration Changelog

## Overview
This document tracks changes made to align the Shadow Bureau backend with the WolfTrace frontend (wolf-trace-ui-design).

---

## Recent Changes (2024-02-14)

### 1. Enhanced Case API Response Shapes

**File: `app/graph_state.py`**

Added comprehensive case metadata support:

```python
# New case metadata system
_case_metadata: dict[str, dict[str, Any]] = {}

def set_case_metadata(case_id: str, metadata: dict[str, Any]) -> None:
    """Store extra case metadata (label, status, location, summary, story) for seed data."""
    _case_metadata[case_id] = metadata

def get_case_metadata(case_id: str) -> dict[str, Any]:
    """Retrieve case metadata."""
    return _case_metadata.get(case_id, {})

def clear_all() -> None:
    """Clear all in-memory state. Used by seed endpoint."""
    _reports.clear()
    _nodes.clear()
    _edges.clear()
    _adjacency.clear()
    _case_reports.clear()
    _case_metadata.clear()  # NEW
```

Enhanced `get_all_cases()` to derive fields from report nodes:
- `updated_at` - Latest report timestamp
- `summary` - First report text_body (200 chars)
- `location` - From first report's location.building
- `story` - Concatenated report timeline

**File: `app/models/case.py`**

Expanded `CaseOut` model to match frontend expectations:

```python
class CaseOut(BaseModel):
    id: str
    case_id: str = ""          # NEW
    title: str
    description: str
    label: str = ""            # NEW - Frontend uses this for case display name
    status: str = "active"     # NEW
    node_count: int = 0        # NEW
    updated_at: Optional[str] = None  # NEW
    created_at: Optional[str] = None
```

**File: `app/routers/cases.py`**

Fixed `POST /api/cases/{case_id}/evidence` endpoint:
- Now returns `GraphNode` shape (not flat EvidenceOut)
- Adds to in-memory graph state via `create_and_add_node()`
- Broadcasts WebSocket update via `broadcast_graph_update()`

Fixed `POST /api/cases/{case_id}/edges` endpoint:
- Adds edge to in-memory state via `create_and_add_edge()`
- Broadcasts WebSocket update
- Emits `edge:created` event for AI pipeline trigger

---

### 2. Mock Data Seed System

**New File: `app/seed_data.py`**

Translates all frontend mock data to Python:
- 10 cases with full metadata
- 27 evidence items
- 20 evidence connections
- 4 public tips

Key function:
```python
def seed_all() -> dict[str, int]:
    """
    Populate in-memory graph with mock data from frontend.
    Idempotent: clears existing data first.
    Returns counts of created items.
    """
    clear_all()
    # Creates cases, evidence, connections, tips
    return {
        "cases": len(MOCK_CASES),
        "evidence": len(MOCK_EVIDENCE),
        "connections": len(MOCK_EVIDENCE_CONNECTIONS),
        "tips": len(MOCK_TIPS),
    }
```

**New File: `app/routers/seed.py`**

New endpoint:
```python
@router.post("/seed")
async def seed_mock_data():
    """Populate backend with mock data from frontend for testing. Idempotent."""
    counts = seed_all()
    return {"status": "seeded", **counts}
```

**Modified: `app/main.py`**

Registered seed router:
```python
app.include_router(seed.router)  # Line 70
```

---

### 3. Case Metadata for Cases Without Evidence

**Issue:** Frontend has 10 cases, but only 3 had evidence. Cases 004-010 didn't appear in backend.

**Fix in `seed_data.py`:**

```python
# Create placeholder report nodes for cases without evidence
cases_with_evidence = {ev["caseId"] for ev in MOCK_EVIDENCE}
for case in MOCK_CASES:
    if case["id"] not in cases_with_evidence:
        placeholder_id = f"rpt-{case['id']}"
        # Create minimal report node
        report_data = {
            "report_id": placeholder_id,
            "case_id": case["id"],
            "text_body": case.get("summary", ""),
            "timestamp": case.get("lastUpdated", datetime.now().isoformat()),
            "anonymous": True,
        }
        _reports[placeholder_id] = report_data
        add_report(case["id"], placeholder_id, report_data, placeholder_id)
```

---

## API Endpoints Status

### ✅ Working Endpoints

| Method | Path | Response Shape | Frontend Usage |
|--------|------|---------------|----------------|
| GET | `/health` | `{ status, knowledge_sources, controller_running }` | Health check |
| GET | `/api/cases` | `CaseOut[]` with full metadata | Case Wall |
| POST | `/api/cases` | `CaseOut` | Create case |
| GET | `/api/cases/{id}` | Case snapshot with nodes/edges | Case detail |
| POST | `/api/cases/{id}/evidence` | `GraphNode` | Add evidence |
| POST | `/api/cases/{id}/edges` | `GraphEdge` | Create connection |
| POST | `/api/report` | `ReportOut` | Public tip submission |
| GET | `/api/reports` | `ReportOut[]` | List tips |
| POST | `/api/seed` | Seed counts | Populate test data |
| WS | `/ws/caseboard` | Real-time graph updates | ⚠️ Not fully tested |

### ❌ Endpoints Not Called by Frontend

| Method | Path | Purpose | Missing Feature |
|--------|------|---------|-----------------|
| GET | `/api/cases/{id}/graph` | Neo4j React Flow format | Frontend uses in-memory snapshot instead |
| POST | `/api/alerts/draft` | AI-generated alert draft | No Alerts Desk UI |
| POST | `/api/alerts/approve` | Publish alert | No Alerts Desk UI |
| GET | `/api/alerts` | List published alerts | No alerts feed page |
| WS | `/ws/alerts` | Real-time alert broadcasts | No WebSocket connection |

---

## Data Flow

### Tip Submission Flow
```
1. POST /api/report
   ↓
2. Create report in _reports
   ↓
3. Create case (if new) or add to existing
   ↓
4. Create GraphNode (type: REPORT)
   ↓
5. Emit event: node:report
   ↓
6. AI pipelines trigger (clustering, forensics, network, etc.)
   ↓
7. WebSocket broadcast: graph_update
```

### Evidence Addition Flow
```
1. POST /api/cases/{id}/evidence
   ↓
2. Save to Neo4j (optional, may fail gracefully)
   ↓
3. Create GraphNode in-memory
   ↓
4. Broadcast WebSocket: add_node
   ↓
5. Frontend receives update via wolftrace-provider
```

### Edge Creation Flow
```
1. POST /api/cases/{id}/edges
   ↓
2. Create link in Neo4j (optional)
   ↓
3. Create GraphEdge in-memory
   ↓
4. Broadcast WebSocket: add_edge
   ↓
5. Emit event: edge:created
   ↓
6. AI classifier triggers (semantic role assignment)
```

---

## Type Mappings (Backend → Frontend)

### Case Fields
```python
Backend (CaseOut)         → Frontend (Case)
------------------          ------------------
case_id / id              → id
label / case_id           → codename
status: "pending"         → status: "Investigating"
updated_at                → lastUpdated
node_count                → evidenceCount
summary                   → summary
story                     → storyText
location                  → location
```

### Evidence/Node Fields
```python
Backend (GraphNode)       → Frontend (Evidence)
-------------------         --------------------
id                        → id
node_type: "report"       → type: "text"
data.text_body            → title (first 50 chars)
data.media_url            → contentUrl
data.timestamp            → timestamp
data.reviewed             → reviewed
case_id                   → caseId
```

### Edge/Connection Fields
```python
Backend (GraphEdge)       → Frontend (EvidenceConnection)
-------------------         -------------------------------
source_id / source        → fromId
target_id / target        → toId
edge_type: "similar_to"   → relation: "related"
edge_type: "debunked_by"  → relation: "contradicts"
```

---

## Known Issues

### 1. Location Format Mismatch
- **Frontend sends:** `location: string` (building name only)
- **Backend expects:** `Location { building: string, lat?: number, lng?: number }`
- **Impact:** Lat/lng always undefined
- **Status:** Works but incomplete data

### 2. Internal Types Exposed in API
- **Issue:** `POST /api/cases/{id}/evidence` returns `GraphNode` (internal format)
- **Better:** Should return explicit DTO matching Evidence type
- **Status:** Works via `mapBackendEvidence()` but not ideal

### 3. Neo4j Graph Endpoint Unused
- **Issue:** `GET /api/cases/{id}/graph` exists but frontend uses in-memory snapshot
- **Benefit:** React Flow format pre-formatted for graph rendering
- **Status:** Consider switching frontend to use this

---

## Testing

### Run Backend
```bash
cd /Users/samarth/Desktop/Wolftrace/hackathon/backend
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Seed Test Data
```bash
curl -X POST http://localhost:8000/api/seed
# Response: {"status": "seeded", "cases": 10, "evidence": 27, "connections": 20, "tips": 4}
```

### Verify Cases
```bash
curl http://localhost:8000/api/cases | jq
# Should return 10 cases with full metadata
```

### Test WebSocket
```javascript
// Browser console
const ws = new WebSocket('ws://localhost:8000/ws/caseboard')
ws.onmessage = (e) => console.log(JSON.parse(e.data))
// Should receive: {type: "snapshots", payload: [...]}
```

---

## Next Steps

### Critical
1. **Verify real-time updates work end-to-end**
   - Add evidence via API while viewing case
   - Check if UI updates without refresh

2. **Test all seeded data appears in frontend**
   - All 10 cases in Case Wall
   - All 27 evidence items in case views

### High Priority
3. **Implement Alerts Desk backend workflow**
   - Endpoint already exists
   - Need frontend UI integration

4. **Add Walkie-Talkie Leads endpoint**
   - Not yet implemented
   - Should return recent case activity

### Medium Priority
5. **Standardize API response contracts**
   - Define explicit DTOs
   - Don't expose internal GraphNode/GraphEdge

6. **Consider Neo4j graph endpoint**
   - Evaluate if React Flow format is better for Evidence Network

---

## Files Changed

### Modified
- `app/graph_state.py` - Case metadata, enhanced snapshots
- `app/models/case.py` - Expanded CaseOut model
- `app/routers/cases.py` - Fixed evidence/edge responses
- `app/main.py` - Registered seed router

### New
- `app/seed_data.py` - Mock data translation
- `app/routers/seed.py` - Seed endpoint

### Key Unchanged (for reference)
- `app/routers/reports.py` - Report submission
- `app/routers/ws.py` - WebSocket handlers
- `app/routers/alerts.py` - Alert drafting (unused by frontend)
- `app/services/graph_db.py` - Neo4j connection
- `app/pipelines/` - AI processing pipelines
