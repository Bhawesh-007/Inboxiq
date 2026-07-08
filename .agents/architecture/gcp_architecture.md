# InboxIQ — GCP Architecture Layout

> A complete reference for how the GCP Pub/Sub pipeline integrates with Gmail,
> the FastAPI backend, and Supabase to power real-time email intelligence.

---

## 1. Big Picture Overview

```
+-------------------------------------------------------------------------+
|                           USER / FRONTEND                               |
|                         (Next.js — port 3000)                           |
+----------------------------+--------------------------------------------+
                             |  REST API calls
                             v
+-------------------------------------------------------------------------+
|                    FastAPI Backend (Python)                              |
|                                                                         |
|   +------------------+   +--------------------+   +----------------+   |
|   |  /emails (GET)   |   | /emails/watch (POST)|   |/emails/webhook |   |
|   |  Fetch & paginate|   |  Watch API trigger  |   |  (POST)        |   |
|   +------------------+   +--------------------+   |  Webhook API   |   |
|                                                     +----------------+   |
+----------+---------------------+---------------------------+------------+
           |                     |                           |
           v                     v                           v
+------------------+   +----------------------+   +----------------------+
|   Gmail API      |   |  GCP Cloud Pub/Sub   |   |  Supabase (Postgres) |
|                  |   |                      |   |                      |
| - messages.list  |   |  Topic: gmail-inbox  |   |  Tables:             |
| - messages.get   |   |  Subscription -->    |   |  - users             |
| - users.watch    |   |  Push to /webhook    |   |  - emails            |
| - history.list   |   |                      |   |  - classifications   |
+------------------+   +----------------------+   |  - page_tokens       |
                                                    +----------------------+
```

---

## 2. The Two Key APIs

### 2A. Watch API — `POST /emails/watch`

**Purpose:** Registers a real-time change listener on the user Gmail inbox.

**Flow:**
```
Frontend / Admin Call
        |
        |  POST /emails/watch?user_id=<uuid>
        v
FastAPI --> watch_inbox(user_id)
        |
        |  Calls Gmail API:
        |  service.users().watch(userId="me", body={
        |      "topicName": "projects/<proj>/topics/gmail-inbox"
        |  })
        v
Gmail API acknowledges and begins pushing change notifications
        |
        |  Returns:
        |  {
        |    "historyId": "12345",
        |    "expiration": "<epoch_ms>"   <- valid for ~7 days
        |  }
        v
FastAPI saves to Supabase users table:
  - last_history_id  = "12345"
  - watch_expiration = "2026-07-14T..."
```

**Key Facts:**

| Property | Value |
|---|---|
| Route | `POST /emails/watch` |
| File | `routes/email.py` (line 204) |
| Service | `services/gmail.py — watch_inbox()` |
| GCP resource | Cloud Pub/Sub Topic (GCP_PUB_SUB_TOPIC env var) |
| Expiry | ~7 days — must be renewed periodically |
| Saves to DB | `users.last_history_id`, `users.watch_expiration` |

**Why it is needed:**
Without calling `watch`, Gmail has no idea where to send notifications.
This is the **subscription handshake** — it tells Gmail:
"Send all inbox changes to our GCP Pub/Sub topic."

---

### 2B. Webhook API — `POST /emails/webhook`

**Purpose:** Receives real-time push notifications from GCP Pub/Sub whenever Gmail detects a change in the watched inbox.

**Flow:**
```
New Email Arrives in Gmail
        |
        |  Gmail detects change
        v
GCP Pub/Sub Topic (gmail-inbox)
        |
        |  Push delivery (HTTP POST) to:
        |  https://<your-domain>/emails/webhook
        v
FastAPI /emails/webhook receives payload:
  {
    "message": {
      "data": "<base64-encoded JSON>",
      "messageId": "...",
      "publishTime": "..."
    },
    "subscription": "projects/.../subscriptions/..."
  }
        |
        |  Step 1: Decode base64 --> JSON
        |  {
        |    "emailAddress": "user@gmail.com",
        |    "historyId": "12399"
        |  }
        v
  Step 2: Trigger background task --> sync_history_emails(email, historyId)
        |
        |  Calls Gmail history.list(startHistoryId = last_history_id)
        |  --> Gets only messages ADDED since last checkpoint
        v
  Step 3: Fetch full detail for each new message
        |
  Step 4: Upsert new emails into Supabase emails table
        |
  Step 5: Update users.last_history_id = current historyId
        v
  Returns {"status": "accepted"} immediately (non-blocking)
```

**Key Facts:**

| Property | Value |
|---|---|
| Route | `POST /emails/webhook` |
| File | `routes/email.py` (line 188) |
| Trigger | GCP Pub/Sub push subscription |
| Payload | Base64-encoded JSON with emailAddress + historyId |
| Processing | Background task (non-blocking) |
| Sync service | `services/sync_history_emails.py` |

**Why it is needed:**
This is the **event receiver**. Instead of polling Gmail every few seconds (expensive, slow),
GCP Pub/Sub *pushes* a notification to this endpoint the moment something changes.
The webhook processes the change incrementally using Gmail history API.

---

## 3. Full Real-Time Email Flow (End to End)

```
Step 0: Setup (one-time per user)
──────────────────────────────────
  POST /emails/watch
     └─► Gmail.watch() ──► GCP Pub/Sub Topic registered
     └─► historyId saved to Supabase users table


Step 1: New email arrives in Gmail
────────────────────────────────────
  Gmail detects change
     └─► Publishes event to GCP Pub/Sub Topic (gmail-inbox)


Step 2: GCP Pub/Sub pushes notification
──────────────────────────────────────────
  Pub/Sub Subscription (Push mode)
     └─► HTTP POST --> FastAPI /emails/webhook
         Payload: { emailAddress, historyId }


Step 3: Webhook processes the event
──────────────────────────────────────
  FastAPI decodes base64 payload
     └─► Spawns BackgroundTask: sync_history_emails(email, historyId)
     └─► Returns 200 {"status": "accepted"} immediately


Step 4: Incremental sync via Gmail History API
────────────────────────────────────────────────
  sync_history_emails:
     └─► Reads users.last_history_id from Supabase
     └─► Calls Gmail history.list(startHistoryId=last_history_id)
     └─► Extracts only "messagesAdded" events
     └─► Fetches full detail for each new message ID
     └─► Upserts into Supabase emails table
     └─► Updates users.last_history_id = new historyId


Step 5: Frontend reads from Supabase
───────────────────────────────────────
  GET /emails
     └─► Reads from Supabase (emails + classifications)
     └─► Triggers ML classification for unclassified emails (background)
     └─► Returns paginated, classified email list to frontend
```

---

## 4. History ID — The Sync Checkpoint

The `historyId` is the most critical piece of state in this pipeline:

```
historyId Lifecycle
────────────────────────────────────────────────────
  watch() called --> historyId = 12345 (baseline)
       |
       v
  Email arrives --> Gmail sends historyId = 12399
       |
       v
  webhook receives 12399
       |
       v
  history.list(startHistoryId=12345)
     --> returns changes between 12345 and 12399
       |
       v
  last_history_id updated to 12399
       |
       v
  Next email --> historyId = 12450
  history.list(startHistoryId=12399) --> delta only
```

**Edge Cases Handled:**

| Scenario | Handling |
|---|---|
| History expired (>7 days old) | Falls back to full `sync_emails_to_supabase()` |
| No history ID in DB | Does a fresh full sync on first webhook call |
| Watch registration expired | `watch_expiration` field enables a renewal job/cron |

---

## 5. GCP Pub/Sub Configuration

```
GCP Project
    └─► Pub/Sub Topic: "gmail-inbox"   (set via GCP_PUB_SUB_TOPIC env var)
         └─► Subscription (Push mode)
              └─► Endpoint: https://<your-backend>/emails/webhook
              └─► Delivery: HTTP POST with Pub/Sub envelope JSON
              └─► Retry policy: exponential backoff on non-2xx responses
```

**Setup Requirements:**
- The backend endpoint must be **publicly reachable over HTTPS** (use ngrok for local dev).
- GCP service account must grant the Gmail API `pubsub.topics.publish` on the topic.
- Gmail API must be authorized with scope `https://www.googleapis.com/auth/gmail.readonly` (minimum).
- The Pub/Sub subscription must be configured in **Push** mode, not Pull.

---

## 6. Component Responsibility Summary

| Component | File | Role |
|---|---|---|
| `GET /emails` | `routes/email.py` | Pulls emails on demand; triggers ML classification in background |
| `POST /emails/watch` | `routes/email.py` | **Watch API** — registers Gmail inbox listener with GCP Pub/Sub |
| `POST /emails/webhook` | `routes/email.py` | **Webhook API** — receives push events from GCP; triggers incremental sync |
| `watch_inbox()` | `services/gmail.py` | Calls `Gmail.users().watch()` and persists `historyId` to Supabase |
| `sync_history_emails()` | `services/sync_history_emails.py` | Fetches only new emails using `Gmail.history.list()` delta |
| GCP Pub/Sub Topic | GCP Console | Message broker between Gmail and the backend |
| Supabase `users` table | Supabase | Stores `last_history_id` and `watch_expiration` checkpoints |
| Supabase `emails` table | Supabase | Persistent store of synced email content |
| Supabase `classifications` table | Supabase | ML-generated labels, priorities, and summaries |
| ML Model `classify_batch()` | `ml_model/predict.py` | Runs in background: tags emails urgent / action / fyi / spam |

---

## 7. Files Reference Map

```
backend/
├── main.py                          ← FastAPI app bootstrap, CORS, router mount
├── config.py                        ← Env vars: tokens, CLIENT_ID, GCP_PUB_SUB_TOPIC
├── database.py                      ← Supabase client init and connection verify
├── routes/
│   ├── __init__.py                  ← Registers api_router
│   └── email.py                     ← /emails GET, /emails/{id} GET,
│                                       /emails/watch POST, /emails/webhook POST
├── services/
│   ├── gmail.py                     ← Gmail API wrapper: fetch, sync, watch_inbox
│   ├── sync_history_emails.py       ← Incremental delta sync using history.list()
│   └── parser.py                    ← HTML body extraction utilities
├── ml_model/
│   └── predict.py                   ← classify_email(), classify_batch()
└── pagination/
    └── paginator.py                 ← Page token management in Supabase
```

---

## 8. Watch vs Webhook — Quick Comparison

| | Watch API | Webhook API |
|---|---|---|
| **Direction** | Backend → Gmail | GCP → Backend |
| **Called by** | Developer / Admin (setup step) | GCP Pub/Sub automatically |
| **Frequency** | Once every ~7 days (renewal) | On every Gmail inbox change |
| **Purpose** | Register the listener | Receive the notification |
| **Route** | `POST /emails/watch` | `POST /emails/webhook` |
| **Data sent** | Pub/Sub topic name | base64-encoded {emailAddress, historyId} |
| **Response** | historyId + expiration | {"status": "accepted"} |
| **Analogy** | Signing up for a newsletter | Receiving a newsletter issue |

---

> **Renewal Reminder:** The `watch` registration expires every ~7 days.
> A cron job or GCP Cloud Scheduler should call `POST /emails/watch`
> periodically to keep the real-time pipeline alive.
