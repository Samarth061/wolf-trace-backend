"""WebSocket router: /ws/caseboard, /ws/alerts."""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.graph_state import connection_manager, get_all_snapshots

router = APIRouter(tags=["ws"])


@router.websocket("/ws/caseboard")
async def ws_caseboard(websocket: WebSocket):
    """Caseboard WS: on connect send all snapshots; then stream graph_update messages."""
    await websocket.accept()
    await connection_manager.connect_caseboard(websocket)
    try:
        snapshots = get_all_snapshots()
        await websocket.send_json({"type": "snapshots", "payload": snapshots})
        while True:
            try:
                _ = await websocket.receive_text()
            except WebSocketDisconnect:
                break
    finally:
        await connection_manager.disconnect_caseboard(websocket)


@router.websocket("/ws/alerts")
async def ws_alerts(websocket: WebSocket):
    """Alerts WS: stream new_alert messages when alerts are published."""
    await websocket.accept()
    await connection_manager.connect_alert(websocket)
    try:
        while True:
            try:
                _ = await websocket.receive_text()
            except WebSocketDisconnect:
                break
    finally:
        await connection_manager.disconnect_alert(websocket)
