"""Pipeline 2: Network Crawler — Backboard/Gemini claims + Fact Check + search queries."""
import logging
from typing import Any

from app.graph_state import (
    broadcast_graph_update,
    create_and_add_edge,
    create_and_add_node,
    get_node,
)
from app.models.graph import EdgeType, NodeType
from app.services import ai, factcheck

logger = logging.getLogger(__name__)


async def run_network(
    case_id: str,
    report_node_id: str,
    report_text: str,
    location: Any = None,
    timestamp: str = "",
) -> None:
    """
    Send report text to Backboard Claim Analyst (or Gemini fallback) for claim extraction.
    Query Fact Check API for each claim -> FactCheck nodes + DEBUNKED_BY edges.
    Generate search queries -> ExternalSource nodes + SIMILAR_TO edges.
    """
    extracted = await ai.extract_claims(report_text, case_id=case_id, location=location, timestamp=timestamp)
    claims = extracted.get("claims", [])
    urgency = extracted.get("urgency", 0.5)
    misinformation_flags = extracted.get("misinformation_flags", [])
    suggested_verifications = extracted.get("suggested_verifications", [])

    # Update report node with extracted data
    report_node = get_node(report_node_id)
    if report_node:
        report_node.data.update({
            "claims": claims,
            "urgency": urgency,
            "misinformation_flags": misinformation_flags,
            "suggested_verifications": suggested_verifications,
        })
        await broadcast_graph_update("update_node", report_node.model_dump(mode="json"))

    # Fact check each claim
    for claim in claims:
        statement = claim.get("statement", "")
        if not statement:
            continue
        fc_results = await factcheck.search_claims(statement)
        for fc in fc_results[:3]:  # Top 3 results
            claim_text = fc.get("text", "") or statement
            rating = (fc.get("claimReview", [{}])[0] if fc.get("claimReview") else {}).get("textualRating", "unknown")
            reviewer = (fc.get("claimReview", [{}])[0] if fc.get("claimReview") else {}).get("publisher", {}).get("name", "unknown")
            url = (fc.get("claimReview", [{}])[0] if fc.get("claimReview") else {}).get("url", "")
            fc_data = {
                "claim_text": claim_text[:300],
                "rating": rating,
                "reviewer": reviewer,
                "url": url,
            }
            fc_node = create_and_add_node(NodeType.FACT_CHECK, case_id, fc_data)
            await broadcast_graph_update("add_node", fc_node.model_dump(mode="json"))
            edge = create_and_add_edge(
                EdgeType.DEBUNKED_BY, report_node_id, fc_node.id, case_id
            )
            await broadcast_graph_update("add_edge", edge.model_dump(mode="json"))

    # Generate search queries and create ExternalSource nodes
    queries = await ai.generate_search_queries(claims)
    for q in queries:
        ext_data: dict[str, Any] = {
            "search_query": q,
            "platform": "web",
            "url": "",
            "status": "pending",
        }
        ext_node = create_and_add_node(NodeType.EXTERNAL_SOURCE, case_id, ext_data)
        await broadcast_graph_update("add_node", ext_node.model_dump(mode="json"))
        edge = create_and_add_edge(
            EdgeType.SIMILAR_TO,
            report_node_id,
            ext_node.id,
            case_id,
            {"confidence": 0.5},
        )
        await broadcast_graph_update("add_edge", edge.model_dump(mode="json"))
