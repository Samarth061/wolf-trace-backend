# Shadow Bureau: Dead Drop — Rebuild Backend with Backboard.io

> **Implemented.** This spec has been built. See `app/services/backboard_client.py`, `app/services/ai.py`, and pipeline integrations.

Paste this into Cursor. This replaces direct Gemini API calls with Backboard.io's unified AI stack for multi-agent investigation with persistent memory.

---

## THE PROMPT

I'm rebuilding the **Shadow Bureau: Dead Drop** backend to use **Backboard.io** (https://backboard.io) as the AI infrastructure layer. Backboard is a unified API that gives us persistent memory, 17,000+ LLM access, RAG, and stateful threads — all through one API. This replaces our direct Gemini calls and gives us multi-agent AI with shared memory for the investigation engine.

### What Backboard.io gives us
- **Single API** (`https://app.backboard.io/api`) for all LLM calls (Gemini, Claude, GPT, Llama, etc.)
- **Persistent memory threads** — each case gets a thread that remembers all evidence, claims, and analysis across messages
- **Assistants** — we create specialized AI assistants (agents) with different instructions, and they share context through threads
- **RAG** — upload evidence documents, and assistants can retrieve from them
- **Model routing** — route simple tasks to cheap models, complex reasoning to expensive ones
- Install: `pip install backboard`
- Client: `client = backboard.Client(api_key="bk_...")`
- Memory: `client.add("case_id", "evidence text...")`

### The multi-agent architecture

Instead of one Gemini API doing everything, we create **4 specialized Backboard assistants** (agents) that collaborate through shared case threads:

```
┌─────────────────────────────────────────────────────────┐
│                    Backboard.io                          │
│              (Persistent Memory Layer)                   │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  Agent 1:     │  │  Agent 2:     │  │  Agent 3:     │  │
│  │  Claim        │  │  Fact         │  │  Alert        │  │
│  │  Analyst      │  │  Checker      │  │  Composer     │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
│         │                  │                  │          │
│         └──────────┬───────┴──────────┬──────┘          │
│                    ▼                  ▼                  │
│              ┌──────────────────────────┐                │
│              │   Shared Case Thread     │                │
│              │   (persistent memory)    │                │
│              └──────────────────────────┘                │
│                         ▲                               │
│                         │                               │
│              ┌──────────────────────────┐                │
│              │  Agent 4:                │                │
│              │  Case Synthesizer        │                │
│              │  (reads all agent output)│                │
│              └──────────────────────────┘                │
└─────────────────────────────────────────────────────────┘
```

**Agent 1 — Claim Analyst:** Extracts structured claims from raw tip text. Flags misinformation patterns. Suggests verifications. Writes findings to the case thread.

**Agent 2 — Fact Checker:** Reads claims from the thread, cross-references with web search and Google Fact Check API, writes verdicts back to the thread.

**Agent 3 — Alert Composer:** Reads the full case thread (all evidence, claims, fact-checks, officer notes) and drafts a public safety alert. Has persistent memory of past alerts for consistency.

**Agent 4 — Case Synthesizer:** Reads the entire case thread after all agents have contributed. Produces a structured case summary, identifies the likely originator, maps the spread network, and assigns confidence scores. This feeds the case board graph.

### What to build

#### 1. `app/services/backboard_client.py` — Backboard client wrapper

```python
import backboard

# Initialize on import
client = backboard.Client(api_key=settings.BACKBOARD_API_KEY)

# Create the 4 assistants on app startup (idempotent — check if they exist first)
# Store assistant IDs in memory after creation

async def get_or_create_assistants():
    """Create the 4 investigation agents. Called once at startup."""
    
    claim_analyst = client.assistants.create(
        name="Shadow Bureau — Claim Analyst",
        instructions=CLAIM_ANALYST_INSTRUCTIONS,  # see below
        llm_provider="google",
        llm_model_name="gemini-2.0-flash",
    )
    
    fact_checker = client.assistants.create(
        name="Shadow Bureau — Fact Checker", 
        instructions=FACT_CHECKER_INSTRUCTIONS,
        llm_provider="google",
        llm_model_name="gemini-2.0-flash",
    )
    
    alert_composer = client.assistants.create(
        name="Shadow Bureau — Alert Composer",
        instructions=ALERT_COMPOSER_INSTRUCTIONS,
        llm_provider="anthropic",  # use Claude for careful, factual writing
        llm_model_name="claude-sonnet-4-5-20250929",
    )
    
    case_synthesizer = client.assistants.create(
        name="Shadow Bureau — Case Synthesizer",
        instructions=CASE_SYNTHESIZER_INSTRUCTIONS,
        llm_provider="google",
        llm_model_name="gemini-2.0-flash",
    )
    
    return {
        "claim_analyst": claim_analyst,
        "fact_checker": fact_checker,
        "alert_composer": alert_composer,
        "case_synthesizer": case_synthesizer,
    }

async def create_case_thread(case_id: str):
    """Create a persistent Backboard thread for a case."""
    # Each case gets its own thread — agents share context through it
    thread = client.threads.create()
    return thread.id

async def send_to_agent(assistant_id: str, thread_id: str, message: str):
    """Send a message to an agent on a case thread and get the response."""
    # Add user message to thread
    client.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=message,
    )
    # Run the assistant
    run = client.threads.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id,
    )
    # Poll for completion (or use streaming if available)
    while run.status not in ("completed", "failed"):
        run = client.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
        await asyncio.sleep(0.5)
    # Get the assistant's response
    messages = client.threads.messages.list(thread_id=thread_id)
    return messages.data[0].content[0].text.value

async def add_memory(entity_id: str, memory_text: str):
    """Store a memory for an entity (case, report, etc.)."""
    client.add(entity_id, memory_text)

async def recall_memory(entity_id: str, query: str):
    """Retrieve relevant memories for an entity."""
    return client.search(entity_id, query)
```

NOTE: The exact Backboard Python SDK methods may differ — check https://app.backboard.io/docs for the current API. The pattern above (assistants, threads, messages, runs) follows their OpenAI-compatible interface. Adapt the method names to match their actual SDK. The key concepts are:
- Create assistants with specialized instructions
- Create threads per case for shared context
- Send messages and run assistants on threads
- Use memory API for long-term knowledge

#### 2. Agent Instructions (system prompts)

```python
CLAIM_ANALYST_INSTRUCTIONS = """You are the Claim Analyst for Shadow Bureau, a campus safety intelligence system.

When given a raw tip or report, you must:
1. Extract ALL factual claims as a JSON array with: statement, confidence (0-1), category (threat/property/medical/environmental/rumor/other)
2. Flag misinformation patterns: forwarded-many-times language, urgency without specificity, appeals to unnamed authorities, missing attribution, AI-generated indicators
3. Assess urgency: critical, high, medium, or low
4. Suggest 1-3 concrete verification steps (check camera, call desk, etc.)

IMPORTANT: You are writing to a shared case thread. Other agents will read your output. Structure it clearly with labeled sections.

Respond in JSON. No preamble."""

FACT_CHECKER_INSTRUCTIONS = """You are the Fact Checker for Shadow Bureau.

You receive claims extracted by the Claim Analyst from the case thread. For each claim:
1. Assess whether the claim can be verified or is likely misinformation
2. Check for common misinformation patterns specific to campus safety (swatting, false active threats, viral hoaxes)
3. Rate each claim: VERIFIED, UNVERIFIED, LIKELY_FALSE, DEBUNKED
4. Provide reasoning for each rating

You have access to the full case thread history. Use prior evidence and context from other agents.

Respond in JSON."""

ALERT_COMPOSER_INSTRUCTIONS = """You are the Alert Composer for Shadow Bureau.

Given a case thread containing claims, fact-check results, and evidence, draft a public safety alert.

RULES:
- Use ONLY confirmed facts. Never speculate.
- Never identify individuals by name.
- Include: status (Confirmed/Investigating/All Clear), location, what is known, clear student instructions, timestamp.
- Keep under 100 words.
- Tone: calm, factual, authoritative. No panic language.

You have persistent memory of past alerts. Maintain consistency in tone and format.

Respond in JSON: {"status": "...", "location_summary": "...", "alert_text": "..."}"""

CASE_SYNTHESIZER_INSTRUCTIONS = """You are the Case Synthesizer for Shadow Bureau.

After all other agents have analyzed a case, you read the entire thread and produce a structured case summary:

1. **Narrative:** One-paragraph summary of what happened, what was claimed, and what was verified.
2. **Origin analysis:** Which source appears to be the originator based on timestamps and content analysis.
3. **Spread map:** How the information spread (original → amplifiers → mutations → student reports).
4. **Confidence assessment:** Overall case confidence score (0-1) with reasoning.
5. **Recommended action:** What security should do next.

This summary feeds the evidence dashboard / case board.

Respond in JSON."""
```

#### 3. Updated pipeline integration

Replace the current `app/services/gemini.py` calls with Backboard agent calls:

**In `app/pipelines/network.py`:**
```python
# OLD: result = await extract_claims(text_body) using direct Gemini
# NEW:
from app.services.backboard_client import send_to_agent, assistants, case_threads

thread_id = case_threads[case_id]  # get or create thread for this case
claims_result = await send_to_agent(
    assistants["claim_analyst"].id, 
    thread_id,
    f"Analyze this report:\n\n{text_body}\n\nLocation: {report.get('location')}\nTimestamp: {report.get('timestamp')}"
)
# Parse JSON from agent response
# Then send claims to fact checker on the SAME thread:
fact_result = await send_to_agent(
    assistants["fact_checker"].id,
    thread_id,
    f"Fact-check the claims from the Claim Analyst above."
)
# The fact checker can see the claim analyst's output because they share the thread
```

**In `app/routers/alerts.py`:**
```python
# OLD: result = await draft_alert(case_context) using direct Gemini
# NEW:
alert_result = await send_to_agent(
    assistants["alert_composer"].id,
    thread_id,
    f"Draft a public alert for this case. Officer notes: {officer_notes}"
)
# Alert composer reads the ENTIRE thread — all evidence, claims, fact-checks
```

**New: After all pipelines complete, run the synthesizer:**
```python
synthesis = await send_to_agent(
    assistants["case_synthesizer"].id,
    thread_id,
    "All agents have completed analysis. Synthesize the full case."
)
# Use synthesis to update graph nodes with roles, confidence, narrative
```

#### 4. Memory integration for cross-case intelligence

```python
# When a case is analyzed, store key findings in Backboard memory
await add_memory(
    f"campus_intel",
    f"Case {case_id}: {narrative}. Origin: {origin}. Verdict: {verdict}."
)

# When a NEW report comes in, check if similar incidents have been seen before
past_context = await recall_memory("campus_intel", report_text)
# Feed this into the Claim Analyst's prompt for richer analysis
```

This means Agent 1 (Claim Analyst) gets smarter over time — it remembers past hoaxes, repeat offenders, and known misinformation patterns from previous cases.

### Project structure changes

```
app/services/
├── backboard_client.py    # NEW — Backboard client, assistants, threads, memory
├── gemini.py              # REMOVE or keep as fallback
├── twelvelabs.py          # KEEP — video forensics (not replaced by Backboard)
├── elevenlabs.py          # KEEP — voice dispatch (not replaced by Backboard)
└── factcheck.py           # KEEP — Google Fact Check API (called by Fact Checker agent)
```

### Environment variables to add
```
BACKBOARD_API_KEY=bk_your_api_key_here
```

### Dependencies to add
```
backboard
```

### What stays the same
- FastAPI app structure, routers, WebSockets — unchanged
- In-memory graph state and event bus — unchanged
- Forensics pipeline (ELA, pHash, EXIF) — unchanged (these are local compute, not LLM)
- TwelveLabs integration — unchanged (video-specific, not replaced by Backboard)
- ElevenLabs integration — unchanged (TTS, not replaced by Backboard)
- Clustering pipeline — unchanged (math-based, not LLM)
- Google Fact Check API — still called directly, but results are fed INTO the Fact Checker agent

### What changes
- `services/gemini.py` → replaced by `services/backboard_client.py`
- `pipelines/network.py` → uses Backboard agents instead of direct Gemini calls
- `routers/alerts.py` → alert drafting uses Backboard Alert Composer agent
- `pipelines/orchestrator.py` → after all 3 pipelines, runs Case Synthesizer agent
- `main.py` → lifespan creates Backboard assistants on startup
- New: cross-case memory for pattern recognition

### The key win for hackathon judges
Instead of "we called Gemini 3 times with different prompts," the pitch becomes: "We built a **multi-agent investigation team** where 4 specialized AI agents collaborate through shared case memory. The Claim Analyst extracts evidence, the Fact Checker verifies it, the Case Synthesizer maps the spread, and the Alert Composer drafts the public response — all sharing context through Backboard's persistent memory layer. And the system gets smarter with every case because it remembers past investigations."

### Critical constraints
- **Backboard SDK is `pip install backboard`.** Check their docs at https://app.backboard.io/docs for exact method signatures — the assistant/thread/run pattern may use slightly different naming than shown above. Adapt accordingly.
- **Graceful fallback:** If `BACKBOARD_API_KEY` is not set, fall back to direct Gemini calls (keep `gemini.py` as a fallback service).
- **Thread per case:** Create one Backboard thread per `case_id`. Store the mapping in memory: `dict[case_id, thread_id]`.
- **Agent responses must be parsed as JSON.** Wrap all agent calls in try/except with JSON parsing and strip markdown fences.
- **Don't block the event loop.** If the Backboard SDK is synchronous, wrap calls in `asyncio.to_thread()`.

Build the complete integration. Every file, production-ready. I have 24 hours.