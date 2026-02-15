# WolfTrace / Shadow Bureau - Hackathon Project

## Project Overview

WolfTrace is a noir-themed campus safety intelligence platform for detecting and triaging misinformation, rumors, and safety incidents. It combines an AI-powered backend (Shadow Bureau) with a detective-themed React frontend (WolfTrace UI).

**Core idea:** Public tips come in -> AI pipelines extract claims, fact-check, cluster duplicates, analyze media forensics -> Officers view an evidence board with force-directed graph, manage cases, and publish verified alerts.

## Architecture

### Backend: `shadow-bureau-backend/` (Python, FastAPI)
- **Framework:** FastAPI with uvicorn, Python 3.11+
- **Package manager:** uv (`uv sync`, `uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`)
- **Config:** Pydantic Settings from `.env` file (`app/config.py`)
- **In-memory graph:** `app/graph_state.py` — nodes, edges, reports stored in dicts (not persisted across restarts)
- **Neo4j AuraDB:** Optional persistent graph DB for evidence/cases (`app/services/graph_db.py`, `app/services/graph_queries.py`)
- **Event bus:** Async queue-based pub/sub (`app/event_bus.py`) for decoupled pipeline triggering
- **WebSocket:** Real-time updates via `/ws/caseboard` and `/ws/alerts` (`app/routers/ws.py`)

### Frontend: `WolfTrace-ui/` (Next.js 16, React 19, TypeScript)
- **Framework:** Next.js 16 with Turbopack (`next dev --turbo`)
- **Package manager:** pnpm
- **UI library:** shadcn/ui components (Radix primitives + Tailwind CSS)
- **State:** React Context via `WolfTraceProvider` (`components/wolftrace-provider.tsx`)
- **API client:** `lib/api-client.ts` — REST + WebSocket client for backend
- **Feature flag:** `NEXT_PUBLIC_USE_BACKEND=true|false` toggles between live backend and mock data
- **Fonts:** Crimson Pro (serif headings), JetBrains Mono (monospace)
- **Theme:** Dark noir aesthetic with amber/gold accent (#A17120, #764608)

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check, returns knowledge source count |
| POST | `/api/report` | Public tip submission (creates case + triggers pipelines) |
| GET | `/api/reports` | List all reports |
| POST | `/api/seed` | Seed database with mock data (11 cases, 30 evidence, 23 connections) ✅ NEW |
| GET | `/api/cases` | List all cases (in-memory) |
| POST | `/api/cases` | Create case in Neo4j |
| GET | `/api/cases/{id}` | Full graph snapshot for case |
| GET | `/api/cases/{id}/graph` | Neo4j graph in React Flow format |
| POST | `/api/cases/{id}/evidence` | Add evidence to Neo4j case |
| DELETE | `/api/cases/{id}/evidence/{evidence_id}` | Delete evidence with cascade ✅ NEW |
| PATCH | `/api/cases/{id}/evidence/{evidence_id}` | Mark evidence as reviewed (sets confidence=1.0) ✅ ENHANCED |
| GET | `/api/cases/{id}/evidence/{evidence_id}/inference` | Get AI inference with summary ✅ ENHANCED |
| POST | `/api/cases/{id}/evidence/{evidence_id}/forensics` | Trigger forensic analysis (image/video) ✅ NEW |
| GET | `/api/cases/{id}/evidence/{evidence_id}/forensics` | Get forensic results ✅ NEW |
| GET | `/api/cases/{id}/story` | Generate AI narrative for case ✅ NEW |
| POST | `/api/cases/{id}/chat` | Chat with AI about evidence ✅ NEW |
| POST | `/api/cases/{id}/edges` | Create red string link between nodes |
| POST | `/api/upload` | Upload media file (image/video/audio), returns file URL ✅ |
| DELETE | `/api/upload/{filename}` | Delete uploaded file ✅ |
| POST | `/api/alerts/draft` | AI-generated alert draft from case context |
| POST | `/api/alerts/approve` | Publish alert + optional TTS audio |
| GET | `/api/alerts` | List published alerts |
| WS | `/ws/caseboard` | Real-time graph updates |
| WS | `/ws/alerts` | Real-time alert broadcasts |

## AI Pipeline (Blackboard Architecture)

The backend uses a **Blackboard Controller** pattern (`app/pipelines/blackboard_controller.py`) that schedules knowledge sources by priority with cooldowns and dedup:

| Priority | Pipeline | Trigger | What it does |
|----------|----------|---------|-------------|
| CRITICAL | `clustering` | node:report, edge:repost_of | Temporal (30min), geo (200m), semantic dedup. Creates SIMILAR_TO edges |
| HIGH | `forensics` | node:report (with media) | ELA heatmap, pHash, EXIF extraction, TwelveLabs video analysis |
| HIGH | `recluster_debunk` | edge:debunked_by | Updates report nodes with debunk counts |
| MEDIUM | `network` | node:report | Claim extraction (Backboard/Gemini), Fact Check API, search query generation |
| LOW | `classifier` | edge:similar_to, etc. | Assigns semantic roles: Originator, Amplifier, Mutator, Unwitting Sharer |
| BACKGROUND | `case_synthesizer` | update:report (with claims) | Full case narrative via Backboard Case Synthesizer agent |

## External Services (all gracefully degrade if unconfigured)

- **Backboard.io** (`app/services/backboard_client.py`): 4 AI agents with persistent case threads — Claim Analyst, Fact Checker, Alert Composer, Case Synthesizer
- **Google Gemini** (`app/services/gemini.py`): Fallback for claim extraction, alert composition, search query generation (model: gemini-2.0-flash)
- **Google Fact Check Tools API** (`app/services/factcheck.py`): Claim verification
- **TwelveLabs** (`app/services/twelvelabs.py`): Video indexing (Marengo), search, summarization (Pegasus)
- **ElevenLabs** (`app/services/elevenlabs.py`): Text-to-speech for audio alerts
- **Neo4j AuraDB** (`app/services/graph_db.py`): Persistent evidence graph

## Graph Data Model

### Node Types (`app/models/graph.py`)
- `report` — Raw tip/report from public
- `external_source` — Search results, external content
- `fact_check` — Fact check results
- `media_variant` — Image/video forensic analysis

### Edge Types
- `similar_to` — Clustering match (with confidence score)
- `repost_of` — Exact media match (pHash hamming distance 0-5)
- `mutation_of` — Modified media (hamming distance 6-15)
- `debunked_by` — Fact check contradicts claim
- `amplified_by` — Spread tracking

### Semantic Roles (assigned by classifier)
- `originator` — Earliest in timeline
- `amplifier` — Connected via REPOST_OF
- `mutator` — Connected via MUTATION_OF
- `unwitting_sharer` — No outgoing edges to external sources

## Frontend Pages

- `/` — Landing page (hero, what we do, tip submission form, bureau door puzzle)
- `/bureau/` — Redirects to `/bureau/wall`
- `/bureau/wall` — Case Wall (corkboard with draggable case cards, string connections, pan/zoom)
- `/bureau/case/[id]` — Case Workspace (evidence network graph + story view + evidence detail panel)
- `/bureau/solved` — Solved cases
- `/bureau/archive` — Archive
- `/bureau/admin` — Admin panel (admin role only)
- `/bureau/settings` — Settings

## Key Frontend Components

- `components/wolftrace-provider.tsx` — Global state provider, backend data loading, WebSocket connection
- `components/bureau/case-wall.tsx` — Corkboard UI with search, filter, drag-to-connect cases
- `components/bureau/case-card.tsx` — Draggable case card with status, location, heat glow
- `components/bureau/case-workspace.tsx` — Case detail view with tabs (Evidence Network, Story View)
- `components/bureau/evidence-network.tsx` — Canvas-based force-directed graph for evidence nodes
- `components/bureau/evidence-detail.tsx` — Side panel for selected evidence details
- `components/bureau/story-panel.tsx` — Narrative story view of case
- `components/bureau/add-evidence-modal.tsx` — Modal for adding new evidence
- `components/bureau/sidebar.tsx` — Bureau navigation sidebar
- `components/landing/bureau-door-modal.tsx` — Hidden puzzle to enter the bureau (double-click streetlamp)
- `components/landing/tip-submission.tsx` — Public tip submission form
- `lib/api-client.ts` — ShadowBureauAPI class + ShadowBureauWebSocket class + type mappers
- `lib/types.ts` — TypeScript interfaces (Case, Evidence, EvidenceConnection, Tip)
- `lib/store.ts` — React Context definition (WolfTraceCtx, useWolfTrace hook)
- `lib/mock-data.ts` — Mock data for development without backend

## ID Conventions

- Case IDs: `CASE-{Adjective}-{Noun}-{4digits}` (e.g., CASE-MIDNIGHT-CIPHER-7203)
- Report IDs: `RPT-{12hex}` (e.g., RPT-A1B2C3D4E5F6)
- Node IDs: `{Prefix}-{12hex}` (prefix: R for report, E for external, F for fact_check, M for media)
- Edge IDs: `E-{12hex}`
- Alert IDs: `ALT-{12hex}`

## Type Mappings (Backend <-> Frontend)

- Backend `case_id` -> Frontend `id`
- Backend `label`/`case_id` -> Frontend `codename`
- Backend `status: "pending"` -> Frontend `status: "Investigating"` (via status map)
- Backend `node (report)` -> Frontend `Evidence (type: text)`
- Backend `edge (similar_to)` -> Frontend `EvidenceConnection (relation: related)`

## Running the Project

### Backend
```bash
cd shadow-bureau-backend
cp .env.example .env  # Add API keys
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Frontend
```bash
cd WolfTrace-ui
pnpm install
# Set NEXT_PUBLIC_USE_BACKEND=true in .env.local
pnpm dev
```

### Seed Mock Data (New in Feb 2026)
```bash
# Seed database with 11 mock cases including "The Phantom Fire" misinformation scenario
curl -X POST http://localhost:8000/api/seed

# Expected response: {"cases": 11, "evidence": 30, "connections": 19, "tips": 4}
```

**What gets seeded:**
- 11 cases (case-001 to case-011) with metadata (codename, status, summary, story)
- 30 evidence nodes (ev-001 to ev-030) as GraphNode objects
- 19 evidence connections as GraphEdge objects
- 4 unattached tips (tip-001 to tip-004)
- Special case: case-011 "The Phantom Fire" - demonstrates misinformation detection with 3-node inference pattern

**Source:** `app/seed_data.py` - Translated from frontend `lib/mock-data.ts`

### Test with curl
```bash
# Submit a tip
curl -X POST http://localhost:8000/api/report \
  -H "Content-Type: application/json" \
  -d '{"text_body": "Test report", "anonymous": true}'

# List cases
curl http://localhost:8000/api/cases | jq

# Upload a file
curl -X POST http://localhost:8000/api/upload \
  -F "file=@/path/to/image.jpg"

# Expected: {"file_url": "file:///tmp/wolftrace-uploads/image.jpg", "filename": "image.jpg", ...}
```

## Current State / Phase

**Phase 1 (Core Features): ✅ COMPLETE**
- API integration with frontend
- WebSocket real-time updates
- Case/evidence mapping
- Tip submission flow
- File upload endpoint (`POST /api/upload`)
- Seed data system for testing (`app/seed_data.py`)

**Phase 2 (AI Pipelines): ✅ OPERATIONAL**
- Blackboard Architecture controller running
- 7 knowledge sources active: clustering, forensics, network, classifier, recluster_debunk, case_synthesizer
- Automatic inference on report submission
- Temporal, geospatial, and semantic clustering
- Claim extraction via Backboard/Gemini
- Fact-checking integration
- Media forensics (pHash, ELA, EXIF, TwelveLabs)

**Remaining Work:**
- Alert drafting UI integration (backend endpoints ready, need frontend UI)
- Walkie-talkie leads panel (need endpoint + frontend)
- Witness inbox full page (frontend only)
- JWT authentication (replace cookie-based auth)
- Neo4j persistent storage (optional - currently in-memory works well)
- Production file storage (move from `/tmp` to S3/Cloudinary)

---

## Recent Changes (Feb 2026)

### ✅ PHASE 1-7 IMPLEMENTATION (Complete - Feb 15, 2026)

**Comprehensive feature implementation across backend and frontend:**

#### Phase 1: Forensic Analysis Integration (CRITICAL) ✅

**New Endpoints:**
- `POST /api/cases/{case_id}/evidence/{evidence_id}/forensics` - Trigger forensic analysis
- `GET /api/cases/{case_id}/evidence/{evidence_id}/forensics` - Get forensic results
- `POST /api/cases/{case_id}/chat` - Evidence chat with AI

**Modified Files:**
1. **`app/routers/cases.py`** - Added forensic endpoints:
   - `analyze_forensics()` - Routes to Backboard (images) or TwelveLabs (videos)
   - `get_forensic_results()` - Fetches existing analysis from node.data
   - `chat_with_evidence()` - AI chat with evidence context
   - Helper functions: `_is_image()`, `_is_video()`

2. **`app/services/backboard_client.py`** - Image forensic analysis:
   ```python
   async def analyze_image_forensics(image_url: str, evidence_context: dict) -> dict:
       # Uses Backboard Claim Analyst with vision
       # Returns: authenticity_score, manipulation_probability, quality_score, indicators
       # Includes evidence context: claims, entities, location, semantic role
   ```

3. **`app/services/twelvelabs.py`** - Video deepfake detection:
   ```python
   async def detect_deepfake(video_url: str, evidence_context: dict) -> dict:
       # 1. Index video with Marengo 2.6
       # 2. Wait for indexing completion
       # 3. Search for deepfake indicators
       # 4. Calculate scores using heuristics
       # Returns: deepfake_probability, manipulation_probability, quality_score, authenticity_score

   async def wait_for_indexing(task_id: str, max_wait: int = 120) -> bool:
       # Polls task status every 5 seconds until ready
   ```

4. **`app/pipelines/forensics.py`** - Enhanced with AI scoring:
   - `_process_image()` - Now includes Backboard vision analysis
   - `_process_video()` - Now includes TwelveLabs deepfake detection
   - Both methods combine traditional forensics (pHash, EXIF, ELA) with AI scores
   - Graceful fallback when APIs unavailable

**API Configuration Required:**
```bash
# .env file
BACKBOARD_API_KEY=<your-key>
TWELVELABS_API_KEY=<your-key>
TWELVELABS_INDEX_ID=<your-index-id>  # Create index via TwelveLabs dashboard
```

#### Phase 2: Evidence Structure Fixes ✅

**Delete Node Functionality:**

1. **`app/graph_state.py`** - Cascade deletion:
   ```python
   def delete_node(node_id: str) -> dict:
       # Finds all connected edges
       # Deletes edges first
       # Removes from adjacency and case reports tracking
       # Deletes node
       # Returns: deleted_node, deleted_edges, edge_ids
   ```

2. **`app/routers/cases.py`** - Delete endpoint:
   ```python
   @router.delete("/cases/{case_id}/evidence/{evidence_id}")
   async def delete_evidence(case_id: str, evidence_id: str):
       # Validates evidence belongs to case
       # Calls delete_node()
       # Broadcasts deletion via WebSocket
   ```

#### Phase 3: Confidence & Review System ✅

**Enhanced Review Endpoint:**

**`app/routers/cases.py`** - Modified `mark_evidence_reviewed()`:
```python
@router.patch("/cases/{case_id}/evidence/{evidence_id}")
async def mark_evidence_reviewed(case_id: str, evidence_id: str, body: dict):
    # When reviewed=True, sets confidence=1.0
    update_data = {
        "reviewed": reviewed,
        "confidence": 1.0 if reviewed else node.data.get("confidence", 0.0)
    }
    # Returns: id, reviewed, confidence
```

#### Phase 5: Enhanced Inference System ✅

**Inference Endpoint Enhancement:**

**`app/routers/cases.py`** - Enhanced `get_evidence_inference()`:
```python
@router.get("/cases/{case_id}/evidence/{evidence_id}/inference")
async def get_evidence_inference(case_id: str, evidence_id: str):
    # NEW: Added summary section
    return {
        "evidence_id": evidence_id,
        "summary": {
            "total_connections": len(inferences),
            "avg_confidence": total_confidence / total_connections,
            "strongest_connection": strongest["target_id"],
            "connection_types": {"similar_to": 5, "debunked_by": 2, ...}
        },
        "inferences": [...],  # Enhanced with detailed reasoning
        "ai_analysis": {...}
    }
```

**Enhanced Reasoning Function:**

**`app/routers/cases.py`** - Improved `_generate_connection_reasoning()`:
```python
def _generate_connection_reasoning(...) -> str:
    # NEW: Explicit component scores in reasoning
    # Example output: "Events occurred within minutes (temporal: 85%),
    #                  same location (geo: 92%), highly similar content (semantic: 78%)"

    # Temporal reasoning thresholds:
    # - >0.8: "within minutes"
    # - >0.6: "within hours"
    # - >0.3: "similar time period"

    # Geographic reasoning thresholds:
    # - >0.8: "same location"
    # - >0.5: "nearby locations"
    # - >0.3: "same region"

    # Semantic reasoning thresholds:
    # - >0.7: "highly similar content"
    # - >0.4: "related content"
    # - >0.2: "loosely related"
```

#### Phase 6: Story Generation ✅

**New Story Endpoint:**

**`app/routers/cases.py`** - Added `get_case_story()`:
```python
@router.get("/cases/{case_id}/story")
async def get_case_story(case_id: str):
    # 1. Gets all nodes for the case
    # 2. Sorts reports by timestamp
    # 3. Formats timeline and connections for AI
    # 4. Uses AI service to generate narrative
    # 5. Parses sections (Origin, Progression, Current Status)
    # 6. Identifies key moments based on connection patterns

    return {
        "case_id": case_id,
        "narrative": "AI-generated coherent narrative...",
        "sections": {"origin": "...", "progression": "...", "status": "..."},
        "key_moments": [{"description": "...", "detail": "..."}]
    }
```

**Helper Functions:**
```python
def _parse_narrative_sections(narrative: str) -> dict[str, str]:
    # Parses AI response into structured sections

def _identify_key_moments(timeline: list, edges: list) -> list[dict]:
    # Finds nodes with most connections (top 3)
    # Returns as key moments with descriptions
```

### ✅ File Upload Router (Previous Work)

**New File:** `app/routers/files.py` (85 lines)

**Endpoints:**
- `POST /api/upload` - Upload media files (image/video/audio)
- `DELETE /api/upload/{filename}` - Delete uploaded file

**Features:**
- File type validation (only image/video/audio allowed)
- Saves to `/tmp/wolftrace-uploads/` directory
- Returns file URL in `file://` format
- Returns metadata: filename, content_type, size
- Error handling for invalid types and upload failures

**Usage:**
```bash
curl -X POST http://localhost:8000/api/upload \
  -F "file=@/path/to/image.jpg"

# Response:
# {
#   "file_url": "file:///tmp/wolftrace-uploads/image_abc123.jpg",
#   "filename": "image_abc123.jpg",
#   "content_type": "image/jpeg",
#   "size": 245680
# }
```

**Integration:**
- Registered in `app/main.py`: `app.include_router(files.router)`
- Used by Forensics Lab frontend component for file analysis
- Files can be referenced in evidence nodes via `media_url` field

### ✅ Seed Data System (Previous Work)

**New File:** `app/seed_data.py` (503 lines)

**Purpose:** Populate in-memory graph with realistic test data translated from frontend mock data

**Endpoint:** `POST /api/seed`

**What Gets Seeded:**
- 11 cases (case-001 to case-011) with full metadata
- 30 evidence nodes (ev-001 to ev-030) as GraphNode objects
- 23 evidence connections as GraphEdge objects (UPDATED)
- 4 unattached tips (tip-001 to tip-004)

**Special Cases:**
- **case-011 "The Phantom Fire"**: Demonstrates misinformation detection
  - ev-028: Suspicious social media post claiming fire
  - ev-029: Verified official report confirming false alarm
  - ev-030: Fabricated image supporting false claim
  - Triangle inference pattern: Official contradicts both suspicious sources

**Status Mapping:**
```python
STATUS_MAP = {
    "Investigating": "active",
    "Confirmed": "verified",
    "Debunked": "debunked",
    "All-clear": "resolved",
    "Closed": "closed",
}
```

**Usage:**
```bash
curl -X POST http://localhost:8000/api/seed

# Response:
# {"status":"seeded","cases":11,"evidence":30,"connections":23,"tips":4}
```

**Data Flow:**
1. Clears all existing in-memory data (`clear_all()`)
2. Creates case metadata via `set_case_metadata()`
3. Adds evidence nodes via `add_node()`
4. Adds report entries via `add_report()`
5. Creates edges via `add_edge()`

### 🔄 Enhanced Cases Router

**File:** `app/routers/cases.py`

**Recent Additions:**
- Improved edge creation endpoint with validation
- Better error handling for missing cases
- Support for cross-case edges
- Enhanced node/edge data formatting for frontend

### 📊 Pipeline Improvements

**Files:** `app/pipelines/classifier.py`, `app/pipelines/clustering.py`

**Enhancements:**
- More robust semantic role classification
- Better handling of edge cases in clustering
- Improved confidence scoring for SIMILAR_TO edges
- Enhanced temporal/geospatial matching thresholds

---

## Testing Workflow

### 1. Start Backend
```bash
cd /home/harsha/Documents/temp/hackathon/wolf-trace-backend
uv run uvicorn app.main:app --reload
```

### 2. Verify Health
```bash
curl http://localhost:8000/health | jq
# Expected: {"status":"ok","controller_running":true,"knowledge_sources":7}
```

### 3. Seed Data (Optional)
```bash
curl -X POST http://localhost:8000/api/seed | jq
# Seeds 11 cases with evidence
```

### 4. Submit Test Report (Alternative)
```bash
curl -X POST http://localhost:8000/api/report \
  -H "Content-Type: application/json" \
  -d '{
    "text_body": "Test fire alarm at Science Building",
    "location": {"building": "Science Building", "lat": 40.7489, "lng": -73.9681},
    "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
    "anonymous": true
  }' | jq
```

### 5. View Created Cases
```bash
curl http://localhost:8000/api/cases | jq
```

### 6. View Case Detail
```bash
curl http://localhost:8000/api/cases/case-001 | jq
```

### 7. Watch WebSocket Updates (Optional)
```bash
# Install websocat: cargo install websocat
websocat ws://localhost:8000/ws/caseboard
# Will show real-time graph updates as events occur
```

---

## File Organization

### Routers
- `app/routers/cases.py` - Case and evidence CRUD + **6 NEW ENDPOINTS** (forensics, chat, delete, story, inference) ✅
- `app/routers/reports.py` - Tip submission
- `app/routers/alerts.py` - Alert drafting and publishing
- `app/routers/ws.py` - WebSocket real-time updates
- `app/routers/files.py` - File upload/delete ✅
- `app/routers/seed.py` - Seed data endpoint ✅

### Pipelines (Knowledge Sources)
- `app/pipelines/clustering.py` - Temporal/geo/semantic deduplication
- `app/pipelines/forensics.py` - Media analysis (pHash, ELA, EXIF, TwelveLabs) **+ AI SCORING** ✅
- `app/pipelines/network.py` - Claim extraction, fact-checking, search
- `app/pipelines/classifier.py` - Semantic role assignment
- `app/pipelines/recluster_debunk.py` - Debunk count updates
- `app/pipelines/case_synthesizer.py` - Narrative generation
- `app/pipelines/blackboard_controller.py` - Event-driven orchestration

### Data
- `app/graph_state.py` - In-memory graph storage **+ DELETE WITH CASCADE** ✅
- `app/seed_data.py` - Mock data for testing ✅
- `app/models/graph.py` - Pydantic models (GraphNode, GraphEdge)

### Services
- `app/services/backboard_client.py` - Backboard.io AI agents **+ IMAGE FORENSICS** ✅
- `app/services/gemini.py` - Google Gemini fallback
- `app/services/factcheck.py` - Google Fact Check API
- `app/services/twelvelabs.py` - Video analysis **+ DEEPFAKE DETECTION** ✅
- `app/services/elevenlabs.py` - Text-to-speech
- `app/services/graph_db.py` - Neo4j integration (optional)

---

## 🎯 Handoff Summary for Cursor

### What's Working (Production-Ready)
✅ **Forensic Analysis** - Real AI-powered image/video analysis (Backboard + TwelveLabs)
✅ **Evidence Management** - CRUD operations with cascade deletion
✅ **Confidence System** - Reviewed evidence = 100% confidence
✅ **Inference Engine** - Enhanced with summary statistics and detailed reasoning
✅ **Story Generation** - AI-generated case narratives
✅ **Real-time Updates** - WebSocket broadcasting for all mutations
✅ **File Upload** - Media upload to `/tmp/wolftrace-uploads/`
✅ **Seed Data** - One-command database seeding (11 cases, 30 evidence, 23 connections)

### Quick Start
```bash
# 1. Setup environment
cd wolf-trace-backend
cp .env.example .env
# Add API keys: BACKBOARD_API_KEY, TWELVELABS_API_KEY, TWELVELABS_INDEX_ID, GEMINI_API_KEY

# 2. Install dependencies
uv sync

# 3. Start server
uv run uvicorn app.main:app --reload

# 4. Seed database (in another terminal)
curl -X POST http://localhost:8000/api/seed

# 5. Verify
curl http://localhost:8000/health | jq
curl http://localhost:8000/api/cases | jq
```

### API Keys Priority
1. **REQUIRED** for forensics:
   - `BACKBOARD_API_KEY` - Image forensic analysis
   - `TWELVELABS_API_KEY` + `TWELVELABS_INDEX_ID` - Video deepfake detection

2. **OPTIONAL** (graceful fallback):
   - `GEMINI_API_KEY` - Fallback AI for claim extraction, story generation
   - `FACTCHECK_API_KEY` - Google Fact Check API
   - `ELEVENLABS_API_KEY` - Text-to-speech for alerts

### Critical Implementation Details
- **All AI services gracefully degrade** - Fallback scores when APIs unavailable
- **In-memory storage** - Data lost on restart (use seed endpoint to repopulate)
- **WebSocket events**: `add_node`, `add_edge`, `update_node`, `delete_node`
- **Context-aware AI** - Evidence metadata (claims, entities, location) passed to all AI calls
- **TwelveLabs setup** - Must create index first via dashboard, then add both API key and index ID to `.env`

### Next Steps (Optional)
- [ ] Migrate from `/tmp` to S3/Cloudinary for production file storage
- [ ] Add Neo4j persistent storage (optional - currently in-memory works well)
- [ ] Implement JWT authentication (replace cookie-based auth)
- [ ] Build Alerts Desk UI (backend endpoints ready)
- [ ] Build Walkie-talkie Leads panel
- [ ] Build Witness Inbox full page

### Testing Endpoints
```bash
# Forensic Analysis
curl -X POST http://localhost:8000/api/cases/case-001/evidence/ev-001/forensics

# Story Generation
curl http://localhost:8000/api/cases/case-001/story | jq

# Enhanced Inference
curl http://localhost:8000/api/cases/case-001/evidence/ev-001/inference | jq

# Delete Evidence
curl -X DELETE http://localhost:8000/api/cases/case-001/evidence/ev-001

# Evidence Chat
curl -X POST http://localhost:8000/api/cases/case-001/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What are the key claims?", "evidence_ids": ["ev-001"]}'
```

### Frontend Integration
See `/home/harsha/Documents/temp/hackathon/WolfTrace-ui/CLAUDE.md` for frontend implementation details.
