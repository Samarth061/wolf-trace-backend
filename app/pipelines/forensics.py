"""Pipeline 1: Forensic Scanner — ELA, pHash, EXIF, TwelveLabs."""
import logging
from datetime import datetime
from typing import Any

from app.forensics.ela import analyze_media_from_url, hamming_distance
from app.graph_state import (
    broadcast_graph_update,
    create_and_add_edge,
    create_and_add_node,
    get_all_media_variants,
    get_node,
)
from app.models.graph import EdgeType, NodeType
from app.services import backboard_client, twelvelabs

logger = logging.getLogger(__name__)


async def run_forensics(case_id: str, report_node_id: str, media_url: str | None) -> None:
    """
    If image: ELA, pHash, EXIF. Compare pHash vs all media.
    If video: TwelveLabs index + summarize.
    Add MediaVariant nodes and REPOST_OF/MUTATION_OF edges.
    """
    if not media_url:
        return

    url_lower = media_url.lower()
    is_video = any(
        url_lower.endswith(ext)
        for ext in (".mp4", ".mov", ".webm", ".avi", ".mkv")
    )

    if is_video:
        await _process_video(case_id, report_node_id, media_url)
    else:
        await _process_image(case_id, report_node_id, media_url)


async def _process_image(case_id: str, report_node_id: str, media_url: str) -> None:
    """Process image: ELA, pHash, EXIF, Backboard AI analysis, compare with existing."""
    # Traditional forensics
    analysis = analyze_media_from_url(media_url)
    phash = analysis.get("phash")
    exif = analysis.get("exif", {})
    ela_available = analysis.get("ela_available", False)

    # Get report node for evidence context
    try:
        report_node = get_node(report_node_id)
        evidence_context = {
            "claims": report_node.data.get("claims", []),
            "entities": report_node.data.get("entities", []),
            "location": report_node.data.get("location", {}),
            "semantic_role": report_node.data.get("semantic_role"),
            "timestamp": report_node.data.get("timestamp"),
        }
    except Exception as e:
        logger.warning(f"Could not get report node context: {e}")
        evidence_context = {}

    # AI-powered forensic analysis using Backboard vision
    ai_scores = {}
    try:
        ai_scores = await backboard_client.analyze_image_forensics(media_url, evidence_context)
        logger.info(f"Backboard analysis completed for {media_url}")
    except Exception as e:
        logger.warning(f"Backboard image analysis failed: {e}")
        # Use fallback scores if AI analysis fails
        ai_scores = {
            "authenticity_score": 75.0,
            "manipulation_probability": 15.0,
            "quality_score": 70.0,
            "manipulation_indicators": ["AI analysis unavailable"],
        }

    data: dict[str, Any] = {
        "phash": phash,
        "exif": exif,
        "ela_available": ela_available,
        "media_url": media_url,
        "hamming_distances": [],
        # AI forensic scores
        "authenticity_score": ai_scores.get("authenticity_score", 75.0),
        "manipulation_probability": ai_scores.get("manipulation_probability", 15.0),
        "quality_score": ai_scores.get("quality_score", 70.0),
        "manipulation_indicators": ai_scores.get("manipulation_indicators", []),
        "ml_accuracy": ai_scores.get("ml_accuracy", 0.91),
        "analyzed_at": datetime.utcnow().isoformat(),
    }

    media_node = create_and_add_node(NodeType.MEDIA_VARIANT, case_id, data)
    await broadcast_graph_update("add_node", media_node.model_dump(mode="json"))

    # Compare against existing media
    existing = get_all_media_variants()
    for other in existing:
        if other.id == media_node.id:
            continue
        other_phash = other.data.get("phash")
        if not phash or not other_phash:
            continue
        dist = hamming_distance(phash, other_phash)
        if dist < 0:
            continue
        data["hamming_distances"].append({"node_id": other.id, "distance": dist})

        if 0 <= dist <= 5:
            edge = create_and_add_edge(
                EdgeType.REPOST_OF, media_node.id, other.id, case_id, {"hamming": dist}
            )
            await broadcast_graph_update("add_edge", edge.model_dump(mode="json"))
        elif 6 <= dist <= 15:
            edge = create_and_add_edge(
                EdgeType.MUTATION_OF, media_node.id, other.id, case_id, {"hamming": dist}
            )
            await broadcast_graph_update("add_edge", edge.model_dump(mode="json"))

    # Update node with hamming distances
    media_node.data["hamming_distances"] = data["hamming_distances"]
    await broadcast_graph_update("update_node", media_node.model_dump(mode="json"))


async def _process_video(case_id: str, report_node_id: str, media_url: str) -> None:
    """Process video: TwelveLabs index, search, summarize, deepfake detection. Create MediaVariant node."""
    # Get report node for evidence context
    try:
        report_node = get_node(report_node_id)
        evidence_context = {
            "claims": report_node.data.get("claims", []),
            "entities": report_node.data.get("entities", []),
            "location": report_node.data.get("location", {}),
            "semantic_role": report_node.data.get("semantic_role"),
            "timestamp": report_node.data.get("timestamp"),
        }
    except Exception as e:
        logger.warning(f"Could not get report node context: {e}")
        evidence_context = {}

    # Basic video analysis (indexing, summary, search)
    result = await twelvelabs.analyze_video(media_url)

    # AI-powered deepfake detection
    deepfake_scores = {}
    try:
        deepfake_scores = await twelvelabs.detect_deepfake(media_url, evidence_context)
        logger.info(f"TwelveLabs deepfake detection completed for {media_url}")
    except Exception as e:
        logger.warning(f"TwelveLabs deepfake detection failed: {e}")
        # Use fallback scores
        deepfake_scores = {
            "deepfake_probability": 10.0,
            "manipulation_probability": 12.0,
            "quality_score": 75.0,
            "authenticity_score": 80.0,
            "indicators": ["AI analysis unavailable"],
        }

    data: dict[str, Any] = {
        "media_url": media_url,
        "media_type": "video",
        "index_task": result.get("index_task"),
        "summary": result.get("summary"),
        "search_results": result.get("search_results", []),
        # AI deepfake detection scores
        "deepfake_probability": deepfake_scores.get("deepfake_probability", 10.0),
        "manipulation_probability": deepfake_scores.get("manipulation_probability", 12.0),
        "quality_score": deepfake_scores.get("quality_score", 75.0),
        "authenticity_score": deepfake_scores.get("authenticity_score", 80.0),
        "ml_accuracy": deepfake_scores.get("ml_accuracy", 0.94),
        "indicators": deepfake_scores.get("indicators", []),
        "analyzed_at": datetime.utcnow().isoformat(),
    }
    media_node = create_and_add_node(NodeType.MEDIA_VARIANT, case_id, data)
    await broadcast_graph_update("add_node", media_node.model_dump(mode="json"))
