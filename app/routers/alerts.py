"""Alerts router: draft (Backboard/Gemini), approve (publish + ElevenLabs), public feed."""
from datetime import datetime

from fastapi import APIRouter

from app.config import settings
from app.graph_state import get_case_snapshot, connection_manager
from app.models.alert import (
    AlertApproveRequest,
    AlertDraftRequest,
    AlertDraftResponse,
    AlertOut,
    AlertStatus,
)
from app.services import ai, elevenlabs
from app.utils.audit import log_action
from app.utils.ids import generate_alert_id

router = APIRouter(prefix="/api", tags=["alerts"])

_alerts: list[dict] = []


@router.post("/alerts/draft", response_model=AlertDraftResponse)
async def draft_alert(req: AlertDraftRequest):
    """Officer: generate alert draft via Gemini from case context."""
    snapshot = get_case_snapshot(req.case_id)
    if not snapshot:
        return AlertDraftResponse(
            case_id=req.case_id,
            draft_text="[Case not found or no data]",
            status="draft",
            location_summary=None,
        )
    nodes = snapshot.get("nodes", [])
    edges = snapshot.get("edges", [])
    context_parts = [f"Case {req.case_id}"]
    for n in nodes[:10]:
        context_parts.append(f"- {n.get('node_type', '')}: {str(n.get('data', {}))[:200]}")
    context = "\n".join(context_parts)
    draft_text = await ai.compose_alert(context, req.officer_notes, case_id=req.case_id)
    loc_summary = None
    for n in nodes:
        if n.get("node_type") == "report":
            loc = (n.get("data") or {}).get("location")
            if loc:
                loc_summary = loc.get("building") or f"{loc.get('lat')},{loc.get('lng')}"
                break
    log_action("system", "alert_drafted", req.case_id, None)
    return AlertDraftResponse(
        case_id=req.case_id,
        draft_text=draft_text,
        status="draft",
        location_summary=loc_summary,
    )


@router.post("/alerts/approve", response_model=AlertOut)
async def approve_alert(req: AlertApproveRequest):
    """Officer: publish alert, broadcast to WS, optional TTS."""
    alert_id = generate_alert_id()
    audio_url = None
    if settings.elevenlabs_api_key and settings.elevenlabs_voice_id:
        audio_bytes = await elevenlabs.text_to_speech(req.final_text)
        if audio_bytes:
            audio_url = f"/api/alerts/{alert_id}/audio"  # In real app, serve or store
    alert_data = {
        "id": alert_id,
        "case_id": req.case_id,
        "text": req.final_text,
        "status": req.status.value,
        "location_summary": None,
        "created_at": datetime.utcnow().isoformat(),
        "audio_url": audio_url,
    }
    _alerts.append(alert_data)
    log_action("system", "alert_approved", req.case_id, alert_id)
    await connection_manager.broadcast_alert({"type": "new_alert", "alert": alert_data})
    return AlertOut(
        id=alert_id,
        case_id=req.case_id,
        text=req.final_text,
        status=req.status.value,
        location_summary=None,
        audio_url=audio_url,
    )


@router.get("/alerts", response_model=list[AlertOut])
async def list_alerts():
    """Public: list published alerts (no auth)."""
    return [
        AlertOut(
            id=a["id"],
            case_id=a["case_id"],
            text=a["text"],
            status=a["status"],
            location_summary=a.get("location_summary"),
            created_at=datetime.fromisoformat(a["created_at"]) if isinstance(a.get("created_at"), str) else datetime.utcnow(),
            audio_url=a.get("audio_url"),
        )
        for a in _alerts
    ]
