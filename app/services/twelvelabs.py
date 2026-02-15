"""TwelveLabs API: video indexing (Marengo), search, summarize (Pegasus)."""
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


async def index_video(video_url: str, engine: str = "marengo2") -> dict[str, Any] | None:
    """Index video with Marengo engine. Returns task info."""
    if not settings.twelvelabs_api_key or not settings.twelvelabs_index_id:
        logger.warning("TwelveLabs API key or index ID missing")
        return None
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{BASE_URL}/tasks",
                headers=_headers(),
                json={
                    "engine_id": engine,
                    "index_id": settings.twelvelabs_index_id,
                    "url": video_url,
                },
            )
            if r.is_success:
                return r.json()
    except Exception as e:
        logger.warning("TwelveLabs index_video failed: %s", e)
    return None


async def search_videos(query: str, index_id: str | None = None) -> list[dict[str, Any]]:
    """Semantic search across indexed videos."""
    if not settings.twelvelabs_api_key:
        return []
    idx = index_id or settings.twelvelabs_index_id
    if not idx:
        return []
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{BASE_URL}/search",
                headers=_headers(),
                json={"index_id": idx, "query": query},
            )
            if r.is_success:
                data = r.json()
                return data.get("data", [])
    except Exception as e:
        logger.warning("TwelveLabs search failed: %s", e)
    return []


async def summarize_video(video_url: str, engine: str = "pegasus1") -> str | None:
    """Summarize video with Pegasus engine."""
    if not settings.twelvelabs_api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{BASE_URL}/summarize",
                headers=_headers(),
                json={"video_url": video_url, "engine_id": engine},
            )
            if r.is_success:
                data = r.json()
                return data.get("summary", {}).get("text") or data.get("summary")
    except Exception as e:
        logger.warning("TwelveLabs summarize failed: %s", e)
    return None


async def analyze_video(video_url: str) -> dict[str, Any]:
    """Index + search + summarize video. Returns dict with index_task, search_results, summary."""
    result: dict[str, Any] = {"index_task": None, "search_results": [], "summary": None}
    index_task = await index_video(video_url)
    if index_task:
        result["index_task"] = index_task
    summary = await summarize_video(video_url)
    if summary:
        result["summary"] = summary
    search_results = await search_videos("campus incident video")
    result["search_results"] = search_results
    return result
