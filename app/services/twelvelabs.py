"""TwelveLabs API: video indexing (Marengo), search, summarize (Pegasus)."""
import asyncio
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.twelvelabs.io/v1.3"


def _headers() -> dict[str, str]:
    return {
        "x-api-key": settings.twelvelabs_api_key,
        "Content-Type": "application/json",
    }


async def index_video(video_url: str, engine: str = "marengo3.0") -> dict[str, Any] | None:
    """Index video with Marengo engine. Returns task info.

    Note: TwelveLabs /tasks endpoint requires multipart/form-data, not JSON.
    """
    if not settings.twelvelabs_api_key or not settings.twelvelabs_index_id:
        logger.warning("TwelveLabs API key or index ID missing")
        return None
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            # TwelveLabs requires multipart/form-data for tasks endpoint
            data = {
                "index_id": settings.twelvelabs_index_id,
                "video_url": video_url,  # Changed from "url" to "video_url"
            }

            # Remove Content-Type header, let httpx set it for multipart
            headers = {"x-api-key": settings.twelvelabs_api_key}

            r = await client.post(
                f"{BASE_URL}/tasks",
                headers=headers,
                data=data,  # Changed from json= to data=
            )

            if r.is_success:
                result = r.json()
                logger.info(f"TwelveLabs video indexing started: task_id={result.get('_id')}")
                return result
            else:
                logger.warning(f"TwelveLabs index_video failed: {r.status_code} - {r.text}")
                return None
    except Exception as e:
        logger.warning("TwelveLabs index_video failed: %s", e)
    return None


async def search_videos(query: str, index_id: str | None = None, video_id: str | None = None) -> list[dict[str, Any]]:
    """Semantic search across indexed videos.

    Args:
        query: Search query text
        index_id: Optional index ID (uses default if not provided)
        video_id: Optional specific video ID to search within

    Returns:
        List of search results with timestamps and relevance scores
    """
    if not settings.twelvelabs_api_key:
        return []
    idx = index_id or settings.twelvelabs_index_id
    if not idx:
        return []
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                "index_id": idx,
                "query_text": query,  # Changed from "query" to "query_text"
                "search_options": ["visual", "conversation", "text_in_video"],
            }

            # Add video_id if searching specific video
            if video_id:
                payload["filter"] = {"id": video_id}

            r = await client.post(
                f"{BASE_URL}/search",
                headers=_headers(),
                json=payload,
            )

            if r.is_success:
                data = r.json()
                results = data.get("data", [])
                logger.info(f"TwelveLabs search returned {len(results)} results")
                return results
            else:
                logger.warning(f"TwelveLabs search failed: {r.status_code} - {r.text}")
                return []
    except Exception as e:
        logger.warning("TwelveLabs search failed: %s", e)
    return []


async def summarize_video(video_id: str, video_url: str | None = None, engine: str = "pegasus1.2") -> str | None:
    """Summarize video with Pegasus engine.

    Args:
        video_id: TwelveLabs video ID (required - from indexing task)
        video_url: Original video URL (optional, for logging)
        engine: Pegasus engine version

    Returns:
        Summary text or None if failed
    """
    if not settings.twelvelabs_api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{BASE_URL}/summarize",
                headers=_headers(),
                json={
                    "video_id": video_id,  # Changed from video_url to video_id
                    "type": "summary",
                },
            )
            if r.is_success:
                data = r.json()
                summary = data.get("summary") or data.get("text", "")
                logger.info(f"TwelveLabs summary generated for video_id={video_id}")
                return summary
            else:
                logger.warning(f"TwelveLabs summarize failed: {r.status_code} - {r.text}")
                return None
    except Exception as e:
        logger.warning("TwelveLabs summarize failed: %s", e)
    return None


async def analyze_video(video_url: str) -> dict[str, Any]:
    """Index + wait + search + summarize video. Returns dict with index_task, search_results, summary, video_id.

    Workflow:
    1. Start indexing task
    2. Wait for indexing to complete
    3. Get video_id from task
    4. Run search and summarize with video_id
    """
    result: dict[str, Any] = {"index_task": None, "search_results": [], "summary": None, "video_id": None}

    # Step 1: Start indexing
    index_task = await index_video(video_url)
    if not index_task:
        logger.warning("Failed to start video indexing")
        return result

    result["index_task"] = index_task
    task_id = index_task.get("_id") or index_task.get("id")

    if not task_id:
        logger.warning("No task ID returned from indexing")
        return result

    # Step 2: Wait for indexing to complete
    indexing_success = await wait_for_indexing(task_id, max_wait=120)

    if not indexing_success:
        logger.warning("Video indexing did not complete successfully")
        return result

    # Step 3: Get video_id from task response
    video_id = index_task.get("video_id")
    if video_id:
        result["video_id"] = video_id

        # Step 4: Run summarization with video_id
        summary = await summarize_video(video_id, video_url)
        if summary:
            result["summary"] = summary

        # Step 5: Search within this specific video
        search_results = await search_videos("campus incident video analysis", video_id=video_id)
        result["search_results"] = search_results
    else:
        logger.warning("No video_id in index_task response")

    return result


async def wait_for_indexing(task_id: str, max_wait: int = 120) -> bool:
    """Poll task status until complete or timeout."""
    if not settings.twelvelabs_api_key:
        return False

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            for _ in range(max_wait // 5):  # Check every 5 seconds
                r = await client.get(
                    f"{BASE_URL}/tasks/{task_id}",
                    headers=_headers(),
                )
                if r.is_success:
                    data = r.json()
                    status = data.get("status", "").lower()
                    if status == "ready":
                        return True
                    elif status in ["failed", "error"]:
                        logger.warning(f"TwelveLabs indexing failed: {data.get('error')}")
                        return False

                await asyncio.sleep(5)

        logger.warning("TwelveLabs indexing timeout")
        return False
    except Exception as e:
        logger.warning(f"wait_for_indexing failed: {e}")
        return False


async def detect_deepfake(video_url: str, evidence_context: dict[str, Any], llm_provider: str = "groq") -> dict[str, Any]:
    """
    Detect deepfakes in video using GROQ (primary) or TwelveLabs (fallback).

    Args:
        video_url: URL to the video file
        evidence_context: Dict with claims, location, timestamp for context
        llm_provider: LLM provider to use ("groq" or "default")

    Returns:
        Dict with deepfake_probability, manipulation_probability, quality_score, etc.
    """
    # Primary: Use GROQ for video analysis (text-based)
    from app.services import groq, backboard_client

    if groq.is_available():
        logger.info("Using GROQ for video deepfake analysis (text-based)")

        # Get video description from Backboard vision
        try:
            description = await backboard_client.describe_image(video_url, evidence_context)

            if description:
                # Use GROQ for deepfake analysis
                ai_scores = await groq.analyze_video_deepfake(description, evidence_context)

                if ai_scores and ai_scores.get("ml_accuracy", 0) > 0:
                    logger.info(f"GROQ video analysis succeeded: ml_accuracy={ai_scores.get('ml_accuracy'):.1f}")
                    return ai_scores
                else:
                    logger.warning("GROQ video analysis failed, falling back to TwelveLabs")
            else:
                logger.warning("Backboard describe_image failed for video, falling back to TwelveLabs")
        except Exception as e:
            logger.warning(f"GROQ video analysis error: {e}, falling back to TwelveLabs")
    else:
        logger.warning("GROQ unavailable, falling back to TwelveLabs")

    # Fallback: Use TwelveLabs if GROQ fails
    if not settings.twelvelabs_api_key or not settings.twelvelabs_index_id:
        missing = []
        if not settings.twelvelabs_api_key:
            missing.append("API key")
        if not settings.twelvelabs_index_id:
            missing.append("index ID")
        logger.error(f"TwelveLabs configuration incomplete: missing {', '.join(missing)}")
        return _generate_fallback_video_scores()

    try:
        logger.info("Starting TwelveLabs deepfake detection workflow")

        # 1. Index video with Marengo engine
        index_task = await index_video(video_url, engine="marengo3.0")

        if not index_task:
            logger.warning("Failed to start video indexing")
            return _generate_fallback_video_scores()

        task_id = index_task.get("_id") or index_task.get("id")
        if not task_id:
            logger.warning("No task_id returned from indexing")
            return _generate_fallback_video_scores()

        logger.info(f"TwelveLabs video indexing started: task_id={task_id}")

        # 2. Wait for indexing to complete
        indexing_complete = await wait_for_indexing(task_id, max_wait=120)

        if not indexing_complete:
            logger.warning("TwelveLabs video indexing did not complete within timeout")
            return _generate_fallback_video_scores()

        # 3. Get video_id from task (need to fetch task status to get video_id)
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                f"{BASE_URL}/tasks/{task_id}",
                headers=_headers(),
            )
            if r.is_success:
                task_data = r.json()
                video_id = task_data.get("video_id")
            else:
                video_id = None

        if not video_id:
            logger.warning("No video_id found in completed task")
            return _generate_fallback_video_scores()

        logger.info(f"TwelveLabs indexing complete: video_id={video_id}")

        # 4. Search for deepfake indicators within this specific video
        deepfake_query = f"""Analyze this video for deepfake and manipulation indicators.

Evidence Context:
- Reported Claims: {evidence_context.get('claims', [])}
- Location: {evidence_context.get('location', {})}
- Timestamp: {evidence_context.get('timestamp')}

Detect:
1. Face manipulation artifacts (deepfake indicators)
2. Audio-visual synchronization issues
3. Unnatural facial movements or expressions
4. Temporal inconsistencies
5. Video quality and resolution

Look for signs of deepfake technology or video manipulation."""

        search_results = await search_videos(deepfake_query, video_id=video_id)

        # 5. Calculate scores from search results
        # TwelveLabs doesn't directly provide deepfake scores,
        # so we use search relevance and heuristics
        deepfake_probability = _calculate_deepfake_score(search_results)
        manipulation_probability = _calculate_manipulation_score(search_results)
        quality_score = _calculate_quality_score(search_results)
        authenticity_score = 100 - (deepfake_probability + manipulation_probability) / 2

        # 6. Get summary using video_id
        summary = await summarize_video(video_id, video_url)

        # 7. Calculate ml_accuracy from search result confidence scores
        if search_results:
            # TwelveLabs returns confidence/score for each search result
            # Average the top 5 results' confidence scores
            top_results = search_results[:5]
            confidences = [r.get("confidence", r.get("score", 0.7)) for r in top_results]
            ml_accuracy = sum(confidences) / len(confidences) if confidences else 0.7
            # Convert to 0-100 range if in 0-1 range
            if ml_accuracy <= 1.0:
                ml_accuracy = ml_accuracy * 100
        else:
            ml_accuracy = 70.0  # Default if no search results

        logger.info(f"TwelveLabs deepfake detection complete: ml_accuracy={ml_accuracy:.1f}")

        return {
            "deepfake_probability": deepfake_probability,
            "manipulation_probability": manipulation_probability,
            "quality_score": quality_score,
            "authenticity_score": authenticity_score,
            "ml_accuracy": ml_accuracy,
            "indicators": _extract_indicators(search_results),
            "summary": summary or "No summary available",
            "video_id": video_id,
            "task_id": task_id,
        }

    except Exception as e:
        logger.exception(f"TwelveLabs API error during deepfake detection: {e}")
        logger.warning("Falling back to low-confidence deepfake detection scores")
        return _generate_fallback_video_scores()


def _calculate_deepfake_score(search_results: list[dict[str, Any]]) -> float:
    """Calculate deepfake probability from search results (0-100 scale)."""
    # Heuristic: Check for deepfake-related terms in results
    if not search_results:
        return 5.0  # Low default

    deepfake_keywords = ["artificial", "synthetic", "manipulated face", "deepfake", "fake", "generated"]
    score = 0.0

    for result in search_results[:5]:  # Check top 5 results
        text = str(result).lower()
        matches = sum(1 for keyword in deepfake_keywords if keyword in text)
        score += matches * 5  # 5 points per match

    return min(score, 95.0)  # Cap at 95%


def _calculate_manipulation_score(search_results: list[dict[str, Any]]) -> float:
    """Calculate manipulation probability from search results (0-100 scale)."""
    if not search_results:
        return 8.0  # Low default

    manipulation_keywords = ["edited", "altered", "modified", "tampered", "inconsistent"]
    score = 0.0

    for result in search_results[:5]:
        text = str(result).lower()
        matches = sum(1 for keyword in manipulation_keywords if keyword in text)
        score += matches * 4

    return min(score, 90.0)


def _calculate_quality_score(search_results: list[dict[str, Any]]) -> float:
    """Calculate video quality score (0-100 scale)."""
    # Heuristic: Check for quality indicators
    if not search_results:
        return 75.0  # Default medium quality

    quality_keywords = ["high resolution", "clear", "hd", "4k", "quality"]
    low_quality_keywords = ["low resolution", "blurry", "grainy", "poor quality", "pixelated"]

    score = 75.0  # Start at medium

    for result in search_results[:3]:
        text = str(result).lower()
        if any(kw in text for kw in quality_keywords):
            score += 5
        if any(kw in text for kw in low_quality_keywords):
            score -= 10

    return max(min(score, 100.0), 0.0)


def _extract_indicators(search_results: list[dict[str, Any]]) -> list[str]:
    """Extract manipulation indicators from search results."""
    if not search_results:
        return ["No indicators detected - manual review recommended"]

    indicators = []
    for result in search_results[:3]:
        # Extract relevant text snippets
        if isinstance(result, dict):
            text = result.get("text", "")
            if text:
                indicators.append(text[:100])

    return indicators if indicators else ["Analysis complete - review video manually"]


def _generate_fallback_video_scores() -> dict[str, Any]:
    """Generate fallback scores when TwelveLabs unavailable.
    
    Uses neutral-to-positive scores for original video content while clearly indicating
    that API is unavailable and manual review is needed.
    """
    return {
        "deepfake_probability": 20.0,
        "manipulation_probability": 25.0,
        "quality_score": 65.0,
        "authenticity_score": 60.0,
        "ml_accuracy": 0.0,
        "indicators": ["TwelveLabs API unavailable - manual review required"],
        "summary": "Automatic deepfake analysis unavailable. Baseline estimate provided pending API recovery.",
        "video_id": None,
        "task_id": None,
    }
