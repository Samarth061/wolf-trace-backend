"""Unified AI layer: Backboard when available, Gemini fallback."""
import json
import logging
from typing import Any

from app.services import backboard_client, gemini

logger = logging.getLogger(__name__)


async def extract_claims(report_text: str, case_id: str = "", location: Any = None, timestamp: str = "") -> dict[str, Any]:
    """Extract claims via Backboard Claim Analyst or Gemini fallback."""
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
            logger.warning("Backboard extract_claims failed, falling back to Gemini: %s", e)
    return await gemini.extract_claims(report_text)


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


async def compose_alert(case_context: str, officer_notes: str | None, case_id: str = "") -> str:
    """Compose alert via Backboard Alert Composer or Gemini fallback."""
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
            logger.warning("Backboard compose_alert failed, falling back to Gemini: %s", e)
    return await gemini.compose_alert(case_context, officer_notes)


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


async def generate_search_queries(claims: list[dict[str, Any]]) -> list[str]:
    """Generate search queries. Uses Gemini (Backboard doesn't replace this)."""
    return await gemini.generate_search_queries(claims)


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
