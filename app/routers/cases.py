"""Cases router: GET/POST /api/cases, GET/POST /api/cases/{case_id}, evidence, edges."""
import logging

from fastapi import APIRouter, Depends, HTTPException
from neo4j import Session as Neo4jSession

from app.event_bus import emit
from app.graph_state import get_all_cases, get_case_snapshot, create_and_add_node, create_and_add_edge, broadcast_graph_update
from app.models.case import CaseCreate, CaseOut, EdgeCreate, EdgeOut, EvidenceCreate, EvidenceOut
from app.models.graph import NodeType, EdgeType
from app.services.graph_db import GraphDatabase
from app.services import graph_queries

router = APIRouter(prefix="/api", tags=["cases"])
logger = logging.getLogger(__name__)


@router.get("/cases")
async def list_cases():
    """List all cases with counts (from in-memory graph)."""
    return get_all_cases()


@router.post("/cases", response_model=CaseOut)
async def create_case(
    body: CaseCreate,
    session: Neo4jSession | None = Depends(GraphDatabase.get_optional_session),
):
    """Create a new case in Neo4j if available. Returns basic case object if Neo4j not configured."""
    # Try to create in Neo4j if available
    if session is not None:
        try:
            result = graph_queries.create_case(
                session,
                case_id=body.case_id,
                title=body.title,
                description=body.description,
            )
            if result:
                cid = result.get("id", body.case_id)
                return CaseOut(
                    id=cid,
                    case_id=cid,
                    title=result.get("title", body.title),
                    description=result.get("description", body.description),
                    label=body.title or cid,
                    status="active",
                    node_count=0,
                    updated_at=result.get("created_at"),
                    created_at=result.get("created_at"),
                )
        except Exception as e:
            logger.warning(f"Failed to create case in Neo4j: {e}")

    # Fallback: return basic case object (Neo4j not available or failed)
    from datetime import datetime
    return CaseOut(
        id=body.case_id,
        case_id=body.case_id,
        title=body.title,
        description=body.description,
        label=body.title or body.case_id,
        status="active",
        node_count=0,
        created_at=datetime.utcnow().isoformat(),
    )


@router.get("/cases/{case_id}/graph")
async def get_case_graph(
    case_id: str,
    session: Neo4jSession = Depends(GraphDatabase.get_session),
):
    """Fetch entire case graph from Neo4j, formatted for React Flow (nodes, edges)."""
    result = graph_queries.get_case_graph(session, case_id)
    if result is None:
        raise HTTPException(status_code=500, detail="Failed to fetch graph from Neo4j")
    if not result.get("nodes") and not result.get("edges"):
        # Case may exist but have no contained nodes
        return {"nodes": [], "edges": [], "case_id": case_id}
    return {"nodes": result["nodes"], "edges": result["edges"], "case_id": case_id}


@router.get("/cases/{case_id}")
async def get_case(case_id: str):
    """Full graph snapshot for a case (from in-memory graph)."""
    snapshot = get_case_snapshot(case_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Case not found")
    return snapshot


@router.post("/cases/{case_id}/evidence")
async def add_evidence(
    case_id: str,
    body: EvidenceCreate,
    session: Neo4jSession | None = Depends(GraphDatabase.get_optional_session),
):
    """Upload raw evidence; saves to Neo4j if available, adds to in-memory graph, returns GraphNode shape."""
    evidence_data = {
        "id": body.id,
        "type": body.type,
        "content": body.content,
        "url": body.url,
        "timestamp": body.timestamp,
    }
    # Try Neo4j first (only if configured)
    if session is not None:
        try:
            graph_queries.add_evidence(session, case_id, evidence_data)
            logger.debug(f"Evidence saved to Neo4j: {body.id}")
        except Exception as e:
            logger.warning(f"Failed to save evidence to Neo4j: {e}")

    # Map evidence type string to NodeType
    type_map = {"text": NodeType.REPORT, "image": NodeType.REPORT, "video": NodeType.REPORT}
    node_type = type_map.get(body.type, NodeType.REPORT)

    # Add to in-memory graph state as a GraphNode
    node_data = {
        "text_body": body.content,
        "media_url": body.url or "",
        "timestamp": body.timestamp or "",
        "reviewed": False,
    }
    node = create_and_add_node(node_type, case_id, node_data, node_id=body.id)
    await broadcast_graph_update("add_node", node.model_dump(mode="json"))

    # Return in GraphNode shape so frontend's mapBackendEvidence works
    return node.model_dump(mode="json")


@router.post("/cases/{case_id}/edges")
async def create_edge(
    case_id: str,
    body: EdgeCreate,
    session: Neo4jSession | None = Depends(GraphDatabase.get_optional_session),
):
    """Red String: link two nodes. Creates RELATED edge, emits edge:created for AI analysis."""
    edge_data = {
        "source_id": body.source_id,
        "target_id": body.target_id,
        "type": body.type,
        "note": body.note,
    }
    # Try Neo4j first (only if configured)
    if session is not None:
        try:
            result = graph_queries.create_link(session, case_id, edge_data)
            logger.debug(f"Edge saved to Neo4j: {body.source_id} -> {body.target_id}")
        except Exception as e:
            logger.warning(f"Failed to save edge to Neo4j: {e}")

    # Map edge type string to EdgeType
    type_lower = (body.type or "related").lower()
    edge_type_map = {
        "supports": EdgeType.SIMILAR_TO,
        "contradicts": EdgeType.DEBUNKED_BY,
        "related": EdgeType.SIMILAR_TO,
        "suspected_link": EdgeType.SIMILAR_TO,
    }
    edge_type = edge_type_map.get(type_lower, EdgeType.SIMILAR_TO)

    # Add to in-memory graph state
    edge = create_and_add_edge(edge_type, body.source_id, body.target_id, case_id, {"note": body.note or ""})
    await broadcast_graph_update("add_edge", edge.model_dump(mode="json"))

    # Emit event for AI analysis trigger
    await emit("edge:created", {
        "case_id": case_id,
        "source": body.source_id,
        "target": body.target_id,
        "relation": edge_type.value,
    })

    # Return in GraphEdge shape so frontend's mapBackendEdge works
    return edge.model_dump(mode="json")
