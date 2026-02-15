"""Cases router: GET/POST /api/cases, GET/POST /api/cases/{case_id}, evidence, edges."""
import logging
from typing import Any
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from neo4j import Session as Neo4jSession

from app.config import settings
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
    request: Request,
    session: Neo4jSession | None = Depends(GraphDatabase.get_optional_session),
):
    """Upload raw evidence; saves to Neo4j if available, adds to in-memory graph, returns GraphNode shape."""
    # Auto-generate unique ID if not provided
    import uuid
    if not body.id:
        body.id = f"ev-{int(datetime.utcnow().timestamp() * 1000)}-{uuid.uuid4().hex[:6]}"

    # Extract LLM provider preference from header
    llm_provider = request.headers.get("X-LLM-Provider", "default")

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
        "confidence": 0.7,  # Default 70% for investigator-submitted evidence
        "semantic_role": "evidence",  # Will be updated by Classifier pipeline
        "role_confidence": 0.5,
        "llm_provider": llm_provider,  # NEW: Pass LLM preference to pipelines
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

    # NEW: Read LLM provider preference from node data
    llm_provider = node.data.get("llm_provider", "default")
    logger.info(f"Forensics using LLM provider: {llm_provider}")

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
    using_fallback = False

    if _is_image(media_url):
        logger.info(f"Analyzing image forensics for {evidence_id}")
        forensic_results = await backboard_client.analyze_image_forensics(
            media_url,
            evidence_context,
            llm_provider=llm_provider
        )
        forensic_results["media_type"] = "image"
        # Check if fallback scores were used (ml_accuracy == 0 from fallback)
        using_fallback = (forensic_results.get("ml_accuracy", 0) == 0.0)

    elif _is_video(media_url):
        logger.info(f"Analyzing video forensics for {evidence_id}")
        forensic_results = await twelvelabs.detect_deepfake(media_url, evidence_context)
        forensic_results["media_type"] = "video"
        # TwelveLabs fallback has ml_accuracy: 0.0
        using_fallback = (forensic_results.get("ml_accuracy", 0) == 0.0)

    else:
        raise HTTPException(status_code=400, detail="Unsupported media type (must be image or video)")

    # Add metadata
    forensic_results["analyzed_at"] = datetime.utcnow().isoformat()
    forensic_results["media_url"] = media_url
    forensic_results["status"] = "fallback" if using_fallback else "success"
    forensic_results["analysis_method"] = "backboard" if _is_image(media_url) else "twelvelabs"
    
    # Add 'indicators' as alias for 'manipulation_indicators' for frontend compatibility
    if "manipulation_indicators" in forensic_results and "indicators" not in forensic_results:
        forensic_results["indicators"] = forensic_results["manipulation_indicators"]
    
    # Determine authenticity from forensic scores
    authenticity = _determine_authenticity(forensic_results)
    
    # Extract key points from media and forensic analysis
    key_points = await _extract_media_key_points(
        media_url,
        forensic_results.get("media_type", "image"),
        forensic_results,
        evidence_context,
        llm_provider=llm_provider  # NEW: Pass LLM provider
    )
    
    # Calculate confidence score (ml_accuracy as 0-1 score)
    ml_accuracy = forensic_results.get("ml_accuracy", 0.0)
    if ml_accuracy > 1.0:
        # ml_accuracy in 0-100 range, normalize to 0-1
        confidence = ml_accuracy / 100.0
    else:
        # Already in 0-1 range
        confidence = ml_accuracy

    # Fallback to authenticity_score if ml_accuracy is 0
    if confidence == 0.0:
        authenticity_score = forensic_results.get("authenticity_score", 0.0)
        confidence = authenticity_score / 100.0 if authenticity_score > 0 else 0.5

    # Store forensics, authenticity, key_points, and confidence in node data
    update_node(evidence_id, {
        "forensics": forensic_results,
        "authenticity": authenticity,
        "key_points": key_points,
        "confidence": confidence,
    })

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


def _determine_authenticity(forensic_results: dict[str, Any]) -> str:
    """Determine evidence authenticity based on forensic scores."""
    auth_score = forensic_results.get("authenticity_score", 75)
    deepfake_prob = forensic_results.get("deepfake_probability", 0)
    manipulation_prob = forensic_results.get("manipulation_probability", 0)
    
    # High confidence authentic
    if auth_score >= 85 and deepfake_prob < 10 and manipulation_prob < 15:
        return "verified"
    
    # High suspicion
    elif auth_score < 60 or deepfake_prob > 30 or manipulation_prob > 40:
        return "suspicious"
    
    # Default to unknown (needs review)
    else:
        return "unknown"


async def _extract_media_key_points(
    media_url: str,
    media_type: str,
    forensic_results: dict[str, Any],
    evidence_context: dict[str, Any],
    llm_provider: str = "default"  # NEW: LLM provider for text processing
) -> list[str]:
    """Extract key points from media based on forensic analysis and AI description."""
    from app.services import backboard_client, twelvelabs, ai
    
    key_points = []
    
    # Add forensic findings as key points
    indicators = forensic_results.get("manipulation_indicators", [])
    if indicators:
        for indicator in indicators[:3]:  # Top 3
            if "API unavailable" not in indicator and "manual review" not in indicator:
                key_points.append(f"Forensic finding: {indicator}")
    
    # Add authenticity insight
    auth_score = forensic_results.get("authenticity_score", 0)
    if auth_score >= 85:
        key_points.append(f"High authenticity score ({auth_score:.1f}%)")
    elif auth_score < 60:
        key_points.append(f"Low authenticity score ({auth_score:.1f}%) - requires review")
    
    # For images: Get AI description and extract claims using configured LLM
    if media_type == "image":
        try:
            description = await backboard_client.describe_image(media_url, evidence_context)
            if description:
                # Route claim extraction based on provider preference
                logger.info(f"Processing image description with LLM provider: {llm_provider}")
                claims_result = await ai.extract_claims(
                    description,
                    llm_provider=llm_provider
                )

                # Extract key points from claims
                claims = claims_result.get("claims", [])
                for claim in claims[:3]:  # Top 3 claims
                    statement = claim.get("statement", "")
                    if statement:
                        key_points.append(f"Visual claim: {statement}")

                # If no claims extracted, fallback to raw description
                if not claims:
                    key_points.append(f"Visual content: {description}")
        except Exception as e:
            logger.warning(f"Failed to get image description: {e}")
    
    # For videos: Get summary
    elif media_type == "video":
        try:
            summary = await twelvelabs.summarize_video(media_url)
            if summary:
                # Split summary into key points (first 3 sentences)
                sentences = [s.strip() for s in summary.split('. ') if s.strip()][:3]
                key_points.extend(sentences)
        except Exception as e:
            logger.warning(f"Failed to get video summary: {e}")
    
    # Add context-based insights
    if evidence_context.get("location"):
        loc = evidence_context["location"]
        if isinstance(loc, dict) and loc.get("building"):
            key_points.append(f"Location: {loc['building']}")
    
    # Limit to 5 key points max
    return key_points[:5]


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
    """Chat with AI about evidence context using Groq (primary) or Backboard (fallback)."""
    from app.graph_state import get_node
    from app.services import backboard_client, groq
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
    context_str = json.dumps(context, indent=2) if context else "No specific evidence selected."
    prompt = f"""You are an evidence analysis assistant for campus safety investigations.

Evidence Context:
{context_str}

User Question: {message}

Provide a clear, factual response based on the evidence context. If analyzing forensics, reference specific metrics. If no evidence is provided, offer general guidance about what to look for."""

    # Primary: Try Groq
    if groq.is_available():
        try:
            client = groq._get_client()
            if client:
                response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": "You are an evidence analysis assistant for campus safety. Provide clear, factual answers based on evidence."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    max_tokens=800,
                )

                ai_response = response.choices[0].message.content.strip()
                logger.info(f"Chat response from GROQ: {len(ai_response)} chars")

                return {
                    "response": ai_response,
                    "sources": evidence_ids,
                }
        except Exception as e:
            logger.warning(f"GROQ chat failed, trying Backboard: {e}")

    # Fallback: Try Backboard
    if backboard_client.is_available():
        try:
            assistants = await backboard_client.get_or_create_assistants()
            if assistants and "claim_analyst" in assistants:
                threads = await backboard_client.create_case_thread(case_id)
                thread_id = threads.get("claim_analyst")

                if thread_id:
                    response = await backboard_client.send_to_agent(
                        "claim_analyst",
                        thread_id,
                        prompt,
                    )

                    if response:
                        return {
                            "response": response,
                            "sources": evidence_ids,
                        }
        except Exception as e:
            logger.warning(f"Backboard chat failed: {e}")

    # Last resort: Helpful error message
    return {
        "response": "AI assistant is currently unavailable. Please ensure GROQ_API_KEY or BACKBOARD_API_KEY is configured in the backend .env file.",
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

    # Prepare timeline data for AI with full context
    timeline_data = []
    for node in timeline:
        timeline_data.append({
            'timestamp': node.data.get("timestamp", "Unknown time"),
            'data': node.data
        })

    # Prepare edge data for AI
    edges_data = []
    for edge in edges:
        edges_data.append({
            'source_id': edge.source_id,
            'target_id': edge.target_id,
            'edge_type': edge.edge_type,
            'data': edge.data
        })

    try:
        # Use AI service to generate narrative
        narrative = await ai_service.generate_case_narrative(timeline_data, edges_data, case_id)

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
    """Parse narrative into sections (Origin, Progression, Current Status)."""
    sections = {}
    current_section = None
    current_text = []

    for line in narrative.split("\n"):
        line = line.strip()

        # Check for section headers (markdown or plain text)
        if "**Origin" in line or line.startswith("Origin:"):
            # Save previous section
            if current_section and current_text:
                sections[current_section] = " ".join(current_text)
            current_section = "origin"
            # Extract text after header if any
            text = line.split(":", 1)[-1].strip().replace("**", "")
            current_text = [text] if text else []

        elif "**Progression" in line or line.startswith("Progression:"):
            if current_section and current_text:
                sections[current_section] = " ".join(current_text)
            current_section = "progression"
            text = line.split(":", 1)[-1].strip().replace("**", "")
            current_text = [text] if text else []

        elif "**Current Status" in line or "**Status" in line or line.startswith("Current Status:") or line.startswith("Status:"):
            if current_section and current_text:
                sections[current_section] = " ".join(current_text)
            current_section = "current_status"
            text = line.split(":", 1)[-1].strip().replace("**", "")
            current_text = [text] if text else []

        elif line and current_section:
            # Add content to current section
            current_text.append(line)

    # Save final section
    if current_section and current_text:
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


@router.get("/cases/{case_id}/story/audio")
async def get_story_audio(case_id: str):
    """Generate TTS audio for case story narrative."""
    from fastapi.responses import Response
    from app.services import elevenlabs
    from app.graph_state import get_case_snapshot

    # Get story
    story = await get_case_story(case_id)
    if not story or not story.get('narrative'):
        raise HTTPException(status_code=404, detail="Story not available")

    # Build audio text
    case_snapshot = get_case_snapshot(case_id)
    case_label = case_snapshot.get('label', case_id) if case_snapshot else case_id
    audio_text = f"Case {case_label}. {story['narrative']}"

    # Truncate to ElevenLabs limit (5000 chars)
    if len(audio_text) > 5000:
        audio_text = audio_text[:4997] + "..."

    # Generate TTS
    audio_bytes = await elevenlabs.text_to_speech(audio_text)

    if not audio_bytes:
        # Check if ElevenLabs is configured
        if not settings.elevenlabs_api_key or not settings.elevenlabs_voice_id:
            raise HTTPException(
                status_code=501,
                detail="Text-to-speech not configured. Please add ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID to .env file."
            )
        else:
            raise HTTPException(
                status_code=503,
                detail="TTS service temporarily unavailable"
            )

    return Response(
        content=audio_bytes,
        media_type="audio/mpeg",
        headers={
            "Content-Disposition": f'inline; filename="{case_id}-story.mp3"',
            "Cache-Control": "public, max-age=3600"
        }
    )
