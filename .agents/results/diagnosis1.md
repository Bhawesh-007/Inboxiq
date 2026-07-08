# InboxIQ — Failed Test Diagnosis & Solutions

**Date:** 2026-07-08 | **Source:** `test_results.md` | **Tests Analyzed:** Test 1, Test 3

---

## Overview

| # | Test | Status | Root Cause Category |
|---|---|---|---|
| 1 | `POST /emails/watch` | ❌ FAIL | **Credential / User Mismatch** |
| 3 | Background Sync Verification | ❌ FAIL | **Invalid `historyId` in Test Payload** |

---

## ❌ Test 1 — `POST /emails/watch` Failure

### Symptom
```
HTTP 200 OK
{"error": "failed to start watch"}
```
Expected: `{"status": "watch started", "data": {...}}`

### Root Cause Analysis

The failure has **three layered causes**:

#### Cause A — Pre-Test Selects Wrong User (Testing Script Bug)
The pre-test Supabase query used `SELECT ... LIMIT 1` without filtering by email, returning
`bhaweshjoshi689@gmail.com` (UUID: `e6a49a7c-...`) instead of the intended primary account
`bhaweshcs@gmail.com` (UUID: `6bf24bf5-...`). The `user_id` passed to the watch endpoint was
therefore wrong from the start.

#### Cause B — `watch_inbox()` Always Uses Env-Var Credentials, Not Per-User OAuth
In `services/gmail.py`, `watch_inbox` calls `get_gmail_service()` which is hardcoded to use
the Railway env-var tokens (`bhaweshcs@gmail.com`). When `user_id` belongs to
`bhaweshjoshi689@gmail.com`, the Gmail API call itself may succeed — but then it stores the
`historyId` against the **wrong user row** in Supabase.

#### Cause C — Missing `datetime` Import in `watch_inbox` (Critical Bug)
In `services/gmail.py` line 201:

```python
expiration_dt = datetime.fromtimestamp(expiration_ms / 1000.0, tz=timezone.utc)
```

`datetime` and `timezone` are **never imported** at the top of `gmail.py`. This raises a
`NameError` at runtime every time `watch_inbox` is called, causing it to return `None` and
the endpoint to return `{"error": "failed to start watch"}`.

**This is very likely the actual crash happening on Railway regardless of which user is passed.**

---

### Solutions for Test 1

#### Fix 1A — Immediate Test Fix (No Code Change Needed)
Call the endpoint with the correct UUID directly:

```
POST /emails/watch?user_id=6bf24bf5-8012-40c0-af85-91bfb4a0ac06
```

Or update the pre-test Supabase query to filter by email:
```python
# Before (wrong):
res = supabase.table("users").select("id").limit(1).execute()

# After (correct):
res = supabase.table("users").select("id").eq("email", "bhaweshcs@gmail.com").execute()
```

#### Fix 1B — Code Fix: Add Missing Import in `gmail.py` (P0 — Must Do)

Add the missing import at the top of `services/gmail.py`:

```diff
+ from datetime import datetime, timezone
  from os import get_terminal_size
  from google.oauth2.credentials import Credentials
  from googleapiclient.discovery import build
  ...
```

Without this fix, `watch_inbox` will crash with a `NameError` on every call regardless of
which user UUID is supplied.

#### Fix 1C — Long-Term: Validate User Match Before Calling Gmail Watch
Add a guard in `watch_inbox` to confirm the resolved Gmail account matches the requested user:

```python
def watch_inbox(user_id: str):
    from datetime import datetime, timezone  # move to top of file instead
    service = get_gmail_service()

    # Guard: verify the token Gmail account matches the requested user
    profile = service.users().getProfile(userId="me", fields="emailAddress").execute()
    token_email = profile.get("emailAddress")

    user_res = supabase.table("users").select("email").eq("id", user_id).execute()
    if not user_res.data or user_res.data[0]["email"] != token_email:
        print(f"[Watch] Credential mismatch: token={token_email}, user_id={user_id}")
        return None  # Fail fast instead of writing to wrong user row

    request_body = {"topicName": GCP_PUB_SUB_TOPIC}
    try:
        response = service.users().watch(userId="me", body=request_body).execute()
        history_id = response.get("historyId")
        expiration_ms = int(response.get("expiration"))
        expiration_dt = datetime.fromtimestamp(expiration_ms / 1000.0, tz=timezone.utc)
        supabase.table("users").update({
            "last_history_id": history_id,
            "watch_expiration": expiration_dt.isoformat()
        }).eq("id", user_id).execute()
        return response
    except Exception as e:
        print(f"Error watching inbox: {e}")
        return None
```

---

## ❌ Test 3 — Background Sync Verification Failure

### Symptom
```
last_history_id expected : 10000000
last_history_id found    : null   (unchanged in DB)
```

### Root Cause Analysis

#### Cause A — Fake `historyId` Far Beyond Real Gmail State
The webhook test sent `historyId: 10000000` — an arbitrarily large integer far ahead of any
real Gmail history entry for this account. When `sync_history_emails` ran:

1. The user `bhaweshcs@gmail.com` was found with `last_history_id = null`.
2. Because `last_history_id` was `null`, the `else` branch ran (lines 65–68 of `sync_history_emails.py`):
   ```python
   else:
       sync_emails_to_supabase()
       supabase.table("users").update({"last_history_id": current_history_id}).eq("id", user_id).execute()
       return
   ```
3. This **should** have updated `last_history_id` to `10000000`.

#### Cause B — Test Verification Read the Wrong User Row
The verification query checked the **first row** of the `users` table (which is
`bhaweshjoshi689@gmail.com`), not `bhaweshcs@gmail.com` (the address in the webhook payload).
So `last_history_id` may have been correctly updated for `bhaweshcs@gmail.com` but the test
checked the **wrong user's row** and reported `null`.

#### Cause C — Race Condition: 10-Second Wait Insufficient
The test waited only 10 seconds. On Railway, background tasks run in-process but cold starts,
GC pauses, or memory pressure can delay execution beyond 10s.

---

### Solutions for Test 3

#### Fix 3A — Use a Realistic `historyId` in Webhook Payload (P0)
Before each test run, query Supabase for the real `last_history_id`:

```python
# Step 1: Get the actual last_history_id for bhaweshcs@gmail.com
res = supabase.table("users") \
    .select("last_history_id") \
    .eq("email", "bhaweshcs@gmail.com") \
    .execute()
actual_id = int(res.data[0]["last_history_id"] or 0)

# Step 2: Send historyId = actual + 1
test_history_id = actual_id + 1
```

Use `test_history_id` in the base64 payload instead of hardcoded `10000000`.

#### Fix 3B — Read the Correct User Row in Verification Query (P0)
Update the post-webhook verification query:

```python
# Before (wrong — reads first row):
res = supabase.table("users").select("last_history_id").limit(1).execute()

# After (correct — reads specific user):
res = supabase.table("users") \
    .select("last_history_id") \
    .eq("email", "bhaweshcs@gmail.com") \
    .execute()
assert res.data[0]["last_history_id"] == str(test_history_id)
```

#### Fix 3C — Add Explicit Logging to `sync_history_emails` (P1)
Confirm the checkpoint is always saved by adding a log at the end of
`services/sync_history_emails.py`:

```python
# Line 106 — existing update
supabase.table("users").update({"last_history_id": current_history_id}).eq("id", user_id).execute()
# Add this log line:
print(f"[Sync] Checkpointed last_history_id={current_history_id} for user {user_id}")
```

Check Railway logs after the test to confirm the checkpoint actually ran.

#### Fix 3D — Increase Background Task Wait Time (P2)

```python
# Before:
time.sleep(10)

# After:
time.sleep(30)  # Railway cold starts and background scheduling can take >10s
```

---

## Priority Summary

| Priority | Fix | Location | Unblocks |
|---|---|---|---|
| 🔴 **P0** | Add `from datetime import datetime, timezone` | `services/gmail.py` top | Test 1 — stops NameError crash |
| 🔴 **P0** | Use UUID `6bf24bf5-8012-40c0-af85-91bfb4a0ac06` (bhaweshcs) | Test script / Postman | Test 1 — correct user targeted |
| 🔴 **P0** | Use `actual_last_history_id + 1` in webhook payload | Test script | Test 3 — realistic historyId |
| 🔴 **P0** | Filter verification query by `email=bhaweshcs@gmail.com` | Test script | Test 3 — reads correct row |
| 🟡 **P1** | Add checkpoint log to `sync_history_emails.py` | `services/sync_history_emails.py` | Test 3 debugging |
| 🟢 **P2** | Add credential-match guard in `watch_inbox()` | `services/gmail.py` | Future silent mismatch prevention |
| 🟢 **P2** | Increase background sync wait to 30s | Test script | Reduce flakiness on Railway |

---

> **Expected outcome after applying all P0 fixes:** All 6/6 tests should pass.
