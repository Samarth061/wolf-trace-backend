"""Orchestrator: Register knowledge sources with Blackboard Controller."""
import logging
from typing import Any

from app.pipelines.blackboard_controller import BlackboardController, Priority
from app.pipelines import case_synthesizer, classifier, clustering, forensics, forensics_xref, network, recluster_debunk

logger = logging.getLogger(__name__)

_controller: BlackboardController | None = None


def register_knowledge_sources() -> BlackboardController:
    """Register all knowledge sources with the Blackboard controller."""
    global _controller
    ctrl = BlackboardController()

    async def _clustering_handler(payload: dict[str, Any]) -> None:
        case_id = payload["case_id"]
        report_node_id = payload.get("report_node_id") or payload.get("node_id") or payload.get("id", "")
        report_data = payload.get("report_data") or payload.get("data", {})
        if not report_node_id and payload.get("edge_type"):
            from app.graph_state import get_nodes_by_type
            from app.models.graph import NodeType
            reports = get_nodes_by_type(case_id, NodeType.REPORT)
            if not reports:
                return
            r = reports[0]
            report_node_id = r.id
            report_data = r.data
        await clustering.run_clustering(case_id, report_node_id, report_data)

    async def _forensics_handler(payload: dict[str, Any]) -> None:
        node_id = payload.get("report_node_id") or payload.get("node_id") or payload.get("id", "")
        media_url = payload.get("media_url") or (payload.get("data") or {}).get("media_url")
        await forensics.run_forensics(payload["case_id"], node_id, media_url)

    async def _network_handler(payload: dict[str, Any]) -> None:
        node_id = payload.get("report_node_id") or payload.get("node_id") or payload.get("id", "")
        node_data = payload.get("data", payload)
        await network.run_network(
            payload["case_id"],
            node_id,
            node_data.get("text_body", ""),
            location=node_data.get("location"),
            timestamp=node_data.get("timestamp", ""),
        )

    def _has_media(p: dict[str, Any]) -> bool:
        return bool(p.get("media_url") or (p.get("data") or {}).get("media_url"))

    def _has_claims(p: dict[str, Any]) -> bool:
        return bool((p.get("data") or p).get("claims"))

    ctrl.register(
        name="clustering",
        priority=Priority.CRITICAL,
        trigger_types=["node:report", "edge:repost_of", "edge:mutation_of"],
        handler=_clustering_handler,
        condition=lambda p: p.get("case_id") and (
            p.get("node_type") == "report" or p.get("report_data") or p.get("edge_type")
        ),
        cooldown_seconds=2.0,
    )
    ctrl.register(
        name="forensics",
        priority=Priority.HIGH,
        trigger_types=["node:report"],
        handler=_forensics_handler,
        condition=_has_media,
        cooldown_seconds=2.0,
    )
    ctrl.register(
        name="network",
        priority=Priority.MEDIUM,
        trigger_types=["node:report"],
        handler=_network_handler,
        cooldown_seconds=1.0,
    )
    ctrl.register(
        name="forensics_xref",
        priority=Priority.MEDIUM,
        trigger_types=["update:report"],
        handler=forensics_xref.run_forensics_xref,
        condition=_has_claims,
        cooldown_seconds=3.0,
    )
    ctrl.register(
        name="classifier",
        priority=Priority.LOW,
        trigger_types=[
            "edge:similar_to",
            "edge:repost_of",
            "edge:mutation_of",
            "edge:debunked_by",
            "edge:amplified_by",
            "node:fact_check",
            "node:external_source",
        ],
        handler=classifier.run_classifier,
        cooldown_seconds=2.0,
    )
    ctrl.register(
        name="recluster_debunk",
        priority=Priority.HIGH,
        trigger_types=["edge:debunked_by"],
        handler=recluster_debunk.run_recluster_debunk,
        cooldown_seconds=1.0,
    )
    ctrl.register(
        name="case_synthesizer",
        priority=Priority.BACKGROUND,
        trigger_types=["update:report"],
        handler=case_synthesizer.run_case_synthesizer,
        condition=_has_claims,
        cooldown_seconds=5.0,
    )
    _controller = ctrl
    return ctrl
