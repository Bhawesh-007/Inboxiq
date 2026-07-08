# InboxIQ — Implementation Plan

**Date:** 2026-07-08
**Source Diagnosis:** [diagnosis1.md](file:///D:/email_sys/Inboxiq/.agents/results/diagnosis1.md) | [test_results.md](file:///D:/email_sys/Inboxiq/.agents/results/test_results.md)
**Target:** Fix 2 failing Pub/Sub tests → achieve 6/6 PASS

---

## Context

InboxIQ is a FastAPI backend deployed on Railway that integrates Gmail's Pub/Sub Watch API
to receive real-time email push notifications via GCP Pub/Sub. Two tests currently fail:

- **Test 1** (`POST /emails/watch`) → Returns `{"error": "failed to start watch"}` instead of watch registration data
- **Test 3** (Background Sync Verification) → `last_history_id` not updated in Supabase after webhook push

The diagnosis identified **four P0 fixes** required (two code changes + two test-script fixes).

---

## Proposed Changes

---

### Component 1 — Backend: `services/gmail.py`

#### [MODIFY] [gmail.py](file:///D:/email_sys/Inboxiq/backend/services/gmail.py)

**Issue:** `watch_inbox()` uses `datetime.fromtimestamp(...)` and `timezone.utc`, but
neither `datetime` nor `timezone` are imported at the top of the file. This raises a
`NameError` on every single call to `watch_inbox`, causing it to crash silently.

**Change:** Add the missing import.

```diff
+ from datetime import datetime, timezone
  from os import get_terminal_size
  from google.oauth2.credentials import Credentials
  from googleapiclient.discovery import build
  ...
```

**Scope:** 1-line addition at the top of the file. No logic changes.

---

### Component 2 — Backend: `routes/email.py`

#### [MODIFY] [email.py](file:///D:/email_sys/Inboxiq/backend/routes/email.py)

**Issue:** The `/emails/watch` route catches all exceptions and returns `{"error": "..."}` with
HTTP 200. This makes it impossible to distinguish a real failure from a successful empty response.

**Change:** Raise an `HTTPException` with HTTP 500 on failure.

```diff
- from fastapi import APIRouter, BackgroundTasks
+ from fastapi import APIRouter, BackgroundTasks, HTTPException

  @router.post("/watch")
  async def register_watch(...):
      try:
          result = watch_inbox(user_id)
          return {"status": "watch started", "data": result}
      except Exception as e:
-         return {"error": "failed to start watch"}
+         raise HTTPException(status_code=500, detail=f"failed to start watch: {str(e)}")
```

**Scope:** Import change + 1-line change in the exception handler.

---

### Component 3 — Backend: `services/sync_history_emails.py`

#### [MODIFY] [sync_history_emails.py](file:///D:/email_sys/Inboxiq/backend/services/sync_history_emails.py)

**Issue:** When Gmail History API returns `404 invalidHistoryId` (happens when `startHistoryId`
is too old or fake), the current code re-raises the error and the function aborts before
the `last_history_id` checkpoint update on line 106.

**Change:** Catch `HttpError 404` specifically, fall back to full sync, and always save the
checkpoint.

```diff
  except HttpError as e:
-     print(f"Error fetching history: {e}")
-     raise
+     if e.resp.status == 404:
+         print(f"[Sync] History ID {last_history_id} invalid/expired. Falling back to full sync.")
+         last_history_id = None  # trigger the full re-sync else-branch below
+     else:
+         raise
```

Also add a confirmation log after the checkpoint update:

```diff
  supabase.table("users").update({"last_history_id": current_history_id}).eq("id", user_id).execute()
+ print(f"[Sync] Checkpointed last_history_id={current_history_id} for user_id={user_id}")
```

**Scope:** 4-line change in the `except` block + 1 log line.

---

### Component 4 — Test Configuration / Postman Collection

#### [MODIFY] Test Script / Postman Environment

These are not code changes — they are test procedure fixes. They should be documented in
`.agents/results/pub_sub_testing.md` (or equivalent):

**Fix T-1: Correct `user_id` for watch endpoint**
- Use the hard-coded UUID `6bf24bf5-8012-40c0-af85-91bfb4a0ac06` (`bhaweshjoshi689@gmail.com`)
- Never use `SELECT * LIMIT 1` — always filter by `email = 'bhaweshjoshi689@gmail.com'`

**Fix T-3: Realistic `historyId` in webhook payload**
- Before each test, query `last_history_id` from Supabase for `bhaweshjoshi689@gmail.com`
- Use `historyId = actual_last_history_id + 1` in the base64 Pub/Sub payload
- Increase wait time after webhook from **10 seconds → 30 seconds** before verification
- Verify the **correct user row** (`bhaweshcs@gmail.com`) in the post-test Supabase query

---

## Priority & Execution Order

| Order | Priority | Change | File | Risk |
|---|---|---|---|---|
| 1 | 🔴 P0 | Add `from datetime import datetime, timezone` | `services/gmail.py` | **Zero risk** — pure import fix |
| 2 | 🔴 P0 | Raise `HTTPException(500)` on watch failure | `routes/email.py` | **Low** — clearer error only |
| 3 | 🔴 P0 | Handle `HttpError 404` in history sync | `services/sync_history_emails.py` | **Low** — adds fallback path |
| 4 | 🔴 P0 | Fix test script: correct UUID + real historyId | Test script / Postman | **Zero** — no backend change |
| 5 | 🟡 P1 | Add checkpoint log | `services/sync_history_emails.py` | **Zero** — logging only |
| 6 | 🟢 P2 | Add credential match guard in `watch_inbox` | `services/gmail.py` | **Low** — defensive guard |

---

## Files to Modify

| File | Change Type | Severity |
|---|---|---|
| [`services/gmail.py`](file:///D:/email_sys/Inboxiq/backend/services/gmail.py) | Add import + optional guard | P0 + P2 |
| [`routes/email.py`](file:///D:/email_sys/Inboxiq/backend/routes/email.py) | Fix exception response code | P0 |
| [`services/sync_history_emails.py`](file:///D:/email_sys/Inboxiq/backend/services/sync_history_emails.py) | Handle 404 + add log | P0 + P1 |

---

## Verification Plan

### After Code Changes (Railway Redeploy)

1. **Trigger Test 1 again:**
   ```
   POST https://inboxiq-production-ec9c.up.railway.app/emails/watch?user_id=6bf24bf5-8012-40c0-af85-91bfb4a0ac06
   ```
   **Expected:** `{"status": "watch started", "data": {"historyId": "...", "expiration": "..."}}` with HTTP 200

2. **Trigger Test 3 again:**
   - Query Supabase for `bhaweshcs@gmail.com` → get real `last_history_id`
   - Send webhook with `historyId = real_id + 1`
   - Wait 30 seconds
   - Re-query Supabase for `bhaweshcs@gmail.com`
   **Expected:** `last_history_id = real_id + 1`

3. **Run full test suite** → Target: **6/6 PASS**

### Automated Tests (Future)
- Add a unit test for `watch_inbox()` mocking the Gmail API to confirm the `datetime` import
  is resolved and no `NameError` is raised.
- Add a unit test for `sync_history_emails()` with a mocked `HttpError(404)` to confirm
  the fallback path triggers correctly.

---

## Open Questions

> [!IMPORTANT]
> **Q1: Per-user OAuth tokens (P2 — lower priority)**
> Currently, `get_gmail_service()` is hardcoded to env-var credentials. If InboxIQ needs
> to support multiple Gmail accounts simultaneously, each user's OAuth tokens must be stored
> in Supabase. Should this be implemented now or deferred?
>
> **Recommendation:** Defer — it's a larger refactor and not blocking the current 2 failures.

> [!NOTE]
> **Q2: Railway env-var token freshness**
> The `GMAIL_ACCESS_TOKEN` in Railway will expire (OAuth short-lived tokens). The `creds.refresh()`
> call in `get_gmail_service()` handles this — but verify that `CLIENT_ID`, `CLIENT_SECRET`, and
> `GMAIL_REFRESH_TOKEN` are correctly set in Railway's environment variables.
