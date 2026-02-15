"""Unified AI layer: routes to GROQ, Backboard, or Gemini based on preference."""
import json
import logging
from typing import Any

from app.services import backboard_client, gemini, groq

logger = logging.getLogger(__name__)


async def extract_claims(
    report_text: str,
    case_id: str = "",
    location: Any = None,
    timestamp: str = "",
    llm_provider: str = "groq"
) -> dict[str, Any]:
    """Extract claims using GROQ (default) or Backboard fallback.

    Provider priority:
    1. GROQ (default, fast, cheap)
    2. Backboard (uses their Gemini key)
    3. Mock data (no direct Gemini usage)
    """

    # Primary: Use GROQ
    if groq.is_available():
        try:
            logger.info("Routing extract_claims to GROQ")
            return await groq.extract_claims(report_text)
        except Exception as e:
            logger.warning(f"GROQ failed, falling back to Backboard: {e}")
            # Fall through to Backboard

    # Fallback 1: Use Backboard (uses their Gemini key)
    if backboard_client.is_available():
        try:
            threads = await backboard_client.create_case_thread(case_id)
            tid = threads.get("claim_analyst", "")
            if tid:
                past = await backboard_client.recall_memory("claim_analyst", report_text[:100])
                ctx = f"Past similar cases:\n{past}\n\n" if past else ""
                msg = f"{ctx}Analyze this report:\n\n{report_text}\n\nLocation: {location}\nTimestamp: {timestamp}"
                resp = await backboard_client.send_to_agent("claim_analyst", tid, msg)
                if resp:
                    return _parse_claims_json(resp)
        except Exception as e:
            logger.warning("Backboard extract_claims failed: %s", e)

    # Fallback 2: Return mock data (NO direct Gemini usage)
    logger.warning("Both GROQ and Backboard unavailable, returning mock claims")
    return {
        "claims": [{"statement": report_text[:200] or "Unknown claim", "confidence": 0.5, "category": "other"}],
        "urgency": 0.5,
        "misinformation_flags": [],
        "suggested_verifications": ["Verify with on-site sources"],
    }


async def fact_check_claims(claims: list[dict], case_id: str, thread_ids: dict[str, str]) -> dict[str, Any]:
    """Send claims to Backboard Fact Checker. Returns parsed JSON or empty."""
    if not backboard_client.is_available() or not thread_ids:
        return {}
    tid = thread_ids.get("fact_checker", "")
    if not tid:
        return {}
    try:
        claims_str = json.dumps(claims, indent=2)
        msg = f"Fact-check the following claims from the Claim Analyst:\n\n{claims_str}"
        resp = await backboard_client.send_to_agent("fact_checker", tid, msg)
        return _parse_claims_json(resp) if resp else {}
    except Exception as e:
        logger.warning("Backboard fact_check failed: %s", e)
        return {}


async def compose_alert(
    case_context: str,
    officer_notes: str | None,
    case_id: str = "",
    llm_provider: str = "groq"
) -> str:
    """Compose alert using GROQ (default) or Backboard fallback."""

    # Primary: Use GROQ
    if groq.is_available():
        try:
            logger.info("Routing compose_alert to GROQ")
            return await groq.compose_alert(case_context, officer_notes)
        except Exception as e:
            logger.warning(f"GROQ failed, falling back to Backboard: {e}")

    # Fallback 1: Backboard with Claude
    if backboard_client.is_available() and case_id:
        try:
            threads = backboard_client.get_thread_ids(case_id)
            tid = threads.get("alert_composer", "")
            if tid:
                msg = f"Draft a public alert for this case.\n\nCase context:\n{case_context}"
                if officer_notes:
                    msg += f"\n\nOfficer notes: {officer_notes}"
                resp = await backboard_client.send_to_agent(
                    "alert_composer", tid, msg,
                    llm_provider="anthropic",
                    model_name="claude-sonnet-4-5-20250929",
                )
                if resp:
                    data = _parse_claims_json(resp)
                    if isinstance(data, dict) and data.get("alert_text"):
                        return data["alert_text"]
                    return resp.strip()
        except Exception as e:
            logger.warning("Backboard compose_alert failed: %s", e)

    # Fallback 2: Mock alert (NO direct Gemini usage)
    logger.warning("Both GROQ and Backboard unavailable, returning mock alert")
    return "Campus Safety Notice: We are investigating a reported incident. Please avoid the area until further notice. Check official channels for updates."


async def synthesize_case(case_id: str, thread_ids: dict[str, str], case_context: str = "") -> dict[str, Any]:
    """Run Case Synthesizer on Backboard. Returns structured summary or empty."""
    if not backboard_client.is_available() or not thread_ids:
        return {}
    tid = thread_ids.get("case_synthesizer", "")
    if not tid:
        return {}
    try:
        msg = f"Case {case_id}. All agents have completed analysis. Synthesize the full case.\n\nCase context:\n{case_context}"
        resp = await backboard_client.send_to_agent("case_synthesizer", tid, msg)
        if resp:
            parsed = _parse_claims_json(resp)
            return parsed if isinstance(parsed, dict) else {}
    except Exception as e:
        logger.warning("Backboard synthesize_case failed: %s", e)
    return {}


async def generate_case_narrative(
    timeline: list[dict[str, Any]],
    connections: list[dict[str, Any]],
    case_id: str = ""
) -> str:
    """Generate case narrative using GROQ (default) or Backboard fallback.

    Args:
        timeline: List of evidence nodes sorted by timestamp
        connections: List of edges connecting evidence
        case_id: Case identifier for Backboard fallback

    Returns:
        Structured narrative with Origin, Progression, and Current Status sections
    """

    # Build rich timeline context
    timeline_context = []
    for item in timeline:
        data = item.get('data', {})
        entry = f"- {item.get('timestamp', 'Unknown')}"

        # Add title/content
        title = data.get('title') or data.get('text_body', '')[:100]
        entry += f": {title}"

        # Add claims
        claims = data.get('claims', [])
        if claims:
            claim_text = ', '.join(c.get('statement', '')[:50] for c in claims[:3])
            entry += f" | Claims: {claim_text}"

        # Add confidence/forensics
        confidence = data.get('confidence', 0)
        if confidence > 0:
            entry += f" | Confidence: {int(confidence * 100)}%"

        forensics = data.get('forensics', {})
        if forensics.get('authenticity_score'):
            entry += f" | Authenticity: {forensics['authenticity_score']:.0f}%"

        timeline_context.append(entry)

    # Build connection context with confidence
    connection_context = []
    for conn in connections[:20]:
        edge_type = conn.get('edge_type', 'related')
        if hasattr(edge_type, 'value'):
            edge_type = edge_type.value
        confidence = conn.get('data', {}).get('confidence', 0)
        source = conn.get('source_id', 'unknown')
        target = conn.get('target_id', 'unknown')

        conn_str = f"- {source} → {edge_type} → {target}"
        if confidence > 0:
            conn_str += f" (confidence: {int(confidence * 100)}%)"
        connection_context.append(conn_str)

    # Create enhanced prompt
    prompt = f"""Generate a coherent narrative for this investigation case.

Evidence Timeline (chronological):
{chr(10).join(timeline_context)}

Evidence Connections:
{chr(10).join(connection_context)}

Generate a structured narrative with these sections:

**Origin**: How the case started - identify earliest evidence and triggering event (1-2 sentences)

**Progression**: How investigation evolved - evidence accumulation, patterns, verified/debunked claims (2-3 sentences)

**Current Status**: Where case stands now - confidence level, verified vs suspicious evidence, uncertainties (1-2 sentences)

Keep narrative factual, concise, and focused on evidence. Use confidence scores and forensic data when assessing credibility."""

    # Primary: Use GROQ
    if groq.is_available():
        try:
            logger.info("Routing generate_case_narrative to GROQ")
            return await groq.generate_narrative(prompt)
        except Exception as e:
            logger.warning(f"GROQ failed, falling back to Backboard: {e}")

    # Fallback: Backboard Case Synthesizer
    if backboard_client.is_available() and case_id:
        try:
            threads = await backboard_client.create_case_thread(case_id)
            tid = threads.get("case_synthesizer", "")
            if tid:
                resp = await backboard_client.send_to_agent("case_synthesizer", tid, prompt)
                if resp:
                    return resp.strip()
        except Exception as e:
            logger.warning("Backboard generate_case_narrative failed: %s", e)

    # Mock fallback
    logger.warning("All AI services unavailable, returning simple narrative")
    return f"Case involves {len(timeline)} pieces of evidence. Evidence shows {len(connections)} connections. Manual review recommended."


async def generate_search_queries(claims: list[dict[str, Any]], llm_provider: str = "groq") -> list[str]:
    """Generate search queries using GROQ (default) with mock fallback."""

    # Primary: Use GROQ
    if groq.is_available():
        try:
            logger.info("Routing generate_search_queries to GROQ")
            return await groq.generate_search_queries(claims)
        except Exception as e:
            logger.warning(f"GROQ failed for search queries: {e}")

    # Fallback: Return mock queries (NO Gemini, Backboard doesn't support this)
    logger.warning("GROQ unavailable, returning mock search queries")
    return ["campus incident", "university safety alert", "student reports"]


def _parse_claims_json(text: str) -> dict[str, Any] | list:
    text = (text or "").strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    return {}
