"""Cypher query repository for Neo4j Case and Evidence."""
import logging
import math
from typing import Any

from neo4j import Session as Neo4jSession

logger = logging.getLogger(__name__)


def create_case(
    session: Neo4jSession,
    case_id: str,
    title: str = "",
    description: str = "",
) -> dict[str, Any] | None:
    """
    Create or update a Case node in Neo4j.
    MERGE ensures idempotency; SET updates title, description, created_at.
    """
    query = """
    MERGE (c:Case {id: $case_id})
    SET c.title = $title, c.description = $description, c.created_at = datetime()
    RETURN c
    """
    try:
        result = session.run(
            query,
            case_id=case_id,
            title=title or "",
            description=description or "",
        )
        record = result.single()
        if record and record["c"]:
            node = record["c"]
            return {
                "id": node["id"],
                "title": node.get("title", ""),
                "description": node.get("description", ""),
                "created_at": str(node["created_at"]) if node.get("created_at") else None,
            }
    except Exception as e:
        logger.exception("create_case failed: %s", e)
    return None


def add_evidence(
    session: Neo4jSession,
    case_id: str,
    evidence_data: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Create an Evidence node and link it to the Case via CONTAINS.
    evidence_data: id, type (e.g. 'photo', 'text'), content, url (optional), timestamp (optional).
    """
    eid = evidence_data.get("id", "")
    etype = evidence_data.get("type", "text")
    content = evidence_data.get("content", "") or evidence_data.get("url", "")
    url = evidence_data.get("url", "")
    timestamp = evidence_data.get("timestamp")
    if timestamp is not None and not isinstance(timestamp, str):
        timestamp = str(timestamp)

    if not eid:
        logger.warning("add_evidence: missing id in evidence_data")
        return None

    query = """
    MATCH (c:Case {id: $case_id})
    CREATE (e:Evidence:Node {
        id: $id,
        type: $type,
        content: $content,
        url: $url,
        timestamp: $timestamp
    })
    CREATE (c)-[:CONTAINS]->(e)
    RETURN e
    """
    try:
        result = session.run(
            query,
            case_id=case_id,
            id=eid,
            type=etype,
            content=content[:10000] if isinstance(content, str) else str(content)[:10000],
            url=url or "",
            timestamp=timestamp,
        )
        record = result.single()
        if record and record["e"]:
            node = record["e"]
            return {
                "id": node["id"],
                "type": node.get("type", ""),
                "content": node.get("content", ""),
                "url": node.get("url", ""),
                "timestamp": str(node["timestamp"]) if node.get("timestamp") else None,
            }
    except Exception as e:
        logger.exception("add_evidence failed: %s", e)
    return None


def create_link(
    session: Neo4jSession,
    case_id: str,
    edge_data: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Create a RELATED edge between two Node nodes (Red String — manual link).
    Returns source, target, relation data for event emission.
    """
    source_id = edge_data.get("source_id", "")
    target_id = edge_data.get("target_id", "")
    rel_type = edge_data.get("type", "SUSPECTED_LINK")
    note = edge_data.get("note") or ""

    if not source_id or not target_id:
        logger.warning("create_link: missing source_id or target_id")
        return None

    query = """
    MATCH (a:Node {id: $source_id}), (b:Node {id: $target_id})
    MERGE (a)-[r:RELATED {type: $type}]->(b)
    SET r.created_at = datetime(), r.note = $note, r.manual = true
    RETURN a, b, r
    """
    try:
        result = session.run(
            query,
            source_id=source_id,
            target_id=target_id,
            type=rel_type,
            note=note,
        )
        record = result.single()
        if record and record["a"] and record["b"] and record["r"]:
            a, b, r = record["a"], record["b"], record["r"]
            return {
                "source": {
                    "id": a["id"],
                    "labels": list(a.labels) if hasattr(a, "labels") else [],
                },
                "target": {
                    "id": b["id"],
                    "labels": list(b.labels) if hasattr(b, "labels") else [],
                },
                "relation": {
                    "type": r.get("type", rel_type),
                    "note": r.get("note"),
                    "created_at": str(r["created_at"]) if r.get("created_at") else None,
                    "manual": r.get("manual", True),
                },
                "source_id": source_id,
                "target_id": target_id,
                "type": rel_type,
                "note": note or None,
            }
    except Exception as e:
        logger.exception("create_link failed: %s", e)
    return None


def get_case_graph(session: Neo4jSession, case_id: str) -> dict[str, Any] | None:
    """
    Fetch full case graph from Neo4j. Returns React Flow format:
    { nodes: [{ id, position: {x,y}, data: { label, type, ... } }], edges: [{ id, source, target, type, ... }] }
    """
    query = """
    MATCH (c:Case {id: $case_id})-[:CONTAINS]->(n)
    OPTIONAL MATCH (n)-[r]-(m)
    WHERE (c)-[:CONTAINS]->(m) OR m:Inference
    RETURN collect(DISTINCT n) AS nodes, collect(DISTINCT r) AS edges, collect(DISTINCT m) AS inferences
    """
    try:
        result = session.run(query, case_id=case_id)
        record = result.single()
        if not record:
            return {"nodes": [], "edges": []}

        raw_nodes = record["nodes"] or []
        raw_edges = record["edges"] or []
        raw_inferences = record["inferences"] or []

        # Merge nodes and inferences, dedupe by id, filter nulls
        seen_ids: set[str] = set()
        all_raw: list[Any] = []
        for node in raw_nodes + raw_inferences:
            if node is not None and hasattr(node, "get") and node.get("id"):
                nid = str(node["id"])
                if nid not in seen_ids:
                    seen_ids.add(nid)
                    all_raw.append(node)

        # Build node id -> index for layout
        node_list = list(all_raw)
        if not node_list and not raw_edges:
            return {"nodes": [], "edges": []}

        # Simple circular layout for React Flow
        n_nodes = len(node_list)
        nodes_flow: list[dict[str, Any]] = []
        for i, node in enumerate(node_list):
            nid = str(node["id"])
            angle = 2 * math.pi * i / max(n_nodes, 1)
            x = 250 + 200 * math.cos(angle)
            y = 250 + 200 * math.sin(angle)

            # Build data from node properties
            data: dict[str, Any] = {"label": nid}
            labels = list(node.labels) if hasattr(node, "labels") else []
            if labels:
                data["nodeType"] = labels[0].lower()
            for key in ("type", "content", "url", "timestamp"):
                if node.get(key) is not None:
                    val = node[key]
                    data[key] = str(val) if val is not None else None

            nodes_flow.append({
                "id": nid,
                "position": {"x": round(x, 2), "y": round(y, 2)},
                "data": data,
            })

        # Build edges for React Flow
        seen_edge_ids: set[str] = set()
        edges_flow: list[dict[str, Any]] = []
        for i, rel in enumerate(raw_edges):
            if rel is None:
                continue
            try:
                start_node = rel.start_node if hasattr(rel, "start_node") else None
                end_node = rel.end_node if hasattr(rel, "end_node") else None
                if not start_node or not end_node:
                    continue
                sid = str(start_node["id"]) if start_node.get("id") else None
                tid = str(end_node["id"]) if end_node.get("id") else None
                if not sid or not tid or sid not in seen_ids or tid not in seen_ids:
                    continue
                eid = getattr(rel, "element_id", None) or f"e-{sid}-{tid}-{i}"
                if eid in seen_edge_ids:
                    continue
                seen_edge_ids.add(eid)

                edge_obj: dict[str, Any] = {
                    "id": eid[:80],
                    "source": sid,
                    "target": tid,
                    "type": getattr(rel, "type", "RELATED"),
                }
                if rel.get("note"):
                    edge_obj["data"] = {"note": rel.get("note")}
                edges_flow.append(edge_obj)
            except Exception as e:
                logger.warning("Skipping edge: %s", e)

        return {"nodes": nodes_flow, "edges": edges_flow}
    except Exception as e:
        logger.exception("get_case_graph failed: %s", e)
    return None
