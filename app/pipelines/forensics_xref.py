"""Knowledge Source: Cross-reference forensics when report has claims — TwelveLabs search."""
import logging
from typing import Any

from app.graph_state import broadcast_graph_update, create_and_add_edge, create_and_add_node, get_node
from app.models.graph import EdgeType, NodeType
from app.services import twelvelabs

logger = logging.getLogger(__name__)


async def run_forensics_xref(payload: dict[str, Any]) -> None:
    """When report node has claims, search TwelveLabs for claim-specific video content."""
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
    for claim in claims[:2]:
        statement = claim.get("statement", "")
        if not statement:
            continue
        results = await twelvelabs.search_videos(statement)
        for r in results[:2]:
            ext_data = {
                "search_query": statement[:200],
                "platform": "twelvelabs",
                "url": r.get("url", ""),
                "status": "found",
                "source": "forensics_xref",
            }
            ext_node = create_and_add_node(NodeType.EXTERNAL_SOURCE, case_id, ext_data)
            await broadcast_graph_update("add_node", ext_node.model_dump(mode="json"))
            edge = create_and_add_edge(
                EdgeType.SIMILAR_TO,
                node_id,
                ext_node.id,
                case_id,
                {"confidence": 0.6},
            )
            await broadcast_graph_update("add_edge", edge.model_dump(mode="json"))
