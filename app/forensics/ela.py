"""ELA heatmap, perceptual hash, EXIF extraction."""
import io
import logging
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
from PIL import Image

logger = logging.getLogger(__name__)

_phash_available = False
_imagehash_available = False

try:
    import imagehash
    import numpy as np

    _imagehash_available = True
except ImportError:
    pass

try:
    import cv2

    _cv2_available = True
except ImportError:
    _cv2_available = False

try:
    from PIL.ExifTags import TAGS
    from PIL import Image as PILImage

    _exif_available = True
except ImportError:
    _exif_available = False


def _fetch_image(url: str) -> bytes | None:
    """Fetch image bytes from URL."""
    if url.startswith("file://"):
        try:
            path = Path(url.replace("file://", "", 1))
            return path.read_bytes()
        except Exception as e:
            logger.warning("Failed to read local image %s: %s", url, e)
            return None
    try:
        parsed = urlparse(url)
        if parsed.path.startswith("/api/upload/"):
            filename = Path(parsed.path).name
            local_path = Path("/tmp/wolftrace-uploads") / filename
            if local_path.exists():
                return local_path.read_bytes()
    except Exception as e:
        logger.warning("Failed to read local upload from %s: %s", url, e)
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(url)
            if r.is_success:
                return r.content
    except Exception as e:
        logger.warning("Failed to fetch image %s: %s", url, e)
    return None


def compute_ela(image_bytes: bytes | None, quality: int = 90) -> bytes | None:
    """
    Compute ELA (Error Level Analysis) heatmap.
    Resave at quality, diff against original, return heatmap as PNG bytes.
    """
    if not _cv2_available or not _imagehash_available or not image_bytes:
        return None
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return None
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
        _, recompressed = cv2.imencode(".jpg", img, encode_param)
        recomp_decoded = cv2.imdecode(recompressed, cv2.IMREAD_COLOR)
        if recomp_decoded is None:
            return None
        diff = cv2.absdiff(img, recomp_decoded)
        diff_gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        _, heatmap = cv2.imencode(".png", diff_gray)
        return heatmap.tobytes() if heatmap is not None else None
    except Exception as e:
        logger.warning("ELA computation failed: %s", e)
        return None


def compute_phash(image_bytes: bytes | None) -> str | None:
    """Compute perceptual hash (pHash) as hex string."""
    if not _imagehash_available or not image_bytes:
        return None
    try:
        img = Image.open(io.BytesIO(image_bytes))
        h = imagehash.phash(img)
        return str(h)
    except Exception as e:
        logger.warning("pHash computation failed: %s", e)
        return None


def hamming_distance(h1: str | None, h2: str | None) -> int:
    """Hamming distance between two hash strings. Returns -1 if invalid."""
    if not h1 or not h2 or not _imagehash_available:
        return -1
    try:
        return imagehash.hex_to_hash(h1) - imagehash.hex_to_hash(h2)
    except Exception:
        return -1


def extract_exif(image_bytes: bytes | None) -> dict[str, Any]:
    """Extract EXIF metadata: GPS, device, timestamp."""
    if not _exif_available or not image_bytes:
        return {}
    out: dict[str, Any] = {}
    try:
        img = Image.open(io.BytesIO(image_bytes))
        exif = img.getexif()
        if not exif:
            return {}
        for tag_id, value in exif.items():
            tag = TAGS.get(tag_id, tag_id)
            if tag == "GPSInfo" and value:
                out["gps"] = _parse_gps(value)
            elif tag in ("Make", "Model", "DateTime", "DateTimeOriginal"):
                if isinstance(value, bytes):
                    try:
                        value = value.decode("utf-8", errors="replace")
                    except Exception:
                        value = str(value)
                out[tag.lower().replace(" ", "_")] = value
    except Exception as e:
        logger.warning("EXIF extraction failed: %s", e)
    return out


def _parse_gps(gps_ifd: Any) -> dict[str, float] | None:
    """Parse GPS IFD to lat/lng. gps_ifd keys: 1=lat_ref, 2=lat, 3=lng_ref, 4=lng."""
    try:
        lat = _get_gps_coord(gps_ifd.get(2), gps_ifd.get(1))
        lng = _get_gps_coord(gps_ifd.get(4), gps_ifd.get(3))
        if lat is not None and lng is not None:
            return {"lat": lat, "lng": lng}
    except Exception:
        pass
    return None


def _get_gps_coord(coord: Any, ref: Any) -> float | None:
    if coord is None:
        return None
    try:
        d, m, s = coord
        decimal = float(d) + float(m) / 60 + float(s) / 3600
        if ref and str(ref) in ("S", "W"):
            decimal = -decimal
        return decimal
    except Exception:
        return None


def analyze_media_from_url(media_url: str | None) -> dict[str, Any]:
    """
    Analyze media from URL. For images: ELA, pHash, EXIF.
    Returns dict with phash, exif, ela_available, media_url.
    """
    if not media_url:
        return {"media_url": None, "phash": None, "exif": {}, "ela_available": False}

    # Detect media type by extension or content
    url_lower = media_url.lower()
    is_image = any(url_lower.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"))

    result: dict[str, Any] = {
        "media_url": media_url,
        "phash": None,
        "exif": {},
        "ela_available": False,
    }

    if is_image:
        data = _fetch_image(media_url)
        if data:
            result["phash"] = compute_phash(data)
            result["exif"] = extract_exif(data)
            result["ela_available"] = compute_ela(data) is not None
    # Video handling is in twelvelabs service - no ELA/pHash/EXIF for video
    return result
