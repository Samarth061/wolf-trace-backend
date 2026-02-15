"""Knowledge Source: Case Synthesizer — produces structured case summary after analysis."""
import json
import logging
from typing import Any

from app.graph_state import broadcast_graph_update, get_case_snapshot, get_node, get_nodes_by_type, update_node
from app.models.graph import NodeType
from app.services import ai, backboard_client

logger = logging.getLogger(__name__)


async def run_case_synthesizer(payload: dict[str, Any]) -> None:
    """Run Case Synthesizer agent, update report nodes with narrative and confidence."""
    case_id = payload.get("case_id")
    if not case_id:
        return
    if not backboard_client.is_available():
        return
    threads = backboard_client.get_thread_ids(case_id)
    if not threads:
        await backboard_client.create_case_thread(case_id)
        threads = backboard_client.get_thread_ids(case_id)
    snapshot = get_case_snapshot(case_id)
    context_parts = [f"Case {case_id}"]
    if snapshot:
        for n in snapshot.get("nodes", [])[:15]:
            context_parts.append(f"- {n.get('node_type', '')}: {str(n.get('data', {}))[:300]}")
    context = "\n".join(context_parts)
    synthesis = await ai.synthesize_case(case_id, threads, case_context=context)
    if not synthesis:
        return
    snapshot = get_case_snapshot(case_id)
    if not snapshot:
        return
    report_nodes = get_nodes_by_type(case_id, NodeType.REPORT)
    for node in report_nodes:
        update_node(node.id, {
            "case_narrative": synthesis.get("narrative", ""),
            "origin_analysis": synthesis.get("origin_analysis", ""),
            "spread_map": synthesis.get("spread_map", ""),
            "confidence_score": synthesis.get("confidence_assessment", {}).get("score")
            if isinstance(synthesis.get("confidence_assessment"), dict)
            else synthesis.get("confidence_assessment"),
            "recommended_action": synthesis.get("recommended_action", ""),
        })
        updated = get_node(node.id)
        if updated:
            await broadcast_graph_update("update_node", updated.model_dump(mode="json"))
    if synthesis.get("narrative"):
        try:
            await backboard_client.add_memory(
                "claim_analyst",
                f"Case {case_id}: {synthesis.get('narrative', '')[:500]}. "
                f"Origin: {synthesis.get('origin_analysis', '')[:200]}.",
                metadata={"case_id": case_id},
            )
        except Exception as e:
            logger.warning("add_memory for case %s failed: %s", case_id, e)
