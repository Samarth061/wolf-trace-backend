"""Pipeline 2: Network Crawler — Backboard/Gemini claims, Fact Check, search queries. All stored in report node."""
import logging
from typing import Any

from app.graph_state import broadcast_graph_update, get_node, update_node
from app.services import ai, factcheck

logger = logging.getLogger(__name__)

# Map fact-check ratings to confidence contribution (0-1)
_RATING_SCORE = {"true": 1.0, "verified": 0.95, "correct": 0.9, "mostly true": 0.8, "half true": 0.5, "unproven": 0.3, "false": 0.1, "fake": 0.0, "debunked": 0.0}


def _confidence_from_fact_checks(fact_checks: list[dict[str, Any]]) -> float:
    """Compute confidence (0-1) from fact check ratings."""
    if not fact_checks:
        return 0.5
    scores = []
    for fc in fact_checks:
        rating = (fc.get("rating") or "").lower()
        s = _RATING_SCORE.get(rating, 0.5)
        for k, v in _RATING_SCORE.items():
            if k in rating:
                s = v
                break
        scores.append(s)
    return sum(scores) / len(scores) if scores else 0.5


async def run_network(
    case_id: str,
    report_node_id: str,
    report_text: str,
    location: Any = None,
    timestamp: str = "",
    llm_provider: str = "default",
) -> None:
    """
    Extract claims, fact-check, generate search queries. Store all in report node data.
    No separate fact_check or external_source nodes. Confidence derived from fact check ratings.
    """
    extracted = await ai.extract_claims(
        report_text,
        case_id=case_id,
        location=location,
        timestamp=timestamp,
        llm_provider=llm_provider
    )
    claims = extracted.get("claims", [])
    urgency = extracted.get("urgency", 0.5)
    misinformation_flags = extracted.get("misinformation_flags", [])
    suggested_verifications = extracted.get("suggested_verifications", [])

    report_node = get_node(report_node_id)
    if not report_node:
        return

    fact_checks: list[dict[str, Any]] = []
    for claim in claims:
        statement = claim.get("statement", "")
        if not statement:
            continue
        fc_results = await factcheck.search_claims(statement)
        for fc in fc_results[:3]:
            claim_text = fc.get("text", "") or statement
            rating = (fc.get("claimReview", [{}])[0] if fc.get("claimReview") else {}).get("textualRating", "unknown")
            reviewer = (fc.get("claimReview", [{}])[0] if fc.get("claimReview") else {}).get("publisher", {}).get("name", "unknown")
            url = (fc.get("claimReview", [{}])[0] if fc.get("claimReview") else {}).get("url", "")
            fact_checks.append({
                "claim_text": claim_text[:300],
                "rating": rating,
                "reviewer": reviewer,
                "url": url,
            })

    queries = await ai.generate_search_queries(claims, llm_provider=llm_provider)
    search_queries = [{"query": q, "platform": "web", "status": "pending"} for q in queries]

    fc_confidence = _confidence_from_fact_checks(fact_checks)
    existing = report_node.data.get("confidence")
    confidence = fc_confidence if existing is None else (float(existing) + fc_confidence) / 2.0

    update_node(report_node_id, {
        "claims": claims,
        "urgency": urgency,
        "misinformation_flags": misinformation_flags,
        "suggested_verifications": suggested_verifications,
        "fact_checks": fact_checks,
        "fact_check_results": fact_checks,
        "search_queries": search_queries,
        "debunk_count": sum(1 for fc in fact_checks if "false" in (fc.get("rating") or "").lower() or "debunk" in (fc.get("rating") or "").lower()),
        "confidence": min(1.0, max(0.0, confidence)),
    })
    updated = get_node(report_node_id)
    if updated:
        await broadcast_graph_update("update_node", updated.model_dump(mode="json"))
