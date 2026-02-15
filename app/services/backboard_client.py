"""Backboard.io client — 4 specialized AI agents with persistent case threads."""
import json
import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.config import settings

UPLOAD_DIR = Path("/tmp/wolftrace-uploads")

logger = logging.getLogger(__name__)

_client = None
_assistants: dict[str, Any] = {}
_case_threads: dict[str, dict[str, str]] = {}  # case_id -> {assistant_name: thread_id}
_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")

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


def _get_client():
    global _client
    if _client is None and settings.backboard_api_key:
        try:
            from backboard import BackboardClient

            _client = BackboardClient(api_key=settings.backboard_api_key)
        except ImportError as e:
            logger.warning("Backboard SDK not installed: %s", e)
        except Exception as e:
            logger.warning("Backboard client init failed: %s", e)
    return _client


def is_available() -> bool:
    return bool(_get_client() and settings.backboard_api_key)


async def get_or_create_assistants() -> dict[str, Any]:
    """Create the 4 investigation agents. Called once at startup."""
    global _assistants
    client = _get_client()
    if not client:
        return {}
    try:
        if _assistants:
            return _assistants
        existing = await client.list_assistants(limit=100)
        by_name = {a.name: a for a in existing if hasattr(a, "name")}
        for name, instructions in [
            ("Shadow Bureau — Claim Analyst", CLAIM_ANALYST_INSTRUCTIONS),
            ("Shadow Bureau — Fact Checker", FACT_CHECKER_INSTRUCTIONS),
            ("Shadow Bureau — Alert Composer", ALERT_COMPOSER_INSTRUCTIONS),
            ("Shadow Bureau — Case Synthesizer", CASE_SYNTHESIZER_INSTRUCTIONS),
        ]:
            key = name.split("—")[-1].strip().lower().replace(" ", "_")
            if name in by_name:
                _assistants[key] = by_name[name]
            else:
                a = await client.create_assistant(name=name, description=instructions)
                _assistants[key] = a
        return _assistants
    except Exception as e:
        logger.exception("get_or_create_assistants failed: %s", e)
        return {}


async def create_case_thread(case_id: str) -> dict[str, str]:
    """Create persistent Backboard threads for a case (one per assistant)."""
    global _case_threads
    if case_id in _case_threads:
        return _case_threads[case_id]
    client = _get_client()
    assistants = await get_or_create_assistants()
    if not client or not assistants:
        return {}
    threads = {}
    try:
        for key, assistant in assistants.items():
            aid = getattr(assistant, "assistant_id", None) or getattr(assistant, "id", None) or assistant
            if aid:
                t = await client.create_thread(assistant_id=aid)
                tid = _extract_thread_id(t)
                if tid:
                    threads[key] = tid
        _case_threads[case_id] = threads
        return threads
    except Exception as e:
        logger.warning("create_case_thread failed: %s", e)
        return {}


async def send_to_agent(
    assistant_key: str,
    thread_id: str,
    message: str,
    llm_provider: str = "google",
    model_name: str = "gemini-2.0-flash",
) -> str:
    """Send a message to an agent on a case thread and get the response."""
    client = _get_client()
    if not client or not thread_id:
        return ""
    try:
        resp = await client.add_message(
            thread_id=thread_id,
            content=message,
            llm_provider=llm_provider,
            model_name=model_name,
            stream=False,
        )
        if hasattr(resp, "message") and resp.message:
            return resp.message
        if hasattr(resp, "content") and resp.content:
            return resp.content
        return ""
    except Exception as e:
        logger.warning("send_to_agent failed: %s", e)
        return ""


async def add_memory(assistant_key: str, content: str, metadata: dict[str, Any] | None = None) -> None:
    """Store a memory for an assistant (cross-case intelligence)."""
    client = _get_client()
    assistants = await get_or_create_assistants()
    if not client or assistant_key not in assistants:
        return
    try:
        aid = getattr(assistants[assistant_key], "assistant_id", None) or getattr(assistants[assistant_key], "id", None)
        if aid:
            await client.add_memory(assistant_id=aid, content=content, metadata=metadata)
    except Exception as e:
        logger.warning("add_memory failed: %s", e)


async def recall_memory(assistant_key: str, query: str) -> str:
    """Retrieve relevant memories for an assistant (via thread context)."""
    client = _get_client()
    assistants = await get_or_create_assistants()
    if not client or assistant_key not in assistants:
        return ""
    try:
        aid = getattr(assistants[assistant_key], "assistant_id", None) or getattr(assistants[assistant_key], "id", None)
        if not aid:
            return ""
        resp = await client.get_memories(assistant_id=aid)
        if hasattr(resp, "memories") and resp.memories:
            relevant = [m.content for m in resp.memories if query.lower() in (m.content or "").lower()]
            return "\n".join(relevant[:5]) if relevant else ""
    except Exception as e:
        logger.warning("recall_memory failed: %s", e)
    return ""


def _parse_json(text: str) -> dict[str, Any] | list[Any]:
    text = (text or "").strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to recover JSON from mixed content
        m = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
    return {}


def get_assistants() -> dict[str, Any]:
    return _assistants


def get_thread_ids(case_id: str) -> dict[str, str]:
    return _case_threads.get(case_id, {})


def _extract_thread_id(thread: Any) -> str | None:
    if thread is None:
        return None
    if isinstance(thread, str):
        m = _UUID_RE.search(thread)
        return m.group(0) if m else (thread if _UUID_RE.fullmatch(thread.strip()) else None)
    if isinstance(thread, dict):
        for key in ("id", "thread_id"):
            val = thread.get(key)
            if val:
                s = str(val)
                if _UUID_RE.fullmatch(s.strip()) and " " not in s:
                    return s
        text = str(thread)
        m = _UUID_RE.search(text)
        return m.group(0) if m else None
    for attr in ("thread_id", "id"):
        val = getattr(thread, attr, None)
        if val is not None:
            s = str(val)
            if "thread_id=" in s or "UUID(" in s or " " in s or "datetime" in s:
                break
            if _UUID_RE.fullmatch(s.strip()):
                return s
    text = str(thread)
    m = _UUID_RE.search(text)
    return m.group(0) if m else None


def _resolve_media_to_local_path(media_url: str) -> Path | None:
    """Resolve media_url to a local filesystem path for Backboard SDK files= parameter.

    Handles:
    - file:///tmp/wolftrace-uploads/xyz.jpg -> /tmp/wolftrace-uploads/xyz.jpg
    - http://localhost:8000/api/upload/xyz.jpg -> /tmp/wolftrace-uploads/xyz.jpg
    - /api/upload/xyz.jpg (relative path) -> /tmp/wolftrace-uploads/xyz.jpg

    Returns None if the path cannot be resolved or the file does not exist.
    """
    if not media_url:
        return None
    url = media_url.strip()
    if url.startswith("file://"):
        try:
            path = Path(url.replace("file://", "", 1))
            return path if path.exists() else None
        except Exception:
            return None
    try:
        parsed = urlparse(url)
        if parsed.path.startswith("/api/upload/"):
            filename = Path(parsed.path).name
            local_path = UPLOAD_DIR / filename
            return local_path if local_path.exists() else None
    except Exception:
        pass
    return None


async def analyze_image_forensics(image_url: str, evidence_context: dict[str, Any]) -> dict[str, Any]:
    """
    Analyze image authenticity using Backboard vision capabilities.

    Args:
        image_url: URL to the image file
        evidence_context: Dict with claims, entities, location, semantic_role, timestamp

    Returns:
        Dict with authenticity_score, manipulation_probability, quality_score, etc.
    """
    client = _get_client()
    assistants = await get_or_create_assistants()

    if not client or "claim_analyst" not in assistants:
        logger.info("Backboard client or assistants not available for image analysis, using fallback scores")
        return _generate_fallback_scores()

    # Resolve to local path for Backboard SDK (cloud API cannot fetch file:// or localhost)
    local_path = _resolve_media_to_local_path(image_url)
    if local_path is None:
        logger.warning("Could not resolve image to local path for forensic analysis: %s", image_url[:80])
        return _generate_fallback_scores()

    try:
        logger.info("Starting image forensic analysis for: %s", local_path)
        # Build forensic analysis prompt (image attached via files=)
        prompt = f"""You are a forensic image analyst. Analyze the attached image for authenticity and manipulation.

Evidence Context:
- Claims: {evidence_context.get('claims', [])}
- Entities: {evidence_context.get('entities', [])}
- Location: {evidence_context.get('location', {})}
- Semantic Role: {evidence_context.get('semantic_role', 'unknown')}
- Timestamp: {evidence_context.get('timestamp')}

Analyze and provide:
1. Authenticity Score (0-100): How likely is this image authentic?
2. Manipulation Probability (0-100): Evidence of editing/tampering?
3. Quality Score (0-100): Image quality and resolution
4. Manipulation Indicators: List specific signs of manipulation
5. Context Consistency: Does image match the reported context?

Return JSON format ONLY (no markdown, no preamble):
{{
  "authenticity_score": 85.5,
  "manipulation_probability": 12.3,
  "quality_score": 91.0,
  "manipulation_indicators": ["minor JPEG artifacts", "EXIF metadata intact"],
  "context_consistency": "high",
  "reasoning": "detailed analysis..."
}}"""

        # Use Claim Analyst assistant (has vision capabilities)
        aid = getattr(assistants["claim_analyst"], "assistant_id", None) or getattr(assistants["claim_analyst"], "id", None)

        if not aid:
            return _generate_fallback_scores()

        # Create a temporary thread for this analysis
        thread = await client.create_thread(assistant_id=aid)
        
        # Extract thread_id robustly (SDK may return dataclass-like repr)
        thread_id = _extract_thread_id(thread)
        
        if not thread_id or thread_id.startswith("<"):
            logger.error(f"Invalid thread_id from Backboard: {thread_id}. Thread object: {thread}")
            return _generate_fallback_scores()

        # Send message with image attachment (Backboard SDK uploads file for vision analysis)
        response = await client.add_message(
            thread_id=thread_id,
            content=prompt,
            files=[str(local_path)],
            llm_provider="google",
            model_name="gemini-2.0-flash",
            stream=False,
        )

        # Extract response text
        response_text = ""
        if hasattr(response, "message") and response.message:
            response_text = response.message
        elif hasattr(response, "content") and response.content:
            response_text = response.content

        # Parse JSON response
        result = _parse_json(response_text)

        if isinstance(result, dict) and "authenticity_score" in result:
            return result
        else:
            logger.warning("Invalid forensic analysis response format. Response (truncated): %s", (response_text or "")[:500])
            return _generate_fallback_scores()

    except Exception as e:
        logger.exception("Backboard API error during image forensics analysis: %s", e)
        logger.warning("Falling back to low-confidence forensic scores due to API error")
        return _generate_fallback_scores()


def _generate_fallback_scores() -> dict[str, Any]:
    """Generate fallback forensic scores when API unavailable.
    
    Uses neutral-to-positive scores for original content while clearly indicating
    that API is unavailable and manual review is needed.
    """
    return {
        "authenticity_score": 65.0,
        "manipulation_probability": 25.0,
        "quality_score": 70.0,
        "manipulation_indicators": ["Backboard API unavailable - manual review required"],
        "context_consistency": "unknown",
        "reasoning": "Automated analysis unavailable. Scores are baseline estimates pending API recovery.",
        "ml_accuracy": 0.0,
    }


async def describe_image(image_url: str, evidence_context: dict[str, Any]) -> str:
    """Get AI description of image content for key points extraction."""
    client = _get_client()
    if not client:
        return ""
    
    try:
        assistants = await get_or_create_assistants()
        aid = getattr(assistants["claim_analyst"], "assistant_id", None) or getattr(assistants["claim_analyst"], "id", None)
        
        if not aid:
            return ""
        
        prompt = f"""Describe this image in 1-2 concise sentences. Focus on:
- What is visible in the image
- Any people, objects, or activities
- Location/setting if identifiable

Context: {evidence_context}

Provide ONLY the description, no preamble or explanation."""

        # Create a temporary thread for this analysis
        thread = await client.create_thread(assistant_id=aid)
        
        # Extract thread_id robustly (SDK may return dataclass-like repr)
        thread_id = _extract_thread_id(thread)
        
        if not thread_id or thread_id.startswith("<"):
            logger.error(f"Invalid thread_id from Backboard for image description: {thread_id}")
            return ""
        
        # Send message
        response = await client.add_message(
            thread_id=thread_id,
            content=prompt,
            llm_provider="google",
            model_name="gemini-2.0-flash",
            stream=False,
        )
        
        # Extract response text
        response_text = ""
        if hasattr(response, "message") and response.message:
            response_text = response.message
        elif hasattr(response, "content") and response.content:
            response_text = response.content
        
        # Limit length and return
        return response_text[:200] if response_text else ""
        
    except Exception as e:
        logger.warning("describe_image failed: %s", e)
        return ""
