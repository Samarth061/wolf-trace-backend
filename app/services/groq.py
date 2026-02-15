"""GROQ API integration - ultra-fast LLM inference with Mixtral/Llama3."""
import json
import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    """Initialize GROQ client (lazy singleton)."""
    global _client
    if _client is None and settings.groq_api_key:
        try:
            from groq import Groq
            _client = Groq(api_key=settings.groq_api_key)
            logger.info("GROQ client initialized successfully")
        except Exception as e:
            logger.warning(f"GROQ client initialization failed: {e}")
    return _client


def is_available() -> bool:
    """Check if GROQ client is available."""
    return _get_client() is not None


# Reuse the same prompts as gemini.py for consistency
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
    """Extract claims using GROQ Llama 3.3 70B (fast, accurate)."""
    client = _get_client()
    if not client:
        logger.warning("GROQ client unavailable for extract_claims")
        return _mock_claims(report_text)

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",  # Current supported reasoning model
            messages=[
                {"role": "system", "content": "You are a disinformation analysis expert for campus safety."},
                {"role": "user", "content": f"{CLAIM_EXTRACTOR_PROMPT}\n\nReport text:\n{report_text}"}
            ],
            temperature=0.3,
            max_tokens=2000,
        )

        content = response.choices[0].message.content

        # Parse JSON response (handle markdown code blocks)
        result = _parse_claims_json(content)
        logger.info(f"GROQ extract_claims succeeded: {len(result.get('claims', []))} claims")
        return result

    except Exception as e:
        logger.warning(f"GROQ extract_claims failed: {e}")
        return _mock_claims(report_text)


async def compose_alert(case_context: str, officer_notes: str | None = None) -> str:
    """Compose public alert using GROQ Llama 3.1 8B (fast generation)."""
    client = _get_client()
    if not client:
        logger.warning("GROQ client unavailable for compose_alert")
        return _mock_alert_draft()

    try:
        prompt = f"{ALERT_COMPOSER_PROMPT}\n\nCase context:\n{case_context}"
        if officer_notes:
            prompt += f"\n\nOfficer notes:\n{officer_notes}"

        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",  # Fast, good quality (560 tokens/sec)
            messages=[
                {"role": "system", "content": "You are a public safety communications expert."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
            max_tokens=300,
        )

        alert_text = response.choices[0].message.content.strip()
        logger.info(f"GROQ compose_alert succeeded: {len(alert_text)} chars")
        return alert_text

    except Exception as e:
        logger.warning(f"GROQ compose_alert failed: {e}")
        return _mock_alert_draft()


async def generate_search_queries(claims: list[dict[str, Any]]) -> list[str]:
    """Generate search queries using GROQ Llama 3.1 8B (fast)."""
    client = _get_client()
    if not client:
        logger.warning("GROQ client unavailable for generate_search_queries")
        return _mock_search_queries()

    try:
        claims_str = json.dumps(claims, indent=2)

        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "You are a search query optimization expert."},
                {"role": "user", "content": f"{NETWORK_CRAWLER_PROMPT}\n\nClaims:\n{claims_str}"}
            ],
            temperature=0.7,
            max_tokens=200,
        )

        content = response.choices[0].message.content
        queries = _parse_search_queries(content)

        logger.info(f"GROQ generate_search_queries succeeded: {len(queries)} queries")
        return queries

    except Exception as e:
        logger.warning(f"GROQ generate_search_queries failed: {e}")
        return _mock_search_queries()


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


async def analyze_image_forensics_from_description(
    image_description: str,
    evidence_context: dict[str, Any]
) -> dict[str, Any]:
    """Generate forensic scores from text description using GROQ.

    Args:
        image_description: Text description of the image from Backboard vision
        evidence_context: Dict with claims, entities, location, semantic_role, timestamp

    Returns:
        Dict with authenticity_score, manipulation_probability, quality_score,
        ml_accuracy, manipulation_indicators
    """
    client = _get_client()
    if not client:
        logger.warning("GROQ client unavailable for forensic analysis")
        return {}

    try:
        # Build context string
        context_str = ""
        if evidence_context.get("claims"):
            context_str += f"\nReported Claims: {json.dumps(evidence_context['claims'])}"
        if evidence_context.get("location"):
            context_str += f"\nLocation: {evidence_context['location']}"
        if evidence_context.get("entities"):
            context_str += f"\nEntities: {evidence_context['entities']}"
        if evidence_context.get("timestamp"):
            context_str += f"\nTimestamp: {evidence_context['timestamp']}"

        prompt = f"""You are a forensic analyst evaluating image authenticity based on a text description.

IMAGE DESCRIPTION:
{image_description}

EVIDENCE CONTEXT:{context_str}

Analyze the image description for forensic indicators:
1. **Authenticity Score (0-100)**: How likely is the described content authentic and not AI-generated?
2. **Manipulation Probability (0-100)**: Signs of AI generation, stock photos, or digital manipulation?
3. **Quality Score (0-100)**: Clarity and detail level of the description
4. **ML Accuracy (0-100)**: Your confidence in this text-based forensic analysis
5. **Manipulation Indicators**: List specific red flags found

Consider:
- Does the description match the reported context and claims?
- Are there AI-generation patterns (too perfect, generic, stock-photo-like)?
- Are claimed entities plausible in the described visual setting?
- Does the described location match the reported location?
- Are there temporal inconsistencies (lighting/weather vs timestamp)?
- Are there suspicious elements indicating staged or synthetic content?

CRITICAL: Return ONLY valid JSON in this exact format (no markdown, no preamble):
{{
  "authenticity_score": 85.5,
  "manipulation_probability": 12.3,
  "quality_score": 91.0,
  "ml_accuracy": 75.0,
  "manipulation_indicators": ["specific indicator 1", "specific indicator 2"],
  "context_consistency": "high|medium|low",
  "reasoning": "brief explanation of scores"
}}"""

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a forensic image analysis expert. Respond ONLY with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=1500,
        )

        content = response.choices[0].message.content.strip()
        result = _parse_claims_json(content)

        if not isinstance(result, dict):
            logger.warning("GROQ forensic analysis returned invalid format")
            return {}

        # Validate required fields
        required = ["authenticity_score", "manipulation_probability", "quality_score", "ml_accuracy"]
        if not all(k in result for k in required):
            logger.warning(f"GROQ forensic analysis missing required fields")
            return {}

        # Add metadata
        result["analysis_method"] = "groq_text_based"
        result["image_description"] = image_description[:200]

        logger.info(f"GROQ forensic analysis succeeded: ml_accuracy={result['ml_accuracy']:.1f}")
        return result

    except Exception as e:
        logger.warning(f"GROQ forensic analysis failed: {e}")
        return {}
