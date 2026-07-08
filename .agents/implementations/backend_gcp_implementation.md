## 3. Backend Changes

### 3.1 — NEW FILE: `backend/routes/websocket.py`

This file owns the `ConnectionManager` singleton and the `/ws/emails/{user_id}` endpoint.
It is the **only** file that manages WebSocket state — all other modules import `manager` from here.

```python
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
```

---

### 3.2 — MODIFY: `backend/routes/__init__.py`

Register the new WebSocket router alongside the existing routers.

**Before:**
```python
from fastapi import APIRouter
from .email import router as email_router
from .auth import router as auth_router

api_router = APIRouter()
api_router.include_router(email_router)
api_router.include_router(auth_router)
```

**After:**
```python
from fastapi import APIRouter
from .email import router as email_router
from .auth import router as auth_router
from .websocket import ws_router          # ← ADD

api_router = APIRouter()
api_router.include_router(email_router)
api_router.include_router(auth_router)
api_router.include_router(ws_router)      # ← ADD
```

---

### 3.3 — MODIFY: `backend/main.py`

The CORS middleware **must also allow WebSocket upgrade headers**. Add `ws://localhost:3000`
to `allow_origins` (or use `["*"]` for local development).

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "ws://localhost:3000"],  # ← add ws origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

### 3.4 — MODIFY: `backend/services/sync_history_emails.py`

Two changes after the `supabase.table("emails").upsert(emails_to_store).execute()` call:

**Change A — Enable background classification (uncomment + fix import)**

```python
# BEFORE (lines 102-104 — currently commented out):
# Optional: Trigger your background classifier on these new emails
# from routes.email import background_classify_emails
# background_classify_emails(emails_to_store)

# AFTER — uncomment and import correctly:
from routes.email import background_classify_emails
background_classify_emails(emails_to_store)   # classifies & writes to Supabase
```

**Change B — Broadcast new emails via WebSocket**

`sync_history_emails` is a **synchronous** function called inside a FastAPI `BackgroundTask`.
To send a WebSocket message (which is `async`), we need `asyncio.run()` as a bridge.

```python
# Add at top of file:
import asyncio
import json

# Add after upsert + classification, still inside `if emails_to_store:` block:

from routes.websocket import manager   # import the singleton

# Format emails for frontend (mirrors GET /emails response shape)
formatted_emails = [
    {
        "id":      e["gmail_id"],
        "subject": e["subject"],
        "from":    e["sender"],
        "date":    e["date"],
        "label":   "unknown",   # classification runs async; frontend re-fetches on click
        "body":    e.get("body", ""),
    }
    for e in emails_to_store
]

payload = {
    "type":   "new_emails",
    "emails": formatted_emails,
}

# Bridge sync → async for the WebSocket send
try:
    asyncio.run(manager.send(user_id, payload))
except RuntimeError:
    # If an event loop is already running (e.g. in testing), use create_task instead
    import asyncio as _aio
    loop = _aio.get_event_loop()
    loop.run_until_complete(manager.send(user_id, payload))
```

> **Full updated `if new_message_ids:` block in context:**
> ```python
> if emails_to_store:
>     supabase.table("emails").upsert(emails_to_store).execute()
>     print(f"Synced {len(emails_to_store)} new emails from history update.")
>
>     # 1. Classify the new emails
>     from routes.email import background_classify_emails
>     background_classify_emails(emails_to_store)
>
>     # 2. Broadcast to the connected browser client
>     from routes.websocket import manager
>     formatted_emails = [
>         {"id": e["gmail_id"], "subject": e["subject"],
>          "from": e["sender"], "date": e["date"], "label": "unknown"}
>         for e in emails_to_store
>     ]
>     try:
>         asyncio.run(manager.send(user_id, {"type": "new_emails", "emails": formatted_emails}))
>     except RuntimeError:
>         pass
> ```

---

### 3.5 — MODIFY: `backend/routes/email.py` — Expose `user_id` from `GET /emails`

The frontend needs `user_id` (the Supabase UUID) to open the correct WebSocket channel.
The easiest way is to add it to the existing `GET /emails` response — it's already computed
as a local variable inside the endpoint.

**Find the return statement (approx. line 134) and add `user_id`:**

```python
# BEFORE:
return {
    "emails": frontend_emails,
    "pagination": {
        "page": page,
        "per_page": per_page,
        "has_more": next_page_token is not None or len(frontend_emails) == per_page
    }
}

# AFTER:
return {
    "emails": frontend_emails,
    "user_id": user_id,           # ← ADD — Supabase UUID string
    "pagination": {
        "page": page,
        "per_page": per_page,
        "has_more": next_page_token is not None or len(frontend_emails) == per_page
    }
}
```

---