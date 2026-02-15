"""Pipeline 3: Clustering — temporal, geo, semantic deduplication."""
import logging
from datetime import datetime, timedelta
from math import asin, cos, radians, sin, sqrt
from typing import Any

from app.graph_state import (
    add_report,
    broadcast_graph_update,
    create_and_add_edge,
    get_all_reports,
    get_node,
)
from app.models.graph import EdgeType

logger = logging.getLogger(__name__)

TEMPORAL_WINDOW_MINUTES = 30
GEO_RADIUS_METERS = 200.0
SIMILARITY_THRESHOLD = 0.4
WEIGHT_TEMPORAL = 0.3
WEIGHT_GEO = 0.3
WEIGHT_SEMANTIC = 0.4


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in meters."""
    R = 6371000  # Earth radius in meters
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlam = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlam / 2) ** 2
    c = 2 * asin(sqrt(a))
    return R * c


async def run_clustering(
    case_id: str,
    report_node_id: str,
    report_data: dict[str, Any],
) -> None:
    """
    Compare incoming report to all existing reports.
    Signals: temporal proximity (30 min), geo (200m), semantic (keyword overlap).
    If combined score >= 0.4, merge with SIMILAR_TO edge.
    """
    report_ts = report_data.get("timestamp")
    if isinstance(report_ts, str):
        try:
            report_ts = datetime.fromisoformat(report_ts.replace("Z", "+00:00"))
        except Exception:
            report_ts = datetime.utcnow()
    elif not report_ts:
        report_ts = datetime.utcnow()

    loc = report_data.get("location") or {}
    report_lat = loc.get("lat")
    report_lng = loc.get("lng")
    report_text = report_data.get("text_body", "").lower()
    report_keywords = set(w for w in report_text.split() if len(w) > 3)

    best_match: tuple[str, float, dict[str, float]] | None = None
    best_score = 0.0

    for existing in get_all_reports():
        if existing.get("report_id") == report_data.get("report_id"):
            continue
        exist_case = existing.get("case_id")
        if exist_case == case_id:
            continue

        # Temporal
        exist_ts = existing.get("timestamp") or existing.get("created_at")
        if isinstance(exist_ts, str):
            try:
                exist_ts = datetime.fromisoformat(exist_ts.replace("Z", "+00:00"))
            except Exception:
                exist_ts = datetime.utcnow()
        elif not exist_ts:
            exist_ts = datetime.utcnow()
        delta = abs((report_ts - exist_ts).total_seconds())
        temporal_score = 1.0 if delta <= TEMPORAL_WINDOW_MINUTES * 60 else max(0, 1 - delta / 3600)

        # Geo
        exist_loc = existing.get("location") or {}
        exist_lat = exist_loc.get("lat")
        exist_lng = exist_loc.get("lng")
        if report_lat is not None and report_lng is not None and exist_lat is not None and exist_lng is not None:
            dist = haversine_meters(report_lat, report_lng, exist_lat, exist_lng)
            geo_score = 1.0 if dist <= GEO_RADIUS_METERS else max(0, 1 - dist / 1000)
        else:
            geo_score = 0.0

        # Semantic (keyword overlap)
        exist_text = (existing.get("text_body") or "").lower()
        exist_keywords = set(w for w in exist_text.split() if len(w) > 3)
        overlap = len(report_keywords & exist_keywords) / max(1, len(report_keywords | exist_keywords))
        semantic_score = min(1.0, overlap * 2)

        combined = (
            WEIGHT_TEMPORAL * temporal_score
            + WEIGHT_GEO * geo_score
            + WEIGHT_SEMANTIC * semantic_score
        )
        if combined >= SIMILARITY_THRESHOLD and combined > best_score:
            exist_node_id = existing.get("report_node_id") or existing.get("report_id")
            if exist_node_id and get_node(exist_node_id):
                component_scores = {
                    "temporal_score": temporal_score,
                    "geo_score": geo_score,
                    "semantic_score": semantic_score,
                }
                best_match = (exist_node_id, combined, component_scores)
                best_score = combined

    if best_match:
        other_node_id, score, components = best_match
        edge = create_and_add_edge(
            EdgeType.SIMILAR_TO,
            report_node_id,
            other_node_id,
            case_id,
            {
                "confidence": score,
                "temporal_score": components["temporal_score"],
                "geo_score": components["geo_score"],
                "semantic_score": components["semantic_score"],
            },
        )
        await broadcast_graph_update("add_edge", edge.model_dump(mode="json"))
