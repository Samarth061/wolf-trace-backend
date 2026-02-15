"""Knowledge Source: Re-evaluate clustering when debunk appears — update report nodes with debunk count."""
import logging
from typing import Any

from app.graph_state import broadcast_graph_update, get_edges_for_case, get_node, update_node
from app.models.graph import EdgeType, NodeType

logger = logging.getLogger(__name__)


async def run_recluster_debunk(payload: dict[str, Any]) -> None:
    """When DEBUNKED_BY edge added, update report nodes with debunk count."""
    case_id = payload.get("case_id")
    if not case_id:
        return
    edges = get_edges_for_case(case_id)
    debunk_count: dict[str, int] = {}
    for e in edges:
        if e.edge_type == EdgeType.DEBUNKED_BY:
            debunk_count[e.source_id] = debunk_count.get(e.source_id, 0) + 1
    for node_id, count in debunk_count.items():
        node = get_node(node_id)
        if node:
            update_node(node_id, {"debunk_count": count})
            updated = get_node(node_id)
            if updated:
                await broadcast_graph_update("update_node", updated.model_dump(mode="json"))
