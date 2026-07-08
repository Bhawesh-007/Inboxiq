# backend/routes/websocket.py

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json

ws_router = APIRouter()


class ConnectionManager:
    """
    Manages active WebSocket connections, keyed by user_id (Supabase UUID string).
    One connection per user — if the same user reconnects, the old socket is replaced.
    """

    def __init__(self):
        # { user_id: WebSocket }
        self.active: dict[str, WebSocket] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        # Gracefully close any stale connection for this user
        if user_id in self.active:
            try:
                await self.active[user_id].close()
            except Exception:
                pass
        self.active[user_id] = websocket
        print(f"[WS] Connected: user_id={user_id}  |  total={len(self.active)}")

    def disconnect(self, user_id: str):
        self.active.pop(user_id, None)
        print(f"[WS] Disconnected: user_id={user_id}  |  total={len(self.active)}")

    async def send(self, user_id: str, payload: dict):
        """Send a JSON payload to a specific user's WebSocket connection."""
        ws = self.active.get(user_id)
        if ws:
            try:
                await ws.send_text(json.dumps(payload))
                print(f"[WS] Sent {len(payload.get('emails', []))} email(s) to user_id={user_id}")
            except Exception as e:
                print(f"[WS] Send failed for user_id={user_id}: {e}")
                self.disconnect(user_id)
        else:
            print(f"[WS] No active socket for user_id={user_id} — skipping broadcast")


# Singleton — import this anywhere you need to broadcast
manager = ConnectionManager()


@ws_router.websocket("/ws/emails/{user_id}")
async def websocket_endpoint(user_id: str, websocket: WebSocket):
    await manager.connect(user_id, websocket)
    try:
        while True:
            # Keep the connection alive; we don't expect client messages
            # but we must await something or the handler exits immediately
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(user_id)
