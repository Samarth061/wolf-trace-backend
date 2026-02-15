"""Reports router: POST /api/report (public), GET /api/reports (officer)."""
from datetime import datetime

from fastapi import APIRouter

from app.event_bus import emit
from app.graph_state import add_report, create_and_add_node, broadcast_graph_update, get_all_reports
from app.models.graph import NodeType
from app.models.report import ReportCreate, ReportOut, Location
from app.utils.audit import log_action
from app.utils.ids import generate_case_id, generate_report_id

router = APIRouter(prefix="/api", tags=["reports"])


@router.post("/report", response_model=ReportOut, status_code=201)
async def submit_report(body: ReportCreate):
    """Public tip submission. Assigns case ID, creates report node, emits ReportReceived event."""
    case_id = generate_case_id()
    report_id = generate_report_id()
    ts = body.timestamp or datetime.utcnow()

    report_data = {
        "text_body": body.text_body,
        "location": body.location.model_dump() if body.location else None,
        "timestamp": ts.isoformat(),
        "media_url": body.media_url,
        "anonymous": body.anonymous,
        "contact": body.contact,
        "status": "processing",
        "created_at": datetime.utcnow().isoformat(),
    }

    report_node = create_and_add_node(
        NodeType.REPORT,
        case_id,
        report_data,
        node_id=report_id,
    )
    await broadcast_graph_update("add_node", report_node.model_dump(mode="json"))

    add_report(case_id, report_id, report_data, report_node_id=report_node.id)

    log_action("anonymous" if body.anonymous else body.contact or "unknown", "report_submitted", case_id, report_id)
    await emit("ReportReceived", {
        "case_id": case_id,
        "report_id": report_id,
        "report_node_id": report_node.id,
        "report_data": report_data,
    })

    return ReportOut(
        case_id=case_id,
        report_id=report_id,
        text_body=body.text_body,
        location=body.location,
        timestamp=ts,
        media_url=body.media_url,
        anonymous=body.anonymous,
        status="pending",
    )


@router.get("/reports", response_model=list[ReportOut])
async def list_reports():
    """Officer-only: list all reports."""
    out = []
    for r in get_all_reports():
        loc = r.get("location")
        if loc and isinstance(loc, dict):
            try:
                loc = Location(**{k: v for k, v in loc.items() if k in ("lat", "lng", "building")})
            except Exception:
                loc = None
        ts = r.get("timestamp")
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                ts = None
        created = r.get("created_at")
        if isinstance(created, str):
            try:
                created = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except Exception:
                created = datetime.utcnow()
        else:
            created = datetime.utcnow()
        out.append(ReportOut(
            case_id=r.get("case_id", ""),
            report_id=r.get("report_id", ""),
            text_body=r.get("text_body", ""),
            location=loc,
            timestamp=ts,
            media_url=r.get("media_url"),
            anonymous=r.get("anonymous", True),
            status=r.get("status", "pending"),
            created_at=created,
        ))
    return out
