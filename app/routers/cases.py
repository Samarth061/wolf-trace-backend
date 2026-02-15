"""Cases router: GET/POST /api/cases, GET/POST /api/cases/{case_id}, evidence, edges."""
import logging
from typing import Any

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


@router.patch("/cases/{case_id}/evidence/{evidence_id}")
async def mark_evidence_reviewed(
    case_id: str,
    evidence_id: str,
    body: dict[str, Any],
    session: Neo4jSession | None = Depends(GraphDatabase.get_optional_session),
):
    """Mark evidence as reviewed by investigator."""
    from app.graph_state import get_node, update_node

    # Update in-memory graph
    node = get_node(evidence_id)
    if not node:
        raise HTTPException(status_code=404, detail="Evidence not found")

    if node.case_id != case_id:
        raise HTTPException(status_code=400, detail="Evidence does not belong to this case")

    # Update reviewed status and confidence
    reviewed = body.get("reviewed", False)
    update_data = {
        "reviewed": reviewed,
        "confidence": 1.0 if reviewed else node.data.get("confidence", 0.0)  # 100% when reviewed
    }
    update_node(evidence_id, update_data)

    # Broadcast update via WebSocket
    node_updated = get_node(evidence_id)
    if node_updated:
        await broadcast_graph_update("update_node", node_updated.model_dump(mode="json"))

    # Optional: Persist to Neo4j if configured
    if session is not None:
        try:
            # TODO: Add Neo4j update query when needed
            logger.debug(f"Neo4j update for reviewed status: {evidence_id}")
        except Exception as e:
            logger.warning(f"Failed to update evidence in Neo4j: {e}")

    return {"id": evidence_id, "reviewed": reviewed, "confidence": update_data["confidence"]}


@router.get("/cases/{case_id}/evidence/{evidence_id}/inference")
async def get_evidence_inference(case_id: str, evidence_id: str):
    """Get AI inference results and reasoning for an evidence node."""
    from app.graph_state import get_node, get_edges_for_node

    # Get the evidence node
    node = get_node(evidence_id)
    if not node:
        raise HTTPException(status_code=404, detail="Evidence not found")

    if node.case_id != case_id:
        raise HTTPException(status_code=400, detail="Evidence does not belong to this case")

    # Get all edges connected to this evidence
    edges = get_edges_for_node(evidence_id)

    inferences = []

    # Build inference results for each connection
    for edge in edges:
        # Determine target node (could be source or target depending on edge direction)
        target_id = edge.target_id if edge.source_id == evidence_id else edge.source_id
        target_node = get_node(target_id)

        if not target_node:
            continue

        # Extract edge metadata
        edge_data = edge.data or {}
        confidence = edge_data.get("confidence", 0.0)
        temporal_score = edge_data.get("temporal_score", 0.0)
        geo_score = edge_data.get("geo_score", 0.0)
        semantic_score = edge_data.get("semantic_score", 0.0)

        # Generate human-readable reasoning
        reasoning = _generate_connection_reasoning(
            edge.edge_type.value,
            temporal_score,
            geo_score,
            semantic_score,
            edge_data
        )

        # Extract target title
        target_data = target_node.data or {}
        target_title = (
            target_data.get("title") or
            target_data.get("text_body", "")[:50] or
            target_node.node_type.value
        )

        inference = {
            "type": edge.edge_type.value,
            "target_id": target_id,
            "target_title": target_title,
            "confidence": confidence,
            "reasoning": reasoning,
            "components": {
                "temporal_score": temporal_score,
                "geo_score": geo_score,
                "semantic_score": semantic_score,
            },
        }
        inferences.append(inference)

    # Get AI analysis from node data
    node_data = node.data or {}
    ai_analysis = node_data.get("ai_analysis", {})

    # Calculate summary statistics
    total_connections = len(inferences)
    total_confidence = sum(inf["confidence"] for inf in inferences)
    avg_confidence = total_confidence / total_connections if total_connections > 0 else 0.0

    # Find strongest connection
    strongest = max(inferences, key=lambda x: x["confidence"]) if inferences else None

    # Count connection types
    connection_types = {}
    for inf in inferences:
        edge_type = inf["type"]
        connection_types[edge_type] = connection_types.get(edge_type, 0) + 1

    return {
        "evidence_id": evidence_id,
        "summary": {
            "total_connections": total_connections,
            "avg_confidence": avg_confidence,
            "strongest_connection": strongest["target_id"] if strongest else None,
            "connection_types": connection_types,
        },
        "inferences": inferences,
        "ai_analysis": ai_analysis,
    }


def _generate_connection_reasoning(
    edge_type: str,
    temporal_score: float,
    geo_score: float,
    semantic_score: float,
    edge_data: dict[str, Any],
) -> str:
    """Generate human-readable reasoning for why connection was made."""
    # Build detailed reasoning with component scores
    parts = []

    # Temporal reasoning
    if temporal_score > 0.8:
        parts.append(f"occurred within minutes (temporal: {int(temporal_score*100)}%)")
    elif temporal_score > 0.6:
        parts.append(f"occurred within hours (temporal: {int(temporal_score*100)}%)")
    elif temporal_score > 0.3:
        parts.append(f"similar time period (temporal: {int(temporal_score*100)}%)")

    # Geographic reasoning
    if geo_score > 0.8:
        parts.append(f"same location (geo: {int(geo_score*100)}%)")
    elif geo_score > 0.5:
        parts.append(f"nearby locations (geo: {int(geo_score*100)}%)")
    elif geo_score > 0.3:
        parts.append(f"same region (geo: {int(geo_score*100)}%)")

    # Semantic reasoning
    if semantic_score > 0.7:
        parts.append(f"highly similar content (semantic: {int(semantic_score*100)}%)")
    elif semantic_score > 0.4:
        parts.append(f"related content (semantic: {int(semantic_score*100)}%)")
    elif semantic_score > 0.2:
        parts.append(f"loosely related (semantic: {int(semantic_score*100)}%)")

    # Edge type specific reasoning
    if edge_type == "similar_to":
        prefix = "Events "
    elif edge_type == "debunked_by":
        return "Fact-check found claims in this evidence to be false. " + ("Events " + ", ".join(parts) if parts else "")
    elif edge_type == "contains":
        prefix = "Evidence contains related information. "
    elif edge_type == "repost_of":
        return "Evidence appears to be a repost of the original content. " + ("Events " + ", ".join(parts) if parts else "")
    elif edge_type == "mutation_of":
        return "Evidence shows signs of content manipulation or alteration. " + ("Events " + ", ".join(parts) if parts else "")
    elif edge_type == "amplified_by":
        prefix = "Evidence amplifies the original information. "
    else:
        prefix = "Events "

    # Manual connections
    if edge_data.get("manual"):
        notes = edge_data.get("notes", "")
        return f"Manually connected by officer{': ' + notes if notes else ''}"

    # Combine reasoning
    if parts:
        return prefix + ", ".join(parts)

    return "Low confidence connection - manual review recommended"


@router.post("/cases/{case_id}/evidence/{evidence_id}/forensics")
async def analyze_forensics(case_id: str, evidence_id: str):
    """Trigger forensic analysis on evidence with media (image or video)."""
    from app.graph_state import get_node, update_node
    from app.services import backboard_client, twelvelabs
    from datetime import datetime

    # Get the evidence node
    node = get_node(evidence_id)
    if not node:
        raise HTTPException(status_code=404, detail="Evidence not found")

    if node.case_id != case_id:
        raise HTTPException(status_code=400, detail="Evidence does not belong to this case")

    # Check if node has media
    media_url = node.data.get("media_url", "")
    if not media_url:
        raise HTTPException(status_code=400, detail="No media attached to this evidence")

    # Build evidence context for AI analysis
    evidence_context = {
        "claims": node.data.get("claims", []),
        "entities": node.data.get("entities", []),
        "location": node.data.get("location", {}),
        "semantic_role": node.data.get("semantic_role"),
        "timestamp": node.data.get("timestamp"),
    }

    # Determine media type and route to appropriate analysis
    forensic_results: dict[str, Any] = {}

    if _is_image(media_url):
        logger.info(f"Analyzing image forensics for {evidence_id}")
        forensic_results = await backboard_client.analyze_image_forensics(media_url, evidence_context)
        forensic_results["media_type"] = "image"

    elif _is_video(media_url):
        logger.info(f"Analyzing video forensics for {evidence_id}")
        forensic_results = await twelvelabs.detect_deepfake(media_url, evidence_context)
        forensic_results["media_type"] = "video"

    else:
        raise HTTPException(status_code=400, detail="Unsupported media type (must be image or video)")

    # Add metadata
    forensic_results["analyzed_at"] = datetime.utcnow().isoformat()
    forensic_results["media_url"] = media_url

    # Store in node.data.forensics
    update_node(evidence_id, {"forensics": forensic_results})

    # Broadcast update via WebSocket
    node_updated = get_node(evidence_id)
    if node_updated:
        await broadcast_graph_update("update_node", node_updated.model_dump(mode="json"))

    logger.info(f"Forensic analysis complete for {evidence_id}: {forensic_results.get('authenticity_score', 'N/A')}")

    return forensic_results


@router.get("/cases/{case_id}/evidence/{evidence_id}/forensics")
async def get_forensic_results(case_id: str, evidence_id: str):
    """Fetch existing forensic analysis results for evidence."""
    from app.graph_state import get_node

    node = get_node(evidence_id)
    if not node:
        raise HTTPException(status_code=404, detail="Evidence not found")

    if node.case_id != case_id:
        raise HTTPException(status_code=400, detail="Evidence does not belong to this case")

    forensics = node.data.get("forensics")
    if not forensics:
        raise HTTPException(status_code=404, detail="No forensic analysis available for this evidence")

    return forensics


def _is_image(file_path: str) -> bool:
    """Check if file is an image based on extension."""
    image_extensions = [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff"]
    return any(file_path.lower().endswith(ext) for ext in image_extensions)


def _is_video(file_path: str) -> bool:
    """Check if file is a video based on extension."""
    video_extensions = [".mp4", ".avi", ".mov", ".wmv", ".flv", ".webm", ".mkv", ".m4v"]
    return any(file_path.lower().endswith(ext) for ext in video_extensions)


@router.delete("/cases/{case_id}/evidence/{evidence_id}")
async def delete_evidence(case_id: str, evidence_id: str):
    """Delete evidence node and cascade to connected edges."""
    from app.graph_state import get_node, delete_node

    # Validate evidence exists and belongs to case
    node = get_node(evidence_id)
    if not node:
        raise HTTPException(status_code=404, detail="Evidence not found")

    if node.case_id != case_id:
        raise HTTPException(status_code=400, detail="Evidence does not belong to this case")

    try:
        # Delete node and connected edges
        result = delete_node(evidence_id)

        # Broadcast deletion via WebSocket
        await broadcast_graph_update("delete_node", {
            "node_id": evidence_id,
            "case_id": case_id,
        })

        logger.info(f"Deleted evidence {evidence_id} and {result['deleted_edges']} connected edges")

        return {
            "status": "deleted",
            "node_id": evidence_id,
            "edges_deleted": result["deleted_edges"],
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/cases/{case_id}/chat")
async def chat_with_evidence(case_id: str, body: dict[str, Any]):
    """Chat with AI about evidence context using Backboard."""
    from app.graph_state import get_node
    from app.services import backboard_client
    import json

    message = body.get("message", "")
    evidence_ids = body.get("evidence_ids", [])

    if not message:
        raise HTTPException(status_code=400, detail="Message is required")

    # Gather evidence context
    context = []
    for eid in evidence_ids:
        node = get_node(eid)
        if node and node.case_id == case_id:
            context.append({
                "id": node.id,
                "content": node.data.get("text_body", ""),
                "claims": node.data.get("claims", []),
                "forensics": node.data.get("forensics", {}),
            })

    # Build prompt with evidence context
    prompt = f"""Evidence Context:\n{json.dumps(context, indent=2)}\n\nUser Question: {message}"""

    # Send to Backboard (use Claim Analyst for general queries)
    assistants = await backboard_client.get_or_create_assistants()

    if not assistants or "claim_analyst" not in assistants:
        raise HTTPException(status_code=503, detail="AI service unavailable")

    # Get or create thread for this case
    threads = await backboard_client.create_case_thread(case_id)
    thread_id = threads.get("claim_analyst")

    if not thread_id:
        raise HTTPException(status_code=500, detail="Failed to create chat thread")

    # Send message and get response
    response = await backboard_client.send_to_agent(
        "claim_analyst",
        thread_id,
        prompt,
    )

    return {
        "response": response or "No response from AI",
        "sources": evidence_ids,
    }


@router.post("/cases/{case_id}/edges")
async def create_edge(
    case_id: str,
    body: EdgeCreate,
    session: Neo4jSession | None = Depends(GraphDatabase.get_optional_session),
):
    """Red String: link two nodes. Creates RELATED edge, emits edge:created for AI analysis."""
    from app.graph_state import get_node

    # Validate that both nodes exist
    source_node = get_node(body.source_id)
    target_node = get_node(body.target_id)

    if not source_node:
        raise HTTPException(status_code=404, detail=f"Source evidence not found: {body.source_id}")
    if not target_node:
        raise HTTPException(status_code=404, detail=f"Target evidence not found: {body.target_id}")

    # Validate nodes belong to this case
    if source_node.case_id != case_id or target_node.case_id != case_id:
        raise HTTPException(status_code=400, detail="Evidence does not belong to this case")

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

    # Add to in-memory graph state with manual flag
    edge = create_and_add_edge(
        edge_type,
        body.source_id,
        body.target_id,
        case_id,
        {
            "note": body.note or "",
            "manual": True,  # Mark as manually created
            "confidence": 1.0,  # Manual connections have 100% confidence
        }
    )
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


@router.get("/cases/{case_id}/story")
async def get_case_story(case_id: str):
    """Generate coherent narrative for the case using AI synthesis."""
    from app.graph_state import get_nodes_for_case, get_edges_for_case
    from app.services import ai as ai_service
    from datetime import datetime

    # Get all nodes for this case
    nodes = get_nodes_for_case(case_id)
    edges = get_edges_for_case(case_id)

    # Filter to report nodes and sort by timestamp
    reports = [n for n in nodes if n.node_type == NodeType.REPORT]
    timeline = sorted(
        reports,
        key=lambda n: n.data.get("timestamp", datetime.now().isoformat())
    )

    if not timeline:
        return {
            "case_id": case_id,
            "narrative": "No evidence has been added to this case yet.",
            "sections": {},
            "key_moments": [],
        }

    # Format timeline for AI
    timeline_text = []
    for i, node in enumerate(timeline, 1):
        timestamp = node.data.get("timestamp", "Unknown time")
        text_body = node.data.get("text_body", "No description")
        title = node.data.get("title", f"Evidence {i}")
        timeline_text.append(f"{i}. [{timestamp}] {title}: {text_body[:200]}")

    # Format connections for AI
    connections_text = []
    for edge in edges:
        source_node = next((n for n in nodes if n.id == edge.source_id), None)
        target_node = next((n for n in nodes if n.id == edge.target_id), None)
        if source_node and target_node:
            source_title = source_node.data.get("title", edge.source_id)
            target_title = target_node.data.get("title", edge.target_id)
            connections_text.append(
                f"- {source_title} → {edge.edge_type.value} → {target_title}"
            )

    # Generate narrative using AI
    story_prompt = f"""Generate a coherent narrative for this investigation case.

Timeline of Events:
{chr(10).join(timeline_text)}

Connections:
{chr(10).join(connections_text[:20])}

Generate a narrative with these sections:
1. **Origin**: How the case started (1-2 sentences)
2. **Progression**: How it evolved over time (2-3 sentences)
3. **Current Status**: Where things stand now (1-2 sentences)

Also identify 2-3 key turning points in the investigation.

Keep the narrative factual, concise, and focused on the evidence timeline."""

    try:
        # Use AI service to generate narrative
        narrative = await ai_service.query_with_context(story_prompt)

        # Extract sections from narrative (simple parsing)
        sections = _parse_narrative_sections(narrative)

        # Identify key moments
        key_moments = _identify_key_moments(timeline, edges)

        return {
            "case_id": case_id,
            "narrative": narrative,
            "sections": sections,
            "key_moments": key_moments,
        }
    except Exception as e:
        logger.error(f"Story generation failed: {e}")
        # Fallback to simple concatenation
        fallback_narrative = f"Case involves {len(timeline)} pieces of evidence collected over time. "
        if edges:
            fallback_narrative += f"Evidence shows {len(edges)} connections between reports. "
        fallback_narrative += "Manual review recommended for complete understanding."

        return {
            "case_id": case_id,
            "narrative": fallback_narrative,
            "sections": {},
            "key_moments": [],
        }


def _parse_narrative_sections(narrative: str) -> dict[str, str]:
    """Parse narrative into sections (simple implementation)."""
    sections = {}
    current_section = None
    current_text = []

    for line in narrative.split("\n"):
        if "**Origin" in line or "Origin:" in line:
            if current_section:
                sections[current_section] = " ".join(current_text)
            current_section = "origin"
            current_text = []
        elif "**Progression" in line or "Progression:" in line:
            if current_section:
                sections[current_section] = " ".join(current_text)
            current_section = "progression"
            current_text = []
        elif "**Current" in line or "Status:" in line:
            if current_section:
                sections[current_section] = " ".join(current_text)
            current_section = "status"
            current_text = []
        elif line.strip() and current_section:
            current_text.append(line.strip())

    if current_section:
        sections[current_section] = " ".join(current_text)

    return sections


def _identify_key_moments(timeline: list, edges: list) -> list[dict[str, str]]:
    """Identify key moments based on evidence with many connections."""
    # Find nodes with the most connections
    connection_counts = {}
    for edge in edges:
        connection_counts[edge.source_id] = connection_counts.get(edge.source_id, 0) + 1
        connection_counts[edge.target_id] = connection_counts.get(edge.target_id, 0) + 1

    # Sort timeline by connection count
    key_nodes = sorted(
        timeline,
        key=lambda n: connection_counts.get(n.id, 0),
        reverse=True
    )[:3]  # Top 3 most connected

    moments = []
    for node in key_nodes:
        title = node.data.get("title", "Evidence")
        description = node.data.get("text_body", "")[:100]
        connection_count = connection_counts.get(node.id, 0)
        moments.append({
            "description": f"{title} - {connection_count} connections",
            "detail": description,
        })

    return moments
