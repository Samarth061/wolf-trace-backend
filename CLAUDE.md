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
| GET | `/api/cases` | List all cases (in-memory) |
| POST | `/api/cases` | Create case in Neo4j |
| GET | `/api/cases/{id}` | Full graph snapshot for case |
| GET | `/api/cases/{id}/graph` | Neo4j graph in React Flow format |
| POST | `/api/cases/{id}/evidence` | Add evidence to Neo4j case |
| POST | `/api/cases/{id}/edges` | Create red string link between nodes |
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

### Test with curl
```bash
# Submit a tip
curl -X POST http://localhost:8000/api/report \
  -H "Content-Type: application/json" \
  -d '{"text_body": "Test report", "anonymous": true}'

# List cases
curl http://localhost:8000/api/cases | jq
```

## Current State / Phase

Phase 1 (Core Features) is complete: API integration, WebSocket real-time updates, case/evidence mapping, tip submission flow.

Remaining work includes: loading states, error handling with toasts, optimistic updates, retry logic, forensics lab UI, alert drafting UI, walkie-talkie leads panel, witness inbox, JWT auth, file uploads.
