# Real-Time Email Synchronization Implementation Plan

## Current State Analysis
The backend has partially implemented the foundation for real-time email updates using Google Cloud Pub/Sub and Gmail API push notifications:
- **`GCP_PUB_SUB_TOPIC`** is defined in `config.py`.
- **`watch_inbox(user_id)`** is implemented in `services/gmail.py` and connected to the `POST /emails/watch` endpoint. It successfully registers a watch on the user's inbox and stores the `historyId` and `expiration`.
- **`POST /emails/webhook`** endpoint exists in `routes/email.py` to receive push payloads from GCP Pub/Sub and triggers a background sync.
- **`sync_history_emails`** in `services/sync_history_emails.py` is functional for fetching incremental history changes and saving them to Supabase.

## Next Steps for Full Real-Time Implementation

### 1. GCP Pub/Sub Infrastructure Setup
Before testing, you must properly configure Google Cloud Platform:
- **Create Topic**: In GCP Console, create a Pub/Sub topic that exactly matches the `GCP_PUB_SUB_TOPIC` environment variable.
- **Grant Permissions**: Add the Gmail API service account (`gmail-api-push@system.gserviceaccount.com`) to the topic as a **Pub/Sub Publisher**.
- **Create Push Subscription**: Create a subscription for the topic and set the Delivery Type to **Push**.
- **Local Webhook URL**: Since GCP cannot push to `localhost`, run `ngrok http 8000` (or whatever port FastAPI runs on) and set the Push Endpoint URL to `https://<ngrok-id>.ngrok.io/emails/webhook`.

### 2. Backend Enhancements
- **Enable Background Classification**: In `services/sync_history_emails.py`, the code to trigger classification on new emails is currently commented out.
  - *Action*: Uncomment and properly wire up `background_classify_emails(emails_to_store)` so new incoming emails are classified immediately.
- **Implement WebSockets for Client Notification**: The frontend currently has no way to know when the webhook has successfully processed new emails.
  - *Action*: Add a FastAPI WebSocket endpoint (e.g., `ws://localhost:8000/ws/emails/{user_id}`).
  - *Action*: Implement a `ConnectionManager` to keep track of active user WebSocket connections.
  - *Action*: Update `sync_history_emails` to broadcast a WebSocket message containing the newly parsed and classified emails to the specific `user_id` once the background task finishes.
- **Renew Watch Subscription**: The Gmail watch API expires after a maximum of 7 days.
  - *Action*: Implement a daily background task or cron job to re-call `watch_inbox(user_id)` before the `watch_expiration` is reached.

### 3. Frontend Integration
- **Connect to WebSocket**: In the frontend React/Next.js application, establish a connection to the new WebSocket endpoint.
- **Handle Real-Time Events**: Listen for incoming email payloads from the WebSocket.
- **Update UI**: Append incoming emails to the top of the `EmailList` state array without requiring a manual page refresh.

---

## Postman Testing Guide

> **Pre-requisite**: Make sure the FastAPI server is running (`uvicorn main:app --reload --port 8000`).

---

### Test 1 — Register Gmail Watch (`POST /emails/watch`)

This is the **first thing you must call** to register the push notification. It stores a `historyId` in Supabase that all incremental syncs are based on.

**Request**
```
Method : POST
URL    : http://localhost:8000/emails/watch?user_id=<YOUR_USER_UUID_FROM_SUPABASE>
Body   : (none)
```

**Expected Response**
```json
{
  "status": "watch started",
  "data": {
    "historyId": "1234567",
    "expiration": "1720000000000"
  }
}
```

**What to verify**
- Response contains `historyId` and `expiration`.
- In Supabase → `users` table, check that `last_history_id` and `watch_expiration` columns are now populated for your user row.

---

### Test 2 — Simulate a Pub/Sub Push to the Webhook (`POST /emails/webhook`)

GCP Pub/Sub sends a very specific JSON payload to your endpoint. The inner `data` field is a **base64-encoded JSON string**. You must manually construct this to test it in Postman.

#### Step 1 — Generate the base64-encoded `data` value

The raw (pre-encoding) JSON must look like this:
```json
{"emailAddress": "youremail@gmail.com", "historyId": "1234568"}
```

Use **one** of these methods to get the base64 value:

**Option A — Python (run in terminal)**
```python
import base64, json
raw = json.dumps({"emailAddress": "youremail@gmail.com", "historyId": "1234568"})
print(base64.b64encode(raw.encode()).decode())
```

**Option B — PowerShell**
```powershell
$raw = '{"emailAddress":"youremail@gmail.com","historyId":"1234568"}'
[Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($raw))
```

**Option C — Online tool**
Go to [https://www.base64encode.org](https://www.base64encode.org), paste the JSON, and copy the result.

> **Important**: Use a `historyId` that is **greater** than the one stored in your Supabase `users` table (the one set by Test 1). Otherwise Gmail History API will return no new items.

---

#### Step 2 — Build the Postman Request

```
Method       : POST
URL          : http://localhost:8000/emails/webhook
Content-Type : application/json
```

**Body (raw JSON)**
```json
{
  "message": {
    "data": "<YOUR_BASE64_STRING_FROM_STEP_1>",
    "messageId": "test-message-id-001",
    "publishTime": "2026-07-08T00:00:00Z"
  },
  "subscription": "projects/your-gcp-project/subscriptions/your-subscription-name"
}
```

**Full example with a real-looking base64 payload**
```json
{
  "message": {
    "data": "eyJlbWFpbEFkZHJlc3MiOiAieW91cmVtYWlsQGdtYWlsLmNvbSIsICJoaXN0b3J5SWQiOiAiMTIzNDU2OCJ9",
    "messageId": "test-message-id-001",
    "publishTime": "2026-07-08T00:00:00Z"
  },
  "subscription": "projects/your-gcp-project/subscriptions/gmail-push-sub"
}
```

**Expected Response (HTTP 200)**
```json
{
  "status": "accepted"
}
```

---

### Test 3 — What happens after the `accepted` response?

The `"accepted"` response means the webhook received the payload successfully, but the **actual sync runs in the background**. To verify it worked end-to-end:

1. **Check FastAPI terminal logs** — You should see:
   ```
   [Webhook] Received notification for youremail@gmail.com with History ID: 1234568
   Synced X new emails from history update.
   ```
2. **Check Supabase → `emails` table** — New email rows should appear matching any emails that arrived since the previous `historyId`.
3. **Check Supabase → `users` table** — The `last_history_id` column for your user should now be updated to `1234568`.

---

### Test 4 — Verify Existing `GET /emails` Still Works

After the webhook sync, confirm that the regular email list endpoint reflects the new emails:

```
Method : GET
URL    : http://localhost:8000/emails?page=1&per_page=10
Body   : (none)
```

**Expected**: The newly synced email should appear at the top of the list (since emails are ordered by `date DESC`).

---

### Common Errors & Fixes

| Error | Likely Cause | Fix |
|---|---|---|
| `{"error": "..."}` on webhook | Bad base64 or missing `emailAddress`/`historyId` in decoded JSON | Re-check your base64 string |
| No new emails after sync | `historyId` sent was not greater than stored `last_history_id` | Use a larger `historyId` value |
| `422 Unprocessable Entity` | Request body doesn't match `PubSubOuterJson` schema | Ensure `message`, `data`, `messageId`, `publishTime`, `subscription` are all present |
| `400 / 404 / 410` from Gmail History API | Stored `historyId` is too old (> 7 days) | Call `POST /emails/watch` again to get a fresh `historyId` |
