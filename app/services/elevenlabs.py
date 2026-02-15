"""ElevenLabs API: text-to-speech for alert audio."""
import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.elevenlabs.io/v1"


async def text_to_speech(text: str, voice_id: Optional[str] = None) -> bytes | None:
    """Convert text to speech. Returns audio bytes (mp3)."""
    key = settings.elevenlabs_api_key
    vid = voice_id or settings.elevenlabs_voice_id
    if not key or not vid:
        logger.warning("ElevenLabs API key or voice ID missing")
        return None
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{BASE_URL}/text-to-speech/{vid}",
                headers={
                    "xi-api-key": key,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                },
                json={"text": text[:5000], "model_id": "eleven_turbo_v2_5"},
            )
            if r.is_success:
                return r.content
            else:
                logger.warning(f"ElevenLabs TTS failed with status {r.status_code}: {r.text}")
    except Exception as e:
        logger.warning("ElevenLabs TTS failed: %s", e)
    return None
