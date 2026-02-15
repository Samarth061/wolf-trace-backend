"""Google Fact Check Tools API."""
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://factchecktools.googleapis.com/v1alpha1"


async def search_claims(claim_text: str) -> list[dict[str, Any]]:
    """Search fact check for a claim. Returns list of review results."""
    api_key = settings.factcheck_api_key or settings.gemini_api_key
    if not api_key:
        return []
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                f"{BASE_URL}/claims:search",
                params={"query": claim_text[:500], "key": api_key},
            )
            if r.is_success:
                data = r.json()
                return data.get("claims", [])
    except Exception as e:
        logger.warning("Fact Check API failed: %s", e)
    return []
