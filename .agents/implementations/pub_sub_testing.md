
## Postman Testing Guide

> **Pre-requisite**: Make sure the FastAPI server is running (`uvicorn main:app --reload --port 8000`).

---

### Test 1 — Register Gmail Watch (`POST /emails/watch`)

This is the **first thing you must call** to register the push notification. It stores a `historyId` in Supabase that all incremental syncs are based on.

**Request**
```
Method : POST
URL    : http://inboxiq-production-ec9c.up.railway.app/emails/watch?user_id=e6a49a7c-cf70-4810-ac4f-d2c3d2fa9bd4
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


#### Step 1 — Build the Postman Request

```
Method       : POST
URL          : http://inboxiq-production-ec9c.up.railway.app/emails/webhook
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
  "status": "accepted",
  "decode_data" : "data_json",
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


### Common Errors & Fixes

| Error | Likely Cause | Fix |
|---|---|---|
| `{"error": "..."}` on webhook | Bad base64 or missing `emailAddress`/`historyId` in decoded JSON | Re-check your base64 string |
| No new emails after sync | `historyId` sent was not greater than stored `last_history_id` | Use a larger `historyId` value |
| `422 Unprocessable Entity` | Request body doesn't match `PubSubOuterJson` schema | Ensure `message`, `data`, `messageId`, `publishTime`, `subscription` are all present |
| `400 / 404 / 410` from Gmail History API | Stored `historyId` is too old (> 7 days) | Call `POST /emails/watch` again to get a fresh `historyId` |
