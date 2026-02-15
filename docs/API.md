# Shadow Bureau API Reference

Complete API documentation for all endpoints.

**Base URL:** `http://localhost:8000`
**Interactive Docs:** http://localhost:8000/docs

---

## Public Endpoints

### Reports

#### Submit Report
```http
POST /api/report
Content-Type: application/json
```

**Request:**
```json
{
  "text_body": "Fire alarm went off in Hunt Library...",
  "location": {
    "lat": 35.7847,
    "lng": -78.6821,
    "building": "Hunt Library"
  },
  "timestamp": "2026-02-14T14:00:00",
  "media_url": "https://example.com/photo.jpg",
  "anonymous": true,
  "contact": null
}
```

**Response (201):**
```json
{
  "case_id": "CASE-MIDNIGHT-CIPHER-7203",
  "report_id": "RPT-AE9F48C92515",
  "text_body": "...",
  "location": {...},
  "timestamp": "2026-02-14T14:00:00",
  "media_url": "...",
  "anonymous": true,
  "status": "pending"
}
```

#### List Reports
```http
GET /api/reports
```

**Response (200):**
```json
[
  {
    "case_id": "CASE-...",
    "report_id": "RPT-...",
    "text_body": "...",
    "status": "processing"
  }
]
```

---

### Cases

#### List Cases
```http
GET /api/cases
```

**Response (200):**
```json
[
  {
    "case_id": "CASE-...",
    "report_count": 1,
    "node_count": 4,
    "edge_count": 3,
    "label": "CASE-...",
    "status": "active"
  }
]
```

#### Get Case Snapshot (In-Memory)
```http
GET /api/cases/{case_id}
```

**Response (200):**
```json
{
  "case_id": "CASE-...",
  "nodes": [
    {
      "id": "RPT-...",
      "node_type": "report",
      "data": {
        "text_body": "...",
        "claims": [...],
        "urgency": 0.7
      }
    }
  ],
  "edges": [
    {
      "id": "E-...",
      "edge_type": "similar_to",
      "source_id": "...",
      "target_id": "..."
    }
  ]
}
```

---

### Neo4j Case Management (Optional)

#### Create Case in Neo4j
```http
POST /api/cases
Content-Type: application/json
```

**Request:**
```json
{
  "case_id": "CASE-...",
  "title": "Hunt Library Incident",
  "description": "Fire alarm investigation"
}
```

**Response (200):**
```json
{
  "id": "CASE-...",
  "title": "...",
  "description": "...",
  "created_at": "2026-02-14T..."
}
```

#### Get Case Graph from Neo4j
```http
GET /api/cases/{case_id}/graph
```

**Response (200):** React Flow format
```json
{
  "case_id": "CASE-...",
  "nodes": [
    {
      "id": "EVIDENCE-001",
      "position": {"x": 250, "y": 250},
      "data": {"label": "EVIDENCE-001", "type": "photo"}
    }
  ],
  "edges": [
    {
      "id": "e-...",
      "source": "EVIDENCE-001",
      "target": "EVIDENCE-002",
      "type": "RELATED"
    }
  ]
}
```

#### Add Evidence
```http
POST /api/cases/{case_id}/evidence
Content-Type: application/json
```

**Request:**
```json
{
  "id": "EVIDENCE-001",
  "type": "photo",
  "content": "Photo of graffiti",
  "url": "https://example.com/photo.jpg",
  "timestamp": "2026-02-14T14:00:00"
}
```

**Response (200):**
```json
{
  "id": "EVIDENCE-001",
  "type": "photo",
  "content": "...",
  "url": "...",
  "timestamp": "..."
}
```

#### Create Red String Link
```http
POST /api/cases/{case_id}/edges
Content-Type: application/json
```

**Request:**
```json
{
  "source_id": "EVIDENCE-001",
  "target_id": "EVIDENCE-002",
  "type": "SUSPECTED_LINK",
  "note": "Both photos taken at same time"
}
```

**Response (200):**
```json
{
  "source_id": "EVIDENCE-001",
  "target_id": "EVIDENCE-002",
  "type": "SUSPECTED_LINK",
  "note": "...",
  "created_at": "..."
}
```

**Events:** Emits `edge:created` event for AI analysis

---

### Alerts

#### Draft Alert
```http
POST /api/alerts/draft
Content-Type: application/json
```

**Request:**
```json
{
  "case_id": "CASE-...",
  "officer_notes": "Multiple reports, high credibility"
}
```

**Response (200):**
```json
{
  "case_id": "CASE-...",
  "draft_text": "CAMPUS ALERT: ...",
  "status": "draft",
  "location_summary": "Hunt Library"
}
```

#### Approve Alert
```http
POST /api/alerts/approve
Content-Type: application/json
```

**Request:**
```json
{
  "case_id": "CASE-...",
  "final_text": "CAMPUS ALERT: Fire alarm resolved...",
  "status": "Confirmed"
}
```

**Valid Status Values:** `"Confirmed"`, `"Investigating"`, `"All Clear"`

**Response (200):**
```json
{
  "id": "ALT-...",
  "case_id": "CASE-...",
  "text": "...",
  "status": "Confirmed",
  "audio_url": null,
  "created_at": "..."
}
```

**Events:** Broadcasts to `/ws/alerts` WebSocket

#### List Alerts
```http
GET /api/alerts
```

**Response (200):**
```json
[
  {
    "id": "ALT-...",
    "case_id": "CASE-...",
    "text": "...",
    "status": "Confirmed",
    "created_at": "..."
  }
]
```

---

## WebSocket Endpoints

### Caseboard Updates
```
ws://localhost:8000/ws/caseboard
```

**On Connect:** Receives all case snapshots
```json
{
  "type": "snapshots",
  "payload": [...]
}
```

**Real-Time Updates:**
```json
{
  "type": "graph_update",
  "action": "add_node" | "add_edge" | "update_node",
  "payload": {...},
  "timestamp": "2026-02-14T..."
}
```

### Alert Stream
```
ws://localhost:8000/ws/alerts
```

**On Alert Approval:**
```json
{
  "type": "new_alert",
  "alert": {
    "id": "ALT-...",
    "case_id": "CASE-...",
    "text": "...",
    "status": "Confirmed"
  }
}
```

---

## System Endpoints

### Health Check
```http
GET /health
```

**Response (200):**
```json
{
  "status": "ok",
  "knowledge_sources": 7,
  "controller_running": true
}
```

---

## Error Responses

All errors follow this format:

```json
{
  "detail": "Error message" | [{...}]
}
```

**Common Status Codes:**
- `200` - Success
- `201` - Created
- `400` - Bad Request (validation error)
- `404` - Not Found
- `422` - Unprocessable Entity (invalid data)
- `500` - Internal Server Error

---

## Rate Limiting

**Current:** No rate limiting (hackathon build)

**Future:** Recommended for production

---

## Authentication

**Current:** None - all routes are public

**Note:** Auth was removed for hackathon simplicity

---

## CORS

**Allowed Origins:**
- `http://localhost:3000`
- `http://localhost:5173`

Configure via `CORS_ORIGINS` environment variable.
