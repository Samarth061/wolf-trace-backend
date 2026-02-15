# WolfTrace Frontend ↔ Shadow Bureau Backend Integration Guide

This guide explains how to run and test the integrated system.

---

## 📋 Overview

**Backend:** Shadow Bureau (FastAPI + Neo4j + Backboard AI)
**Frontend:** WolfTrace UI (Next.js + React + TypeScript)
**Connection:** REST API + WebSocket for real-time updates

---

## 🚀 Quick Start

### 1. Start the Backend

```bash
cd shadow-bureau-backend

# Ensure environment is configured
cp .env.example .env
# Edit .env to add API keys (optional - graceful fallbacks)

# Install dependencies (if needed)
uv sync

# Start server
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

# Verify backend is running
curl http://localhost:8000/health
```

**Expected output:**
```json
{
  "status": "ok",
  "knowledge_sources": 7,
  "controller_running": true
}
```

---

### 2. Start the Frontend

```bash
cd ../WolfTrace-ui

# Install dependencies (first time only)
pnpm install
# or: npm install

# Create environment file
cp .env.local.example .env.local

# Edit .env.local to enable backend:
# NEXT_PUBLIC_USE_BACKEND=true
# NEXT_PUBLIC_API_URL=http://localhost:8000

# Start frontend
pnpm dev
# or: npm run dev
```

**Frontend should start at:** http://localhost:3000

---

## 🔧 Configuration

### Backend (.env)

```bash
# Required for full functionality (but all gracefully degrade)
BACKBOARD_API_KEY=your_backboard_key
GEMINI_API_KEY=your_gemini_key

# Optional: Neo4j for persistent evidence board
NEO4J_URI=neo4j+s://your-instance.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your-password

# CORS (already configured for Next.js)
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

### Frontend (.env.local)

```bash
# Enable backend integration
NEXT_PUBLIC_USE_BACKEND=true

# Backend API URL
NEXT_PUBLIC_API_URL=http://localhost:8000
```

**Toggle backend:** Set `NEXT_PUBLIC_USE_BACKEND=false` to use mock data

---

## 🧪 Testing the Integration

### Test 1: Submit a Public Tip

1. **Open frontend:** http://localhost:3000
2. **Double-click streetlamp** to trigger bureau door puzzle
3. **Solve puzzle** (click pattern) and enter as Detective
4. **Submit a tip** from the landing page (before logging in, or use the form)

**Expected flow:**
- Frontend calls `POST /api/report` on backend
- Backend creates case with noir codename (e.g., `CASE-MIDNIGHT-CIPHER-7203`)
- Backend runs pipelines (clustering, claim extraction, network search)
- Frontend receives case via WebSocket update
- Case appears on Case Wall (corkboard view)

**Verify:**
```bash
# Check backend logs
# Should see:
# INFO: Knowledge source clustering started for CASE-...
# INFO: Knowledge source network started for CASE-...

# Check case was created
curl http://localhost:8000/api/cases | jq
```

---

### Test 2: View Evidence Board

1. **Click on a case** from the Case Wall
2. **View Evidence Network** tab

**Expected:**
- See nodes (reports + external sources) in force-directed graph
- See edges connecting related evidence
- Nodes should be draggable
- Evidence details panel on right

**Data flow:**
- Frontend calls `GET /api/cases/{case_id}`
- Backend returns graph snapshot with nodes/edges
- Frontend renders in force-directed canvas

**Verify:**
```bash
# Get specific case
curl http://localhost:8000/api/cases/CASE-YOUR-ID | jq '.nodes | length'
# Should return number of nodes created by pipelines
```

---

### Test 3: Real-Time Updates

**Setup:**
1. Open **two browser tabs** with the Case Wall
2. In terminal, submit a report via API

**Submit report:**
```bash
curl -X POST http://localhost:8000/api/report \
  -H "Content-Type: application/json" \
  -d '{
    "text_body": "Test real-time update: Strange lights at Talley Student Union",
    "location": {"lat": 35.7847, "lng": -78.6821, "building": "Talley"},
    "timestamp": "2026-02-14T20:00:00",
    "anonymous": true
  }'
```

**Expected:**
- **Both browser tabs** automatically show new case (via WebSocket)
- No manual refresh needed
- Case appears within 1-2 seconds

**Check WebSocket:**
- Open browser DevTools → Network → WS
- Should see WebSocket connection to `ws://localhost:8000/ws/caseboard`
- Messages like `{"type": "graph_update", "action": "add_node", ...}`

---

### Test 4: Add Evidence (Neo4j Required)

**Prerequisites:** Neo4j configured in backend `.env`

1. **Create a case in Neo4j:**
```bash
curl -X POST http://localhost:8000/api/cases \
  -H "Content-Type: application/json" \
  -d '{
    "case_id": "CASE-TEST-001",
    "title": "Test Evidence Board",
    "description": "Testing manual evidence workflow"
  }'
```

2. **Add evidence from frontend:**
   - Click case in Case Wall
   - Click "Add Evidence" button
   - Fill in title, type, key points
   - Submit

3. **Create red string connection:**
   - Add another piece of evidence
   - Drag from one evidence node to another
   - Select relationship type

**Expected:**
- Evidence nodes appear in graph
- Backend stores in Neo4j
- Red string edges connect evidence
- AI analyzes the connection (check backend logs)

**Verify:**
```bash
# Get Neo4j graph
curl http://localhost:8000/api/cases/CASE-TEST-001/graph | jq
```

---

## 🔍 Type Mappings

### Backend → Frontend

| Backend Type | Frontend Type | Mapping |
|--------------|---------------|---------|
| `case_id` | `id` | Direct |
| `label` / `case_id` | `codename` | Use label or fallback to case_id |
| `status: "pending"` | `status: "Investigating"` | Via status map |
| `node (report)` | `Evidence (type: text)` | Via mapBackendEvidence |
| `edge (similar_to)` | `EvidenceConnection (relation: related)` | Via mapBackendEdge |

### Key Differences

**Backend:**
- Uses `case_id`, `report_id` with noir naming
- Nodes have `node_type` ("report", "external_source")
- Edges have `edge_type` ("similar_to", "contains")

**Frontend:**
- Uses `id`, `codename` for display
- Evidence has `type` ("text", "image", "video")
- Connections have `relation` ("supports", "contradicts", "related")

---

## 🐛 Troubleshooting

### Backend won't start

```bash
# Check Python version
python3 --version  # Need 3.11+

# Reinstall dependencies
cd shadow-bureau-backend
uv sync --reinstall
```

### Frontend can't connect

**Check CORS:**
```bash
# Backend should log CORS origins on startup
# If not, update .env:
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

**Check API URL:**
```bash
# Frontend .env.local must match backend
NEXT_PUBLIC_API_URL=http://localhost:8000
```

**Test manually:**
```bash
curl http://localhost:8000/health
# Should return JSON, not error
```

### WebSocket not connecting

**Check browser console:**
- DevTools → Console
- Look for WebSocket errors
- Should see: "✅ WebSocket connected: ws://localhost:8000/ws/caseboard"

**Common issues:**
- Backend not running on port 8000
- CORS blocking WebSocket (check backend logs)
- Firewall blocking WebSocket protocol

**Test WebSocket manually:**
```bash
# Install websocat: cargo install websocat
websocat ws://localhost:8000/ws/caseboard

# Should receive initial snapshots message
```

### No data showing up

**Backend using mock data:**
- Set `NEXT_PUBLIC_USE_BACKEND=false` in frontend
- Frontend will use mock data (27 evidence items, 10 cases)

**Backend has no cases:**
```bash
# Submit a test report
curl -X POST http://localhost:8000/api/report \
  -H "Content-Type: application/json" \
  -d '{"text_body": "Test report", "anonymous": true}'
```

### TypeScript errors in frontend

```bash
cd WolfTrace-ui

# Install dependencies
pnpm install

# Restart dev server
pnpm dev
```

---

## 📊 Data Flow Diagram

```
PUBLIC TIP SUBMISSION:
┌─────────────┐
│  Frontend   │
│  Tip Form   │
└──────┬──────┘
       │ POST /api/report
       ▼
┌─────────────────────┐
│  Backend            │
│  POST /api/report   │
└──────┬──────────────┘
       │ Creates case, emits ReportReceived
       ▼
┌─────────────────────┐
│  Pipelines          │
│  - Clustering       │
│  - Network Search   │
│  - Claim Extract    │
└──────┬──────────────┘
       │ Emits graph_update events
       ▼
┌─────────────────────┐
│  WebSocket          │
│  /ws/caseboard      │
└──────┬──────────────┘
       │ Broadcasts to all clients
       ▼
┌─────────────────────┐
│  Frontend           │
│  Case Wall Updates  │
└─────────────────────┘
```

```
EVIDENCE BOARD INTERACTION:
┌─────────────┐
│  Frontend   │
│  Click Case │
└──────┬──────┘
       │ GET /api/cases/{id}
       ▼
┌─────────────────────┐
│  Backend            │
│  Returns snapshot   │
│  {nodes, edges}     │
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│  Frontend           │
│  Force-Directed     │
│  Graph Render       │
└─────────────────────┘

ADD EVIDENCE:
┌─────────────┐
│  Frontend   │
│  Add Button │
└──────┬──────┘
       │ POST /api/cases/{id}/evidence
       ▼
┌─────────────────────┐
│  Backend Neo4j      │
│  Creates node       │
│  Emits edge:created │
└──────┬──────────────┘
       │ AI analyzes
       ▼
┌─────────────────────┐
│  WebSocket Update   │
└─────────────────────┘
```

---

## ✅ Integration Checklist

- [ ] Backend running on port 8000
- [ ] Backend health check returns `"status": "ok"`
- [ ] Frontend running on port 3000
- [ ] Frontend `.env.local` has `NEXT_PUBLIC_USE_BACKEND=true`
- [ ] WebSocket connection established (check browser DevTools)
- [ ] Can submit tip from landing page
- [ ] Case appears on Case Wall
- [ ] Can view evidence in Evidence Board
- [ ] Real-time updates working (test with curl)
- [ ] (Optional) Neo4j connected for manual evidence

---

## 🎯 Next Steps

### Phase 1: Core Features ✅
- [x] API client integration
- [x] WebSocket real-time updates
- [x] Case/evidence mapping
- [x] Tip submission flow

### Phase 2: Enhanced UX
- [ ] Loading states during API calls
- [ ] Error handling with toast notifications
- [ ] Optimistic updates (update UI before backend confirms)
- [ ] Retry logic for failed requests

### Phase 3: Advanced Features
- [ ] Forensics Lab integration (image/video analysis)
- [ ] Alert drafting/publishing UI
- [ ] Walkie-talkie Leads panel
- [ ] Full Witness Inbox workflow

### Phase 4: Production Ready
- [ ] Authentication (JWT/sessions)
- [ ] File upload for evidence media
- [ ] Environment-specific configs (dev/staging/prod)
- [ ] Error boundary components

---

## 📚 Key Files

### Backend
- `app/main.py` - FastAPI app with CORS
- `app/routers/reports.py` - POST /api/report endpoint
- `app/routers/cases.py` - Case/evidence endpoints
- `app/routers/ws.py` - WebSocket handlers
- `app/graph_state.py` - In-memory graph storage

### Frontend
- `lib/api-client.ts` - API integration layer ⭐ (NEW)
- `components/wolftrace-provider.tsx` - State + API calls ⭐ (UPDATED)
- `components/bureau/add-evidence-modal.tsx` - Evidence submission
- `components/bureau/evidence-network.tsx` - Graph visualization
- `app/bureau/case/[id]/page.tsx` - Case detail view

---

**Integration Status:** ✅ Complete and ready to test

**Run both systems and visit:** http://localhost:3000
