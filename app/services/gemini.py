"""Gemini API: Claim extraction, Alert composition, Network crawler prompts."""
import json
import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is None and settings.gemini_api_key:
        try:
            import google.generativeai as genai

            genai.configure(api_key=settings.gemini_api_key)
            _client = genai.GenerativeModel("gemini-2.0-flash")
        except Exception as e:
            logger.warning("Gemini client init failed: %s", e)
    return _client


CLAIM_EXTRACTOR_PROMPT = """You are the Claim Extraction module for Shadow Bureau, a campus safety triage system.
Given a raw tip or report text from a student, extract ALL factual claims as an array.
For each claim, provide: the statement, a confidence score (0-1), and a category (threat, property, medical, environmental, rumor, other).
Also flag misinformation patterns: forwarded-many-times language, urgency without specificity, appeals to unnamed authorities, missing source attribution, AI-generated indicators.
Suggest 1-3 concrete verification steps security can take (check camera, call desk, etc.).
Respond ONLY in JSON. No preamble."""

ALERT_COMPOSER_PROMPT = """You are the Alert Composer for Shadow Bureau. Given a verified case with forensic results, clustered reports, and officer notes, generate a public safety alert.
RULES: Use only confirmed facts. Never speculate. Never identify individuals by name.
Include: status (Confirmed/Investigating/All Clear), location, what is known, clear instructions for students, timestamp. Keep it under 100 words.
Tone: calm, factual, authoritative. No panic language."""

NETWORK_CRAWLER_PROMPT = """You are the Network Crawler for Shadow Bureau. Given extracted claims from a campus incident report, generate 2-3 targeted search queries that would find related content online (social media posts, news articles, forum discussions about the same incident)."""


async def extract_claims(report_text: str) -> dict[str, Any]:
    """Extract claims from report text. Returns structured JSON with claims, urgency, misinformation_flags, suggested_verifications."""
    client = _get_client()
    if not client:
        return _mock_claims(report_text)
    try:
        response = await _generate_content(client, f"{CLAIM_EXTRACTOR_PROMPT}\n\nReport text:\n{report_text}")
        if response:
            return _parse_claims_json(response)
    except Exception as e:
        logger.warning("Gemini extract_claims failed: %s", e)
    return _mock_claims(report_text)


async def compose_alert(case_context: str, officer_notes: str | None = None) -> str:
    """Generate alert draft from case context and officer notes."""
    client = _get_client()
    if not client:
        return _mock_alert_draft()
    try:
        prompt = f"{ALERT_COMPOSER_PROMPT}\n\nCase context:\n{case_context}"
        if officer_notes:
            prompt += f"\n\nOfficer notes:\n{officer_notes}"
        response = await _generate_content(client, prompt)
        return response.strip() if response else _mock_alert_draft()
    except Exception as e:
        logger.warning("Gemini compose_alert failed: %s", e)
    return _mock_alert_draft()


async def generate_search_queries(claims: list[dict[str, Any]]) -> list[str]:
    """Generate search queries for related content discovery."""
    client = _get_client()
    if not client:
        return _mock_search_queries()
    try:
        claims_str = json.dumps(claims, indent=2)
        response = await _generate_content(client, f"{NETWORK_CRAWLER_PROMPT}\n\nClaims:\n{claims_str}")
        if response:
            return _parse_search_queries(response)
    except Exception as e:
        logger.warning("Gemini generate_search_queries failed: %s", e)
    return _mock_search_queries()


async def _generate_content(model: Any, prompt: str) -> str | None:
    """Run async generation. Gemini SDK is sync, so we run in executor."""
    import asyncio

    def _sync_gen():
        try:
            resp = model.generate_content(prompt)
            if resp and resp.text:
                return resp.text
        except Exception as e:
            logger.warning("Gemini generate_content error: %s", e)
        return None

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_gen)


def _parse_claims_json(text: str) -> dict[str, Any]:
    """Extract JSON from response, handling markdown code blocks."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    return _mock_claims("")


def _parse_search_queries(text: str) -> list[str]:
    """Parse search queries from response (numbered list or newline-separated)."""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    queries = []
    for line in lines:
        if line and not line.startswith("#"):
            if line[0].isdigit() and ". " in line:
                line = line.split(". ", 1)[1]
            queries.append(line.strip('"-'))
    return queries[:3] if queries else _mock_search_queries()


def _mock_claims(report_text: str) -> dict[str, Any]:
    return {
        "claims": [{"statement": report_text[:200] or "Unknown claim", "confidence": 0.5, "category": "other"}],
        "urgency": 0.5,
        "misinformation_flags": [],
        "suggested_verifications": ["Verify with on-site sources"],
    }


def _mock_alert_draft() -> str:
    return "Campus Safety Notice: We are investigating a reported incident. Please avoid the area until further notice. Check official channels for updates."


def _mock_search_queries() -> list[str]:
    return ["campus incident", "NC State safety", "university alert"]
