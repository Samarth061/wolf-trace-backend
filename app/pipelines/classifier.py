"""Knowledge Source: Node role classifier — Originator, Amplifier, Mutator, Unwitting Sharer."""
import logging
from datetime import datetime
from typing import Any

from app.graph_state import (
    broadcast_graph_update,
    get_edges_for_node,
    get_node,
    get_nodes_by_type,
    update_node,
)
from app.models.graph import EdgeType, NodeSemanticRole, NodeType

logger = logging.getLogger(__name__)


async def run_classifier(payload: dict[str, Any]) -> None:
    """
    Assign semantic roles to report nodes:
    - Earliest timestamp → Originator
    - Connected via REPOST_OF → Amplifier
    - Connected via MUTATION_OF → Mutator
    - Report with no outgoing edges to external sources → Unwitting Sharer
    """
    case_id = payload.get("case_id")
    if not case_id:
        return
    report_nodes = get_nodes_by_type(case_id, NodeType.REPORT)
    if not report_nodes:
        return
    for node in report_nodes:
        role, confidence = _classify_node(node, report_nodes)
        if role:
            update_node(node.id, {
                "semantic_role": role.value,
                "role_confidence": confidence,
            })
            updated = get_node(node.id)
            if updated:
                await broadcast_graph_update("update_node", updated.model_dump(mode="json"))


def _classify_node(node: Any, all_reports: list[Any]) -> tuple[NodeSemanticRole | None, float]:
    """Classify node role with confidence score (0.0-1.0)."""
    outgoing = get_edges_for_node(node.id)
    has_repost_out = any(e.edge_type == EdgeType.REPOST_OF for e in outgoing)
    has_mutation_out = any(e.edge_type == EdgeType.MUTATION_OF for e in outgoing)
    has_debunked_out = any(e.edge_type == EdgeType.DEBUNKED_BY for e in outgoing)
    has_similar_out = any(e.edge_type == EdgeType.SIMILAR_TO for e in outgoing)

    # High confidence roles based on explicit edge types
    if has_mutation_out:
        return NodeSemanticRole.MUTATOR, 0.95
    if has_repost_out:
        return NodeSemanticRole.AMPLIFIER, 0.95

    # Check if this is the earliest timestamp (Originator)
    ts = _get_timestamp(node)
    if ts and all(_get_timestamp(r) and _get_timestamp(r) >= ts for r in all_reports if r.id != node.id):
        return NodeSemanticRole.ORIGINATOR, 0.90

    # Unwitting Sharer: no external sources linked
    has_external_out = any(
        get_node(e.target_id) and get_node(e.target_id).node_type in (NodeType.EXTERNAL_SOURCE, NodeType.FACT_CHECK)
        for e in outgoing
    )
    if not has_external_out and not has_similar_out:
        return NodeSemanticRole.UNWITTING_SHARER, 0.70

    # Fallback: earliest node is Originator
    earliest = min(all_reports, key=lambda n: _get_timestamp(n) or datetime.max)
    if node.id == earliest.id:
        return NodeSemanticRole.ORIGINATOR, 0.80

    return None, 0.0


def _get_timestamp(node: Any) -> datetime | None:
    ts = node.data.get("timestamp") or node.data.get("created_at")
    if not ts:
        return None
    if isinstance(ts, str):
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            return None
    return ts
