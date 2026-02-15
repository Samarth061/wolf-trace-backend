"""Knowledge Source: Cross-reference forensics when report has claims — TwelveLabs search. Stored in report node."""
import logging
from typing import Any

from app.graph_state import broadcast_graph_update, get_node, update_node
from app.models.graph import NodeType
from app.services import twelvelabs

logger = logging.getLogger(__name__)


async def run_forensics_xref(payload: dict[str, Any]) -> None:
    """When report has claims, search TwelveLabs for claim-specific video content. Store in report.data."""
    case_id = payload.get("case_id")
    node_id = payload.get("node_id")
    if not case_id or not node_id:
        return
    node = get_node(node_id)
    if not node or node.node_type != NodeType.REPORT:
        return
    claims = node.data.get("claims", [])
    if not claims:
        return
    video_xref: list[dict[str, Any]] = list(node.data.get("video_xref", []))
    for claim in claims[:2]:
        statement = claim.get("statement", "")
        if not statement:
            continue
        results = await twelvelabs.search_videos(statement)
        for r in results[:2]:
            video_xref.append({
                "search_query": statement[:200],
                "platform": "twelvelabs",
                "url": r.get("url", ""),
                "status": "found",
            })
    update_node(node_id, {"video_xref": video_xref})
    updated = get_node(node_id)
    if updated:
        await broadcast_graph_update("update_node", updated.model_dump(mode="json"))
