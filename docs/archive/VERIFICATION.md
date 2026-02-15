# Shadow Bureau: Verification Guide

Complete testing instructions to verify the backend works after cleanup.

---

## 🚀 Step 1: Start the Server

```bash
cd /home/harsha/Documents/hackathon/shadow-bureau-backend

# Install dependencies (if not already done)
uv sync

# Start the server
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Expected Output:**
```
INFO:     Shadow Bureau backend started (blackboard: 7 sources)
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

**✅ Verification:** You should see:
- `blackboard: 7 sources` (all knowledge sources registered)
- No import errors
- Server running on port 8000

---

## 🏥 Step 2: Health Check

### Browser Test:
Open: **http://localhost:8000/health**

**Expected Response:**
```json
{
  "status": "ok",
  "knowledge_sources": 7,
  "controller_running": true
}
```

### curl Test:
```bash
curl http://localhost:8000/health | jq
```

**✅ Pass Criteria:**
- `status: "ok"`
- `knowledge_sources: 7` (clustering, forensics, network, forensics_xref, classifier, recluster_debunk, case_synthesizer)
- `controller_running: true`

---

## 📚 Step 3: Interactive API Documentation

FastAPI provides automatic interactive docs:

### **Swagger UI (Recommended)**
Open: **http://localhost:8000/docs**

### **ReDoc (Alternative)**
Open: **http://localhost:8000/redoc**

---

## 🧪 Step 4: Test Each Endpoint via Swagger UI

### 4.1 **Test Report Submission** (Core Flow)

1. Go to `http://localhost:8000/docs`
2. Find **POST /api/report** endpoint
3. Click "Try it out"
4. Use this test payload:

```json
{
  "text_body": "Suspicious person seen near Hunt Library at 2pm wearing a black hoodie. Taking photos of building entrances.",
  "location": {
    "lat": 35.7847,
    "lng": -78.6821,
    "building": "Hunt Library"
  },
  "timestamp": "2026-02-14T14:00:00",
  "media_url": "https://images.unsplash.com/photo-1517849845537-4d257902454a",
  "anonymous": true,
  "contact": null
}
```

5. Click **Execute**

**✅ Expected Response (201):**
```json
{
  "case_id": "CASE-MIDNIGHT-CIPHER-7203",
  "report_id": "R1234567890",
  "text_body": "Suspicious person seen near Hunt Library...",
  "location": {
    "lat": 35.7847,
    "lng": -78.6821,
    "building": "Hunt Library"
  },
  "timestamp": "2026-02-14T14:00:00",
  "media_url": "https://images.unsplash.com/photo-1517849845537-4d257902454a",
  "anonymous": true,
  "status": "pending"
}
```

**✅ What Should Happen:**
- Report created with noir-themed `case_id` (e.g., CASE-MIDNIGHT-CIPHER-7203)
- Blackboard controller triggers pipelines:
  - **Network pipeline:** Extracts claims (if Backboard/Gemini API key set)
  - **Forensics pipeline:** Analyzes image (if media_url accessible)
  - **Clustering pipeline:** Looks for similar reports
- WebSocket broadcast to all connected clients

---

### 4.2 **Test List Reports**

1. Find **GET /api/reports**
2. Click "Try it out" → "Execute"

**✅ Expected:** Array with your submitted report(s)

---

### 4.3 **Test List Cases**

1. Find **GET /api/cases**
2. Click "Try it out" → "Execute"

**✅ Expected Response:**
```json
[
  {
    "case_id": "CASE-MIDNIGHT-CIPHER-7203",
    "report_count": 1,
    "node_count": 3,
    "edge_count": 2,
    "label": "CASE-MIDNIGHT-CIPHER-7203",
    "status": "active"
  }
]
```

---

### 4.4 **Test Case Snapshot (In-Memory Graph)**

1. Find **GET /api/cases/{case_id}**
2. Click "Try it out"
3. Enter your `case_id` from Step 4.1
4. Execute

**✅ Expected:** Full graph snapshot with nodes and edges:
```json
{
  "case_id": "CASE-MIDNIGHT-CIPHER-7203",
  "nodes": [
    {
      "id": "R1234567890",
      "node_type": "report",
      "case_id": "CASE-MIDNIGHT-CIPHER-7203",
      "data": {
        "text_body": "...",
        "claims": [...],
        "urgency": 0.7
      }
    },
    {
      "id": "FC123",
      "node_type": "fact_check",
      "data": { ... }
    }
  ],
  "edges": [
    {
      "id": "E123",
      "edge_type": "debunked_by",
      "source_id": "R1234567890",
      "target_id": "FC123"
    }
  ]
}
```

---

### 4.5 **Test Neo4j Case Creation** (Optional - requires Neo4j)

**Prerequisites:** Neo4j credentials in `.env`

1. Find **POST /api/cases**
2. Click "Try it out"
3. Payload:
```json
{
  "case_id": "CASE-TEST-NEO4J-001",
  "title": "Test Case",
  "description": "Testing Neo4j integration"
}
```
4. Execute

**✅ Expected (200):** Case created in Neo4j

---

### 4.6 **Test Evidence Upload** (Optional - requires Neo4j)

1. Create a case first (Step 4.5)
2. Find **POST /api/cases/{case_id}/evidence**
3. Use the `case_id` from previous step
4. Payload:
```json
{
  "id": "EVIDENCE-001",
  "type": "photo",
  "content": "Photo of suspicious activity",
  "url": "https://example.com/photo.jpg",
  "timestamp": "2026-02-14T14:00:00"
}
```

**✅ Expected:** Evidence node created and linked to case via CONTAINS edge

---

### 4.7 **Test Red String Link** (Optional - requires Neo4j)

1. Create a case + 2 evidence items
2. Find **POST /api/cases/{case_id}/edges**
3. Payload:
```json
{
  "source_id": "EVIDENCE-001",
  "target_id": "EVIDENCE-002",
  "type": "SUSPECTED_LINK",
  "note": "Both photos taken at same location"
}
```

**✅ Expected:** RELATED edge created, `edge:created` event emitted

---

### 4.8 **Test Alert Draft**

1. Find **POST /api/alerts/draft**
2. Payload (use your case_id):
```json
{
  "case_id": "CASE-MIDNIGHT-CIPHER-7203",
  "officer_notes": "Multiple reports, high credibility"
}
```

**✅ Expected Response:**
```json
{
  "case_id": "CASE-MIDNIGHT-CIPHER-7203",
  "draft_text": "CAMPUS ALERT: Investigating suspicious activity near Hunt Library...",
  "status": "draft",
  "location_summary": "Hunt Library"
}
```

---

### 4.9 **Test Alert Approval**

1. Find **POST /api/alerts/approve**
2. Payload:
```json
{
  "case_id": "CASE-MIDNIGHT-CIPHER-7203",
  "final_text": "CAMPUS ALERT: Suspicious activity reported near Hunt Library at 2pm. No immediate threat. Campus police investigating. Report any information to 919-555-0100.",
  "status": "published"
}
```

**✅ Expected:**
- Alert published
- WebSocket broadcast to all `/ws/alerts` clients
- TTS audio generated (if ElevenLabs configured)

---

### 4.10 **Test Public Alert Feed**

1. Find **GET /api/alerts**
2. Execute

**✅ Expected:** Array of published alerts

---

## 🔌 Step 5: Test WebSockets

### Using Browser Console

#### 5.1 **Test Caseboard WebSocket**

Open browser console on any page and run:

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/caseboard');

ws.onopen = () => console.log('✅ Connected to caseboard');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('📨 Message:', data);
};

ws.onerror = (error) => console.error('❌ Error:', error);
```

**✅ Expected:**
1. Initial message: `{ type: "snapshots", payload: [...] }` (all case snapshots)
2. Real-time updates when you submit reports: `{ type: "graph_update", action: "add_node", ... }`

#### 5.2 **Test Alerts WebSocket**

```javascript
const alertWs = new WebSocket('ws://localhost:8000/ws/alerts');

alertWs.onopen = () => console.log('✅ Connected to alerts');

alertWs.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('🚨 Alert:', data);
};
```

**✅ Expected:** New alert messages when you approve alerts

---

### Using websocat (CLI Tool)

```bash
# Install websocat
cargo install websocat
# or: brew install websocat

# Connect to caseboard
websocat ws://localhost:8000/ws/caseboard

# Connect to alerts
websocat ws://localhost:8000/ws/alerts
```

---

## 🧠 Step 6: Verify Blackboard Controller

### Check Console Logs

After submitting a report, watch the server console for:

```
INFO: Knowledge source clustering started for CASE-...
INFO: Knowledge source network started for CASE-...
INFO: Knowledge source forensics started for CASE-...
```

**✅ Expected Flow:**
1. Report submitted → node added
2. **CRITICAL priority:** `clustering` runs first
3. **HIGH priority:** `forensics` (if media_url)
4. **MEDIUM priority:** `network` extracts claims
5. **MEDIUM priority:** `forensics_xref` (after claims added)
6. **LOW priority:** `classifier` assigns semantic roles
7. **BACKGROUND priority:** `case_synthesizer` (if Backboard configured)

---

## 🔬 Step 7: Advanced Testing Scenarios

### 7.1 **Test Claim Extraction** (requires API keys)

Set in `.env`:
```
GEMINI_API_KEY=your_key_here
# OR
BACKBOARD_API_KEY=your_key_here
```

Submit a report with claims:
```json
{
  "text_body": "Fire alarm went off in EB2 at 3pm. Everyone evacuated safely. Building is now closed.",
  "location": { "lat": 35.7721, "lng": -78.6737, "building": "EB2" },
  "anonymous": true
}
```

**✅ Check:** Report node should have `claims`, `urgency`, `misinformation_flags` in data

---

### 7.2 **Test Forensics Pipeline** (requires accessible image URL)

Submit report with valid image URL:
```json
{
  "text_body": "Photo of graffiti on Talley Student Union wall",
  "media_url": "https://images.unsplash.com/photo-1579783902614-a3fb3927b6a5",
  "anonymous": true
}
```

**✅ Check:**
- `MediaVariant` node created
- pHash, EXIF data extracted
- Edge created: report → media_variant

---

### 7.3 **Test Clustering** (submit multiple similar reports)

Submit 2 reports with similar time/location:

**Report 1:**
```json
{
  "text_body": "Loud noise near DH Hill Library",
  "location": { "lat": 35.7868, "lng": -78.6704, "building": "DH Hill" },
  "timestamp": "2026-02-14T15:00:00",
  "anonymous": true
}
```

**Report 2:**
```json
{
  "text_body": "Explosion sound heard near library",
  "location": { "lat": 35.7865, "lng": -78.6701, "building": "DH Hill" },
  "timestamp": "2026-02-14T15:02:00",
  "anonymous": true
}
```

**✅ Check:** `SIMILAR_TO` edge created between the two reports

---

## ✅ Final Verification Checklist

- [ ] Server starts without errors
- [ ] Health endpoint returns `knowledge_sources: 7`
- [ ] Blackboard controller is `running: true`
- [ ] Can submit reports via `/api/report`
- [ ] Report creates noir-themed case_id
- [ ] Can list reports via `/api/reports`
- [ ] Can list cases via `/api/cases`
- [ ] Can get case snapshot via `/api/cases/{id}`
- [ ] Can draft alert via `/api/alerts/draft`
- [ ] Can approve alert via `/api/alerts/approve`
- [ ] Can view alerts via `/api/alerts`
- [ ] WebSocket `/ws/caseboard` connects and receives snapshots
- [ ] WebSocket `/ws/alerts` connects
- [ ] Pipelines run in order (check console logs)
- [ ] No auth errors (all routes public)
- [ ] No import errors

---

## 🐛 Troubleshooting

### Server won't start
```bash
# Check Python version
python3 --version  # Should be 3.11+

# Reinstall dependencies
uv sync --reinstall
```

### Import errors
```bash
# Verify syntax
python3 -m py_compile app/main.py app/pipelines/orchestrator.py
```

### API keys missing (optional)
- Server runs fine WITHOUT API keys (graceful fallbacks)
- Claims extraction uses mock data if no Gemini/Backboard
- Fact checking returns empty if no FACTCHECK_API_KEY
- TTS skipped if no ELEVENLABS_API_KEY

### Neo4j errors (optional)
- Neo4j is OPTIONAL - in-memory graph works without it
- Only needed for `/api/cases/{id}/graph`, evidence, Red String

---

## 🎯 Success Criteria

✅ **Minimal Success:**
- Server starts
- Health check passes
- Can submit report
- Can list reports/cases
- WebSockets connect

✅ **Full Success:**
- All above PLUS:
- Pipelines run (check console logs)
- Claims extracted (with API keys)
- Alerts draft/approve work
- WebSockets receive real-time updates

---

## 📊 Performance Expectations

| Operation | Expected Time |
|-----------|---------------|
| Server startup | 2-5 seconds |
| Report submission | < 500ms |
| Pipeline execution | 1-3 seconds total |
| Claim extraction (with AI) | 2-5 seconds |
| WebSocket message | < 100ms |
| Case snapshot | < 200ms |

---

## 🚀 Next Steps After Verification

Once everything passes:

1. **Connect Frontend:** Update frontend to point to `http://localhost:8000`
2. **Add API Keys:** For full AI features (Gemini/Backboard)
3. **Configure Neo4j:** For persistent graph storage (optional)
4. **Test WebSocket UI:** Build real-time dashboard

---

**Need Help?**
- Check server console for detailed error logs
- Verify `.env` file exists (copy from `.env.example`)
- Ensure port 8000 is available: `lsof -i :8000`
