"""Pipeline 1: Forensic Scanner — ELA, pHash, EXIF, TwelveLabs. All stored in report node."""
import asyncio
import logging
from datetime import datetime
from typing import Any

from app.forensics.ela import analyze_media_from_url, hamming_distance
from app.graph_state import (
    broadcast_graph_update,
    create_and_add_edge,
    get_node,
    get_reports_with_phash,
    update_node,
)
from app.models.graph import EdgeType, NodeType
from app.services import backboard_client, twelvelabs

logger = logging.getLogger(__name__)


async def _retry_api_call(coro_func, max_retries: int = 3, backoff_base: float = 1.0):
    """Retry an async API call with exponential backoff.
    
    Args:
        coro_func: A coroutine or function that returns a coroutine
        max_retries: Number of retry attempts (default 3)
        backoff_base: Base for exponential backoff in seconds
    
    Returns:
        Result from the coroutine, or None if all retries fail
    """
    for attempt in range(max_retries):
        try:
            if callable(coro_func):
                result = await coro_func()
            else:
                result = await coro_func
            return result
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = backoff_base * (2 ** attempt)
                logger.warning(
                    f"API call failed (attempt {attempt + 1}/{max_retries}). "
                    f"Retrying in {wait_time}s. Error: {e}"
                )
                await asyncio.sleep(wait_time)
            else:
                logger.error(
                    f"API call failed after {max_retries} attempts. "
                    f"Error: {e}"
                )
                return None
    return None


async def run_forensics(
    case_id: str,
    report_node_id: str,
    media_url: str | None,
    llm_provider: str = "default"
) -> None:
    """
    If image: ELA, pHash, EXIF. Compare pHash vs all media.
    If video: TwelveLabs index + summarize.
    Add MediaVariant nodes and REPOST_OF/MUTATION_OF edges.

    Args:
        llm_provider: LLM provider for text processing (groq/default)
    """
    if not media_url:
        return

    url_lower = media_url.lower()
    is_video = any(
        url_lower.endswith(ext)
        for ext in (".mp4", ".mov", ".webm", ".avi", ".mkv")
    )

    if is_video:
        await _process_video(case_id, report_node_id, media_url, llm_provider)
    else:
        await _process_image(case_id, report_node_id, media_url, llm_provider)


async def _process_image(
    case_id: str,
    report_node_id: str,
    media_url: str,
    llm_provider: str = "default"
) -> None:
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

    # AI-powered forensic analysis using GROQ or Backboard vision
    ai_scores = {}
    try:
        # Retry Backboard API call with exponential backoff
        async def call_backboard():
            return await backboard_client.analyze_image_forensics(
                media_url,
                evidence_context,
                llm_provider=llm_provider
            )

        ai_scores = await _retry_api_call(call_backboard, max_retries=3, backoff_base=1.0)
        
        if ai_scores:
            logger.info(f"Backboard analysis completed for {media_url}")
        else:
            logger.warning(f"Backboard analysis failed after retries for {media_url}")
            # Use fallback scores if all retries exhausted
            ai_scores = {
                "authenticity_score": 65.0,
                "manipulation_probability": 25.0,
                "quality_score": 70.0,
                "manipulation_indicators": ["Backboard API unavailable - manual review required"],
                "ml_accuracy": 0.0,
            }
    except Exception as e:
        logger.exception(f"Unexpected error in Backboard analysis: {e}")
        # Use fallback scores if unexpected error
        ai_scores = {
            "authenticity_score": 65.0,
            "manipulation_probability": 25.0,
            "quality_score": 70.0,
            "manipulation_indicators": ["Backboard API unavailable - manual review required"],
            "ml_accuracy": 0.0,
        }

    data: dict[str, Any] = {
        "phash": phash,
        "exif": exif,
        "ela_available": ela_available,
        "media_url": media_url,
        "hamming_distances": [],
        "authenticity_score": ai_scores.get("authenticity_score", 65.0),
        "manipulation_probability": ai_scores.get("manipulation_probability", 25.0),
        "quality_score": ai_scores.get("quality_score", 70.0),
        "manipulation_indicators": ai_scores.get("manipulation_indicators", []),
        "indicators": ai_scores.get("manipulation_indicators", []),
        "ml_accuracy": ai_scores.get("ml_accuracy", 0.0),
        "analyzed_at": datetime.utcnow().isoformat(),
    }

    existing_reports = get_reports_with_phash(exclude_id=report_node_id)
    for other in existing_reports:
        other_phash = other.data.get("phash")
        if not phash or not other_phash:
            continue
        dist = hamming_distance(phash, other_phash)
        if dist < 0:
            continue
        data["hamming_distances"].append({"node_id": other.id, "distance": dist})
        if 0 <= dist <= 5:
            edge = create_and_add_edge(EdgeType.REPOST_OF, report_node_id, other.id, case_id, {"hamming": dist})
            await broadcast_graph_update("add_edge", edge.model_dump(mode="json"))
        elif 6 <= dist <= 15:
            edge = create_and_add_edge(EdgeType.MUTATION_OF, report_node_id, other.id, case_id, {"hamming": dist})
            await broadcast_graph_update("add_edge", edge.model_dump(mode="json"))

    update_node(report_node_id, data)
    updated = get_node(report_node_id)
    if updated:
        await broadcast_graph_update("update_node", updated.model_dump(mode="json"))


async def _process_video(
    case_id: str,
    report_node_id: str,
    media_url: str,
    llm_provider: str = "default"
) -> None:
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
        # Retry TwelveLabs API call with exponential backoff
        async def call_twelvelabs():
            return await twelvelabs.detect_deepfake(media_url, evidence_context)
        
        deepfake_scores = await _retry_api_call(call_twelvelabs, max_retries=3, backoff_base=1.0)
        
        if deepfake_scores:
            logger.info(f"TwelveLabs deepfake detection completed for {media_url}")
        else:
            logger.warning(f"TwelveLabs deepfake detection failed after retries for {media_url}")
            # Use fallback scores if all retries exhausted
            deepfake_scores = {
                "deepfake_probability": 20.0,
                "manipulation_probability": 25.0,
                "quality_score": 65.0,
                "authenticity_score": 60.0,
                "ml_accuracy": 0.0,
                "indicators": ["TwelveLabs API unavailable - manual review required"],
            }
    except Exception as e:
        logger.exception(f"Unexpected error in TwelveLabs deepfake detection: {e}")
        # Use fallback scores if unexpected error
        deepfake_scores = {
            "deepfake_probability": 20.0,
            "manipulation_probability": 25.0,
            "quality_score": 65.0,
            "authenticity_score": 60.0,
            "ml_accuracy": 0.0,
            "indicators": ["TwelveLabs API unavailable - manual review required"],
        }

    data: dict[str, Any] = {
        "media_url": media_url,
        "media_type": "video",
        "index_task": result.get("index_task"),
        "summary": result.get("summary"),
        "search_results": result.get("search_results", []),
        "deepfake_probability": deepfake_scores.get("deepfake_probability", 20.0),
        "manipulation_probability": deepfake_scores.get("manipulation_probability", 25.0),
        "quality_score": deepfake_scores.get("quality_score", 65.0),
        "authenticity_score": deepfake_scores.get("authenticity_score", 60.0),
        "ml_accuracy": deepfake_scores.get("ml_accuracy", 0.0),
        "indicators": deepfake_scores.get("indicators", []),
        "manipulation_indicators": deepfake_scores.get("indicators", []),
        "analyzed_at": datetime.utcnow().isoformat(),
    }
    update_node(report_node_id, data)
    updated = get_node(report_node_id)
    if updated:
        await broadcast_graph_update("update_node", updated.model_dump(mode="json"))
