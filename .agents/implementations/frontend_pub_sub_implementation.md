# Frontend GCP Pub/Sub Integration — Implementation Guide

> **Scope**: Integrating the already-working GCP Pub/Sub → Gmail push webhook backend into the
> Next.js (React 19 / Next 16) frontend so new emails appear in the inbox **in real-time**,
> without any page refresh.
>
> **Stack**: FastAPI (Python) · Supabase · Next.js 16 · Vanilla CSS · Native Browser WebSocket API

---

## 1. System Overview

### Current Pipeline (backend — already working)

```
[Gmail Inbox]
      │  new email arrives
      ▼
[Gmail Push Notification]
      │  POST to GCP Pub/Sub topic  (GCP_PUB_SUB_TOPIC env var)
      ▼
[GCP Pub/Sub — Push Subscription]
      │  HTTP POST to ngrok/deployed URL
      ▼
POST /emails/webhook  (routes/email.py)
      │  decodes base64 Pub/Sub payload → { emailAddress, historyId }
      │  queues BackgroundTask
      ▼
sync_history_emails(email_address, history_id)  (services/sync_history_emails.py)
      │  calls Gmail History API since last_history_id
      │  upserts new emails to Supabase `emails` table
      │  updates `last_history_id` in Supabase `users` table
      ▼
  [Supabase DB updated — but frontend has NO idea yet]
```

### Target Pipeline (after this implementation)

```
… (same as above through sync_history_emails) …
      │
      ├──► background_classify_emails(new_emails)   [currently commented out — ENABLE]
      │         └── writes to Supabase `classifications` table
      │
      └──► WebSocket broadcast → manager.send(user_id, { type: "new_emails", emails: [...] })
                  │
                  ▼
      [Browser — useWebSocket hook]
                  │  receives WS message
                  ▼
      Emaillist.jsx — prepends new emails to top of list
                  │  shows animated "↑ N new email(s)" banner
                  ▼
      User sees inbox update live ✅
```

---

## 2. Current State Audit

| Component | File | Status |
|---|---|---|
| Pub/Sub watch registration | `services/gmail.py → watch_inbox()` | ✅ Done |
| Watch endpoint | `routes/email.py → POST /emails/watch` | ✅ Done |
| Webhook receiver | `routes/email.py → POST /emails/webhook` | ✅ Done |
| Incremental history sync | `services/sync_history_emails.py` | ✅ Done |
| Background email classifier | `routes/email.py → background_classify_emails()` | ✅ Defined, ⚠️ not called from sync |
| WebSocket server | — | ❌ Missing |
| `user_id` exposed on `GET /emails` | `routes/email.py` | ❌ Not returned |
| Frontend WebSocket connection | — | ❌ Missing |
| Real-time email prepend in UI | `Emaillist.jsx` | ❌ Missing |
| Watch auto-renewal (7-day limit) | — | ❌ Missing |

---

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

## 4. Frontend Changes

### 4.1 — NEW FILE: `frontend/inbox-iq/app/hooks/useWebSocket.js`

Create the directory `app/hooks/` and add this hook. It encapsulates all WebSocket lifecycle logic — open, message parsing, cleanup — so `Emaillist.jsx` stays clean.

```js
// frontend/inbox-iq/app/hooks/useWebSocket.js
"use client";
import { useEffect, useState, useRef, useCallback } from "react";

const WS_BASE = "ws://localhost:8000"; // adjust port if FastAPI runs elsewhere

/**
 * useWebSocket
 *
 * Opens a WebSocket connection to /ws/emails/{userId} once userId is known.
 * Parses incoming { type: "new_emails", emails: [...] } messages.
 *
 * @param {string|null} userId  - Supabase UUID; hook is a no-op until this is set
 * @returns {{ newEmails: Array, clearNewEmails: Function, wsStatus: string }}
 */
export function useWebSocket(userId) {
  const [newEmails, setNewEmails] = useState([]);
  const [wsStatus, setWsStatus]   = useState("idle"); // idle | connecting | open | closed | error
  const wsRef = useRef(null);

  useEffect(() => {
    if (!userId) return;

    const url = `${WS_BASE}/ws/emails/${userId}`;
    console.log(`[WS] Connecting to ${url}`);
    setWsStatus("connecting");

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log("[WS] Connection established");
      setWsStatus("open");
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "new_emails" && Array.isArray(msg.emails) && msg.emails.length > 0) {
          console.log(`[WS] Received ${msg.emails.length} new email(s)`);
          setNewEmails((prev) => [...msg.emails, ...prev]);
        }
      } catch (err) {
        console.error("[WS] Failed to parse message:", err);
      }
    };

    ws.onerror = (err) => {
      console.error("[WS] Error:", err);
      setWsStatus("error");
    };

    ws.onclose = (event) => {
      console.log(`[WS] Closed — code=${event.code}`);
      setWsStatus("closed");
    };

    // Cleanup: close socket when userId changes or component unmounts
    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [userId]);

  const clearNewEmails = useCallback(() => setNewEmails([]), []);

  return { newEmails, clearNewEmails, wsStatus };
}
```

---

### 4.2 — MODIFY: `frontend/inbox-iq/app/Components/Emaillist.jsx`

Six targeted changes:

1. Import `useWebSocket`
2. Add `userId` state
3. Store `user_id` from fetch response
4. Call the hook with `userId`
5. Merge `newEmails` at the top of the rendered list
6. Render the animated new-email banner

```jsx
// frontend/inbox-iq/app/Components/Emaillist.jsx
"use client";
import React from "react";
import "./Emailist.css";
import { useEffect, useState } from "react";
import Tagbadge from "./Tagbadge";
import { useWebSocket } from "../hooks/useWebSocket"; // ← 1. IMPORT

function Emaillist({ onEmailClick }) {
  const [emails, setEmails]       = useState([]);
  const [loading, setLoading]     = useState(true);
  const [selectedId, setSelectedId] = useState(null);
  const [error, setError]         = useState(null);
  const [page, setPage]           = useState(1);
  const [hasMore, setHasMore]     = useState(false);
  const [userId, setUserId]       = useState(null); // ← 2. ADD userId STATE
  const per_page = 10;

  // ← 3. CALL THE HOOK — no-op until userId is populated
  const { newEmails, clearNewEmails } = useWebSocket(userId);

  useEffect(() => {
    setLoading(true);
    fetch(`http://localhost:8000/emails?page=${page}&per_page=${per_page}`)
      .then((res) => {
        if (!res.ok) throw new Error("Failed to fetch emails");
        return res.json();
      })
      .then((data) => {
        if (data.error) {
          console.error("Backend error:", data.error);
          setError(data.error);
          setEmails([]);
        } else {
          setEmails(data.emails || []);
          setHasMore(data.pagination?.has_more || false);
          setError(null);
          // ← 4. STORE user_id so the WS hook can open its connection
          if (data.user_id && !userId) {
            setUserId(data.user_id);
          }
        }
        setLoading(false);
      })
      .catch((err) => {
        console.error("Fetch error:", err);
        setError(err.message);
        setEmails([]);
        setLoading(false);
      });
  }, [page]);

  const handleClick = (email) => {
    setSelectedId(email.id);
    onEmailClick(email.id);
    clearNewEmails(); // dismiss banner when user interacts
  };

  // ← 5. MERGE — new real-time emails sit above paginated emails
  const allEmails = [...newEmails, ...emails];

  if (loading) return <div className="loading">Loading emails ....</div>;
  if (error)   return <div className="error">Error: {error}</div>;

  return (
    <div className="supclass flex flex-col gap-3">
      <div className="header text-white text-2xl font-bold">
        <div className="head">Inbox</div>
      </div>

      {/* ← 6. REAL-TIME BANNER */}
      {newEmails.length > 0 && (
        <div className="new-email-banner" onClick={clearNewEmails}>
          ↑ {newEmails.length} new email{newEmails.length > 1 ? "s" : ""} — click to dismiss
        </div>
      )}

      <div className="emaillist flex flex-col gap-1.5">
        {allEmails.map((email) => (
          <div
            key={email.id}
            className={`email-box ${selectedId === email.id ? "selected" : ""} ${
              newEmails.some((e) => e.id === email.id) ? "email-box--new" : ""
            }`}
            onClick={() => handleClick(email)}
          >
            <div className="email-header flex items-center gap-2">
              <span className="sender">{email.from}</span>
              <span className="time">{email.date}</span>
              <Tagbadge tag={email.label} />
            </div>
            <div className="email-subject">{email.subject}</div>
          </div>
        ))}
      </div>

      <div className="pagination-container">
        <button
          className="pagination-btn"
          disabled={page === 1 || loading}
          onClick={() => setPage(page - 1)}
        >
          Prev
        </button>
        <span className="page-indicator">Page {page}</span>
        <button
          className="pagination-btn"
          disabled={!hasMore || loading}
          onClick={() => setPage(page + 1)}
        >
          Next
        </button>
      </div>
    </div>
  );
}

export default Emaillist;
```

> **Note on port**: The original `Emaillist.jsx` fetches from `localhost:5003`. Updated to `localhost:8000` (uvicorn default). If your FastAPI is on a different port, update `WS_BASE` in `useWebSocket.js` and the fetch URL here consistently.

---

### 4.3 — MODIFY: `frontend/inbox-iq/app/Components/Emailist.css`

Add styles for the new banner and the highlight state on freshly arrived email cards.
Append to the bottom of the existing file:

```css
/* ─── Real-time new-email banner ───────────────────────────────────────── */

@keyframes slideDown {
  from {
    opacity: 0;
    transform: translateY(-12px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.new-email-banner {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;

  background: linear-gradient(135deg, #0f2a2a 0%, #0a1f1f 100%);
  border: 1px solid #4db8b8;
  border-radius: 10px;
  padding: 10px 16px;

  font-size: 13px;
  font-weight: 600;
  color: #4db8b8;
  letter-spacing: 0.04em;
  cursor: pointer;

  animation: slideDown 0.3s cubic-bezier(0.22, 1, 0.36, 1) both;
  transition: background 0.2s ease, transform 0.15s ease;
}

.new-email-banner:hover {
  background: linear-gradient(135deg, #163535 0%, #0d2828 100%);
  transform: translateY(-1px);
}

/* ─── Highlight ring on cards that just arrived via WebSocket ───────────── */

@keyframes newEmailPulse {
  0%   { box-shadow: 0 0 0 0 rgba(77, 184, 184, 0.45); }
  70%  { box-shadow: 0 0 0 6px rgba(77, 184, 184, 0);  }
  100% { box-shadow: 0 0 0 0 rgba(77, 184, 184, 0);    }
}

.email-box--new {
  border-color: #4db8b8 !important;
  animation: newEmailPulse 1.4s ease-out 1;
}

/* ─── Selected email card ───────────────────────────────────────────────── */
.email-box.selected {
  background: #16213a;
  border-color: #3b82f6;
}
```

---

## 5. Data Flow — Sequence Diagram

```
Browser (Emaillist.jsx)                 FastAPI                    Gmail / GCP
         │                                 │                           │
         │── GET /emails ─────────────────►│                           │
         │◄─ { emails, user_id, ... } ─────│                           │
         │                                 │                           │
         │── WS UPGRADE /ws/emails/{uid} ─►│                           │
         │◄─ 101 Switching Protocols ───────│                           │
         │                                 │                           │
         │                                 │◄── email arrives ─────────│
         │                                 │    POST /emails/webhook   │
         │                                 │    (Pub/Sub payload)      │
         │                                 │                           │
         │                                 │── BackgroundTask ─────────►
         │                                 │   sync_history_emails()   │
         │                                 │   → upsert to Supabase    │
         │                                 │   → classify emails       │
         │                                 │   → manager.send(uid, …)  │
         │                                 │                           │
         │◄── WS message: new_emails ──────│                           │
         │    { type, emails: [...] }       │                           │
         │                                 │                           │
    prepend to list                        │                           │
    show banner                            │                           │
```

---

## 6. File Change Summary

| # | Action | File |
|---|---|---|
| 1 | **CREATE** | `backend/routes/websocket.py` |
| 2 | **MODIFY** | `backend/routes/__init__.py` — register `ws_router` |
| 3 | **MODIFY** | `backend/main.py` — add `ws://localhost:3000` to CORS origins |
| 4 | **MODIFY** | `backend/services/sync_history_emails.py` — enable classifier + WS broadcast |
| 5 | **MODIFY** | `backend/routes/email.py` — return `user_id` in `GET /emails` |
| 6 | **CREATE** | `frontend/inbox-iq/app/hooks/useWebSocket.js` |
| 7 | **MODIFY** | `frontend/inbox-iq/app/Components/Emaillist.jsx` — consume hook + render banner |
| 8 | **MODIFY** | `frontend/inbox-iq/app/Components/Emailist.css` — banner + pulse animation |

---

## 7. Environment & Dependencies

### Backend — no new pip packages required
`websockets` support is built into FastAPI / Starlette. The `WebSocket`, `WebSocketDisconnect`
imports come from `fastapi` directly.

```txt
# Already in requirements.txt (verify):
fastapi
uvicorn[standard]   ← the [standard] extra bundles websockets support
```

> If `uvicorn[standard]` is not installed, run:
> ```bash
> pip install "uvicorn[standard]"
> ```

### Frontend — no new npm packages required
Uses the native browser `WebSocket` API — zero additional dependencies.

---

## 8. Testing Checklist

### Step 1 — Backend WebSocket endpoint
```bash
# Start FastAPI
uvicorn main:app --reload --port 8000

# In a separate terminal, test the WS endpoint with wscat (optional)
npx wscat -c ws://localhost:8000/ws/emails/test-user-id
# Expected: connection stays open, no error
```

### Step 2 — Frontend loads + WebSocket connects
```bash
# Start Next.js
cd frontend/inbox-iq && npm run dev
```
- Open `http://localhost:3000`
- Open DevTools → **Network** → filter **WS**
- Load the inbox — you should see a WebSocket connection to `ws://localhost:8000/ws/emails/<uuid>`
- Status column should read **101** (Switching Protocols → Open)

### Step 3 — Simulate a Pub/Sub push
Use Postman or curl. Refer to `pub_sub_testing.md` for the full Postman payload.

```bash
# Quick curl example (adjust base64 and historyId)
curl -X POST http://localhost:8000/emails/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "data": "eyJlbWFpbEFkZHJlc3MiOiAieW91ckBnbWFpbC5jb20iLCAiaGlzdG9yeUlkIjogIjk5OTk5OSJ9",
      "messageId": "test-001",
      "publishTime": "2026-07-08T00:00:00Z"
    },
    "subscription": "projects/proj/subscriptions/sub"
  }'
```

- FastAPI terminal should log: `[WS] Sent X email(s) to user_id=<uuid>`
- Browser inbox should show the "↑ N new emails" banner **without refreshing**
- New email cards should pulse with a teal border ring

### Step 4 — End-to-end live test (requires ngrok + GCP)
```bash
# Expose FastAPI to the internet
ngrok http 8000

# Update GCP Pub/Sub Push Subscription endpoint to:
# https://<ngrok-id>.ngrok.io/emails/webhook
```
- Send a real email to the watched Gmail account
- Banner should appear in browser within ~5 seconds

---

## 9. Common Errors & Fixes

| Error | Cause | Fix |
|---|---|---|
| `WebSocket connection failed` in browser | FastAPI not running or wrong port | Check uvicorn is on port 8000; check `WS_BASE` in hook |
| `403 Forbidden` on WS upgrade | CORS origin mismatch | Add `ws://localhost:3000` to `allow_origins` in `main.py` |
| Banner never appears | `user_id` not returned from `GET /emails` | Verify Step 3.5 — `user_id` must be in the JSON response |
| WS connects but no messages | `manager.send()` raises `RuntimeError` | Check asyncio bridge — use the try/except pattern in Step 3.4 |
| `uvicorn` error: `websockets` not installed | Missing standard extras | `pip install "uvicorn[standard]"` |
| Emails synced but not classified | Classifier import still commented out | Apply Change A in Step 3.4 |
| `historyId` not found after webhook | `historyId` sent ≤ stored `last_history_id` | Use a larger `historyId` in the Postman payload |

---

## 10. Optional: Watch Auto-Renewal

Gmail watch registrations expire after **7 days**. After that, no more Pub/Sub notifications
are sent and the entire real-time pipeline goes silent.

### New file: `backend/services/watch_renewal.py`

```python
import asyncio
from datetime import datetime, timezone
from database import supabase
from services.gmail import watch_inbox


async def renewal_loop(interval_seconds: int = 86_400):
    """
    Runs every 24 hours. Re-registers the Gmail watch for any user
    whose watch_expiration is within the next 24 hours.
    """
    while True:
        await asyncio.sleep(interval_seconds)
        now = datetime.now(tz=timezone.utc)
        res = supabase.table("users").select("id, watch_expiration").execute()
        for user in res.data:
            exp_str = user.get("watch_expiration")
            if not exp_str:
                continue
            try:
                exp_dt = datetime.fromisoformat(exp_str)
                remaining = (exp_dt - now).total_seconds()
                if remaining < 86_400:   # renew if less than 24 h left
                    print(f"[WatchRenewal] Renewing watch for user {user['id']}")
                    watch_inbox(user["id"])
            except Exception as e:
                print(f"[WatchRenewal] Error for user {user['id']}: {e}")
```

### Hook into `backend/main.py` lifespan:

```python
from services.watch_renewal import renewal_loop

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting up...")
    if verify_connection():
        print("Supabase verified")
    else:
        print("Supabase not verified")
    # Start watch renewal background task
    task = asyncio.create_task(renewal_loop())
    yield
    task.cancel()
    print("Shutting down...")
```

---

*Last updated: 2026-07-08*
*Author: Antigravity (InboxIQ)*
