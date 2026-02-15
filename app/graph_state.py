"""In-memory graph state + WebSocket ConnectionManager."""
import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TYPE_CHECKING

from app.models.graph import EdgeType, GraphEdge, GraphNode, NodeType
from app.utils.ids import generate_edge_id, generate_node_id

if TYPE_CHECKING:
    from app.pipelines.blackboard_controller import BlackboardController

logger = logging.getLogger(__name__)

_controller: "BlackboardController | None" = None
_reports: dict[str, dict[str, Any]] = {}  # case_id -> report data
_nodes: dict[str, GraphNode] = {}
_edges: list[GraphEdge] = []
_adjacency: dict[str, list[str]] = defaultdict(list)  # source_id -> [target_ids]
_case_reports: dict[str, list[str]] = defaultdict(list)  # case_id -> [report_ids]


@dataclass
class ConnectionManager:
    """Manages WebSocket connections for caseboard and alerts."""

    caseboard_connections: set[Any] = field(default_factory=set)
    alert_connections: set[Any] = field(default_factory=set)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def connect_caseboard(self, websocket: Any) -> None:
        async with self._lock:
            self.caseboard_connections.add(websocket)

    async def disconnect_caseboard(self, websocket: Any) -> None:
        async with self._lock:
            self.caseboard_connections.discard(websocket)

    async def connect_alert(self, websocket: Any) -> None:
        async with self._lock:
            self.alert_connections.add(websocket)

    async def disconnect_alert(self, websocket: Any) -> None:
        async with self._lock:
            self.alert_connections.discard(websocket)

    async def broadcast_caseboard(self, message: dict[str, Any]) -> None:
        dead: set[Any] = set()
        async with self._lock:
            conns = set(self.caseboard_connections)
        for ws in conns:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            async with self._lock:
                self.caseboard_connections.discard(ws)

    async def broadcast_alert(self, message: dict[str, Any]) -> None:
        dead: set[Any] = set()
        async with self._lock:
            conns = set(self.alert_connections)
        for ws in conns:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            async with self._lock:
                self.alert_connections.discard(ws)


connection_manager = ConnectionManager()


def add_node(node: GraphNode) -> None:
    _nodes[node.id] = node


def add_edge(edge: GraphEdge) -> None:
    _edges.append(edge)
    _adjacency[edge.source_id].append(edge.target_id)


def update_node(node_id: str, data_updates: dict[str, Any]) -> None:
    if node_id in _nodes:
        _nodes[node_id].data.update(data_updates)


def delete_node(node_id: str) -> dict[str, Any]:
    """Delete node and cascade to connected edges."""
    if node_id not in _nodes:
        raise ValueError(f"Node {node_id} not found")

    # Find all connected edges
    edges_to_delete = [
        e for e in _edges
        if e.source_id == node_id or e.target_id == node_id
    ]

    # Delete edges first
    for edge in edges_to_delete:
        _edges.remove(edge)

    # Remove from adjacency
    _adjacency.pop(node_id, None)
    for neighbors in _adjacency.values():
        if node_id in neighbors:
            neighbors.remove(node_id)

    # Remove from case reports tracking
    for case_id, report_ids in _case_reports.items():
        if node_id in report_ids:
            report_ids.remove(node_id)

    # Delete node
    node = _nodes.pop(node_id)

    return {
        "deleted_node": node_id,
        "deleted_edges": len(edges_to_delete),
        "edge_ids": [e.id for e in edges_to_delete],
    }


def get_node(node_id: str) -> GraphNode | None:
    return _nodes.get(node_id)


def get_nodes_for_case(case_id: str) -> list[GraphNode]:
    return [n for n in _nodes.values() if n.case_id == case_id]


def get_nodes_by_type(case_id: str, node_type: NodeType) -> list[GraphNode]:
    return [n for n in _nodes.values() if n.case_id == case_id and n.node_type == node_type]


def get_external_source_by_query(case_id: str, search_query: str) -> GraphNode | None:
    """Return existing external_source node with same search_query if any."""
    q = (search_query or "")[:500]
    for n in _nodes.values():
        if n.case_id == case_id and n.node_type == NodeType.EXTERNAL_SOURCE:
            if (n.data.get("search_query") or "")[:500] == q:
                return n
    return None


def get_edges_for_node(node_id: str) -> list[GraphEdge]:
    outgoing = [e for e in _edges if e.source_id == node_id]
    incoming = [e for e in _edges if e.target_id == node_id]
    return outgoing + incoming


def get_case_urgency(case_id: str) -> str:
    """Derived from highest urgency across report nodes."""
    reports = get_nodes_by_type(case_id, NodeType.REPORT)
    urgencies = []
    for n in reports:
        u = n.data.get("urgency")
        if u is not None:
            urgencies.append(float(u))
    if not urgencies:
        return "unknown"
    if max(urgencies) >= 0.8:
        return "high"
    if max(urgencies) >= 0.5:
        return "medium"
    return "low"


def set_controller(controller: "BlackboardController | None") -> None:
    global _controller
    _controller = controller


def get_all_media_variants() -> list[GraphNode]:
    """Get all media_variant nodes for pHash comparison (legacy; prefer get_reports_with_phash)."""
    from app.models.graph import NodeType

    return [n for n in _nodes.values() if n.node_type == NodeType.MEDIA_VARIANT]


def get_reports_with_phash(exclude_id: str | None = None) -> list[GraphNode]:
    """Get report nodes that have phash in data (for consolidated forensics pHash comparison)."""
    result = []
    for n in _nodes.values():
        if n.node_type != NodeType.REPORT or n.id == exclude_id:
            continue
        if n.data.get("phash"):
            result.append(n)
    return result


def get_edges_for_case(case_id: str) -> list[GraphEdge]:
    return [e for e in _edges if e.case_id == case_id]


def get_all_cases() -> list[dict[str, Any]]:
    cases: dict[str, dict[str, Any]] = {}
    for report_id, data in _reports.items():
        cid = data.get("case_id")
        if cid:
            if cid not in cases:
                cases[cid] = {
                    "case_id": cid,
                    "report_count": 0,
                    "node_count": 0,
                    "edge_count": 0,
                    "label": cid,
                    "status": "active",
                    "updated_at": None,
                    "summary": "",
                    "location": "Unknown Location",
                    "story": "",
                }
            cases[cid]["report_count"] += 1
    for n in _nodes.values():
        if n.case_id not in cases:
            cases[n.case_id] = {
                "case_id": n.case_id,
                "report_count": 0,
                "node_count": 0,
                "edge_count": 0,
                "label": n.case_id,
                "status": "active",
                "updated_at": None,
                "summary": "",
                "location": "Unknown Location",
                "story": "",
            }
        cases[n.case_id]["node_count"] += 1
        # Track latest updated_at
        node_ts = n.created_at.isoformat() if n.created_at else None
        if node_ts and (cases[n.case_id]["updated_at"] is None or node_ts > cases[n.case_id]["updated_at"]):
            cases[n.case_id]["updated_at"] = node_ts
        # Extract summary/location/story from first report node
        if n.node_type == NodeType.REPORT and not cases[n.case_id]["summary"]:
            text = n.data.get("text_body", "")
            cases[n.case_id]["summary"] = text[:200] + ("..." if len(text) > 200 else "")
            loc = n.data.get("location")
            if isinstance(loc, dict) and loc.get("building"):
                cases[n.case_id]["location"] = loc["building"]
            elif isinstance(loc, str) and loc:
                cases[n.case_id]["location"] = loc
        # Build story from report nodes
        if n.node_type == NodeType.REPORT:
            text = n.data.get("text_body", "")
            if text:
                ts = n.data.get("timestamp", "")
                entry = f"Report ({ts}): {text}" if ts else text
                if cases[n.case_id]["story"]:
                    cases[n.case_id]["story"] += "\n\n" + entry
                else:
                    cases[n.case_id]["story"] = entry
    for e in _edges:
        if e.case_id not in cases:
            cases[e.case_id] = {
                "case_id": e.case_id,
                "report_count": 0,
                "node_count": 0,
                "edge_count": 0,
                "label": e.case_id,
                "status": "active",
                "updated_at": None,
                "summary": "",
                "location": "Unknown Location",
                "story": "",
            }
        cases[e.case_id]["edge_count"] += 1
    # Set default updated_at for cases without timestamps
    now = datetime.utcnow().isoformat()
    for c in cases.values():
        if c["updated_at"] is None:
            c["updated_at"] = now
    # Apply case metadata overrides (from seed data)
    for cid, c in cases.items():
        meta = _case_metadata.get(cid)
        if meta:
            if meta.get("label"):
                c["label"] = meta["label"]
            if meta.get("status"):
                c["status"] = meta["status"]
            if meta.get("location") and c["location"] == "Unknown Location":
                c["location"] = meta["location"]
            if meta.get("summary") and not c["summary"]:
                c["summary"] = meta["summary"]
            if meta.get("story") and not c["story"]:
                c["story"] = meta["story"]
            if meta.get("updated_at"):
                c["updated_at"] = meta["updated_at"]
    return list(cases.values())


def get_all_reports() -> list[dict[str, Any]]:
    """Return all reports for GET /api/reports."""
    return list(_reports.values())


def add_report(case_id: str, report_id: str, report_data: dict[str, Any], report_node_id: str | None = None) -> None:
    """Store report and link to case."""
    report_data["case_id"] = case_id
    report_data["report_id"] = report_id
    if report_node_id:
        report_data["report_node_id"] = report_node_id
    _reports[report_id] = report_data
    _case_reports[case_id].append(report_id)


def get_case_snapshot(case_id: str) -> dict[str, Any] | None:
    nodes = get_nodes_for_case(case_id)
    edges = get_edges_for_case(case_id)
    if not nodes and not edges:
        return None
    # Derive metadata from nodes for frontend mapBackendCase
    updated_at = None
    summary = ""
    location = "Unknown Location"
    story_parts: list[str] = []
    for n in nodes:
        ts = n.created_at.isoformat() if n.created_at else None
        if ts and (updated_at is None or ts > updated_at):
            updated_at = ts
        if n.node_type == NodeType.REPORT:
            text = n.data.get("text_body", "")
            if text and not summary:
                summary = text[:200] + ("..." if len(text) > 200 else "")
            loc = n.data.get("location")
            if not story_parts or location == "Unknown Location":
                if isinstance(loc, dict) and loc.get("building"):
                    location = loc["building"]
                elif isinstance(loc, str) and loc:
                    location = loc
            if text:
                ts_str = n.data.get("timestamp", "")
                entry = f"Report ({ts_str}): {text}" if ts_str else text
                story_parts.append(entry)
    result = {
        "case_id": case_id,
        "label": case_id,
        "status": "active",
        "updated_at": updated_at or datetime.utcnow().isoformat(),
        "summary": summary,
        "location": location,
        "story": "\n\n".join(story_parts),
        "node_count": len(nodes),
        "nodes": [n.model_dump(mode="json") for n in nodes],
        "edges": [e.model_dump(mode="json") for e in edges],
    }
    # Apply case metadata overrides (from seed data)
    meta = _case_metadata.get(case_id)
    if meta:
        if meta.get("label"):
            result["label"] = meta["label"]
        if meta.get("status"):
            result["status"] = meta["status"]
        if meta.get("location") and result["location"] == "Unknown Location":
            result["location"] = meta["location"]
        if meta.get("summary") and not result["summary"]:
            result["summary"] = meta["summary"]
        if meta.get("story") and not result["story"]:
            result["story"] = meta["story"]
        if meta.get("updated_at"):
            result["updated_at"] = meta["updated_at"]
    return result


def get_all_snapshots() -> list[dict[str, Any]]:
    seen: set[str] = set()
    snapshots = []
    for cid in _case_reports:
        if cid in seen:
            continue
        seen.add(cid)
        s = get_case_snapshot(cid)
        if s:
            snapshots.append(s)
    for n in _nodes.values():
        if n.case_id in seen:
            continue
        seen.add(n.case_id)
        s = get_case_snapshot(n.case_id)
        if s:
            snapshots.append(s)
    return snapshots


def _event_type_from_action(action: str, payload: dict[str, Any]) -> str:
    if action == "add_node":
        nt = payload.get("node_type", "")
        return f"node:{nt}"
    if action == "add_edge":
        et = payload.get("edge_type", "")
        return f"edge:{et}"
    if action == "update_node":
        nt = payload.get("node_type", "")
        return f"update:{nt}"
    return action


async def broadcast_graph_update(action: str, payload: dict[str, Any]) -> None:
    msg = {
        "type": "graph_update",
        "action": action,
        "payload": payload,
        "timestamp": datetime.utcnow().isoformat(),
    }
    await connection_manager.broadcast_caseboard(msg)
    if _controller:
        event_type = _event_type_from_action(action, payload)
        try:
            asyncio.create_task(_controller.notify(event_type, payload))
        except Exception as e:
            logger.warning("Controller notify failed: %s", e)


_case_metadata: dict[str, dict[str, Any]] = {}  # case_id -> {label, status, location, summary, story, updated_at}


def set_case_metadata(case_id: str, metadata: dict[str, Any]) -> None:
    """Store extra case metadata (label, status, location, summary, story) for seed data."""
    _case_metadata[case_id] = metadata


def get_case_metadata(case_id: str) -> dict[str, Any] | None:
    return _case_metadata.get(case_id)


def clear_all() -> None:
    """Clear all in-memory state. Used by seed endpoint."""
    _reports.clear()
    _nodes.clear()
    _edges.clear()
    _adjacency.clear()
    _case_reports.clear()
    _case_metadata.clear()


def create_and_add_node(
    node_type: NodeType,
    case_id: str,
    data: dict[str, Any],
    node_id: str | None = None,
) -> GraphNode:
    nid = node_id or generate_node_id(prefix=node_type.value[:1].upper())
    logger.info(f"Creating node {nid} of type {node_type.value} for case {case_id}")
    node = GraphNode(id=nid, node_type=node_type, case_id=case_id, data=data)
    add_node(node)
    logger.info(f"Node {nid} created successfully, will be broadcast")
    return node


def create_and_add_edge(
    edge_type: EdgeType,
    source_id: str,
    target_id: str,
    case_id: str,
    data: dict[str, Any] | None = None,
) -> GraphEdge:
    edge = GraphEdge(
        id=generate_edge_id(),
        edge_type=edge_type,
        source_id=source_id,
        target_id=target_id,
        case_id=case_id,
        data=data or {},
    )
    add_edge(edge)
    return edge
