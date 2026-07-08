# InboxIQ — Pub/Sub API Test Results (Railway Production)

**Date:** 2026-07-08 | **Tested Against:** `https://inboxiq-production-ec9c.up.railway.app` | **Overall: ⚠️ 4/6 PASSED**

> **Fix Status (2026-07-08):** Code fixes from `fix_implementation.md` applied. Awaiting Railway redeploy + re-test to confirm 6/6.

---

## Summary

| # | Test (from pub_sub_testing.md) | Method | Endpoint | HTTP | Result |
|---|---|---|---|---|---|
| 0 | Health Check | `GET` | `/` | `200` | ✅ PASS |
| Pre | Supabase User Lookup | `INTERNAL` | `supabase.users` | `200` | ✅ PASS |
| 1 | Register Gmail Watch | `POST` | `/emails/watch` | `200` | ❌ FAIL — fix applied, pending redeploy |
| 2 | Simulate Pub/Sub Webhook Push | `POST` | `/emails/webhook` | `200` | ✅ PASS |
| 3 | Background Sync Verification | `INTERNAL` | `supabase.users + supabase.emails` | `—` | ❌ FAIL — fix applied, pending redeploy |
| 4 | GET /emails Returns Emails | `GET` | `/emails?page=1&per_page=10` | `200` | ✅ PASS |

---

## Test 0 — Health Check

| Field | Value |
|---|---|
| Method | `GET` |
| URL | `https://inboxiq-production-ec9c.up.railway.app/` |
| HTTP Status | `200` |
| Response | `{"status": "InboxIQ backend is running"}` |
| Result | ✅ **PASS** |

---

## Pre-Test — Supabase User Lookup

| Field | Value |
|---|---|
| Method | `INTERNAL` (Supabase Python SDK) |
| Table | `supabase.users` |
| User ID Found | `e6a49a7c-cf70-4810-ac4f-d2c3d2fa9bd4` |
| Email | `bhaweshjoshi689@gmail.com` |
| `last_history_id` (before tests) | `null` — **no watch ever registered for this user** |
| Result | ✅ **PASS** (user exists, data returned) |

> ⚠️ **Note:** Supabase returned a different user (`bhaweshjoshi689@gmail.com`) than the primary test account (`bhaweshcs@gmail.com`). This is because `SELECT ... LIMIT 1` returns the first row, not a specific user. The watch endpoint depends on valid Gmail credentials for the matched user, so it failed.

> **Test Procedure Fix (from fix_implementation.md):** Always filter by `email = 'bhaweshcs@gmail.com'` — never use `LIMIT 1` without a filter.

---

## Test 1 — Register Gmail Watch (`POST /emails/watch`) ❌

| Field | Value |
|---|---|
| Method | `POST` |
| URL | `https://inboxiq-production-ec9c.up.railway.app/emails/watch?user_id=e6a49a7c-cf70-4810-ac4f-d2c3d2fa9bd4` |
| HTTP Status | `200` |
| Response | `{"error": "failed to start watch"}` |

**Assertion Checks:**

| Check | Result |
|---|---|
| `status == 200` | ✅ |
| `response.status == "watch started"` | ❌ |
| `response.data.historyId` present | ❌ |
| `response.data.expiration` present | ❌ |

**Result: ❌ FAIL**

**Root Causes Identified (diagnosis1.md):**

| # | Cause | Type |
|---|---|---|
| A | `from datetime import datetime, timezone` missing in `services/gmail.py` — caused `NameError` crash in `watch_inbox()` on every call | **Code bug** |
| B | Test used wrong `user_id` (`bhaweshjoshi689` via `LIMIT 1`) instead of `bhaweshcs@gmail.com` (`6bf24bf5-...`) | **Test script bug** |
| C | No credential-match guard — `watch_inbox()` silently updates wrong user row | **Code gap** |

**Fixes Applied (2026-07-08):**

| Fix | File | Change |
|---|---|---|
| ✅ Added `from datetime import datetime, timezone` | `services/gmail.py` | Resolves NameError crash |
| ✅ Changed error response to `HTTPException(status_code=500)` | `routes/email.py` | Clearer failure signal |
| ⏳ Use UUID `6bf24bf5-8012-40c0-af85-91bfb4a0ac06` | Test script / Postman | **Pending — manual update** |

**Re-test Procedure:**
```
POST https://inboxiq-production-ec9c.up.railway.app/emails/watch?user_id=6bf24bf5-8012-40c0-af85-91bfb4a0ac06
```
**Expected after redeploy:** `{"status": "watch started", "data": {"historyId": "...", "expiration": "..."}}`

---

## Test 2 — Simulate Pub/Sub Webhook Push (`POST /emails/webhook`) ✅

Base64 payload decoded: `{"emailAddress": "bhaweshcs@gmail.com", "historyId": "10000000"}`

| Field | Value |
|---|---|
| Method | `POST` |
| URL | `https://inboxiq-production-ec9c.up.railway.app/emails/webhook` |
| HTTP Status | `200` |
| `message.data` (decoded) | `{"emailAddress": "bhaweshcs@gmail.com", "historyId": "10000000"}` |
| `message.messageId` | `test-msg-railway-001` |
| Response | `{"status": "accepted"}` |

**Assertion Checks:**

| Check | Result |
|---|---|
| `status == 200` | ✅ |
| `response.status == "accepted"` | ✅ |
| No `error` field in response | ✅ |

**Result: ✅ PASS** — Webhook endpoint correctly decoded the base64 Pub/Sub payload and accepted it. Background sync was triggered.

---

## Test 3 — Background Sync Supabase Verification ❌

Waited **10 seconds** after webhook, then queried Supabase.

| Field | Value |
|---|---|
| `last_history_id` expected | `10000000` |
| `last_history_id` found in DB | `null` |
| `history_id_updated` | `false` |
| Emails exist in DB | ✅ yes |

**Top 3 emails in Supabase (for the user returned):**

| Gmail ID | Subject | Date |
|---|---|---|
| `19f31ccc51fc1a01` | Query regarding tally codebrewers hackathon | Sun, 5 Jul 2026 |
| `19f32e32e9a3a6bf` | "Cleaning services" | Sun, 5 Jul 2026 |
| `19f34675d13c7637` | Build failed for graceful-balance | Sun, 5 Jul 2026 |

**Assertion Checks:**

| Check | Result |
|---|---|
| `last_history_id` updated to `10000000` | ❌ |
| Emails exist in DB | ✅ |

**Result: ❌ FAIL**

**Root Causes Identified (diagnosis1.md):**

| # | Cause | Type |
|---|---|---|
| A | `historyId: 10000000` is a fake value far beyond real Gmail history — History API returned no delta | **Test script bug** |
| B | Verification query used `LIMIT 1`, reading `bhaweshjoshi689`'s row, not the row updated by sync | **Test script bug** |
| C | 10-second wait may be insufficient on Railway under load | **Test timing issue** |

**Fixes Applied (2026-07-08):**

| Fix | File | Change |
|---|---|---|
| ✅ Added `[Sync]` checkpoint log after every `last_history_id` update | `services/sync_history_emails.py` | Confirms checkpoint on Railway logs |
| ⏳ Use `actual_last_history_id + 1` from Supabase as webhook historyId | Test script | **Pending — manual update** |
| ⏳ Filter verification query by `email = 'bhaweshcs@gmail.com'` | Test script | **Pending — manual update** |
| ⏳ Increase wait from 10s → 30s before Supabase verification query | Test script | **Pending — manual update** |

**Re-test Procedure:**
1. Query `last_history_id` for `bhaweshcs@gmail.com` from Supabase → call it `real_id`
2. Send webhook with `historyId = real_id + 1`
3. Wait **30 seconds**
4. Query Supabase: `SELECT last_history_id FROM users WHERE email = 'bhaweshcs@gmail.com'`
5. **Expected:** `last_history_id == real_id + 1`

---

## Test 4 — `GET /emails` Returns Emails ✅

| Field | Value |
|---|---|
| Method | `GET` |
| URL | `https://inboxiq-production-ec9c.up.railway.app/emails?page=1&per_page=10` |
| HTTP Status | `200` |
| Emails Returned | `10` |
| `has_more` | `true` |

**Top email:**
```json
{
  "id": "19f31ccc51fc1a01",
  "subject": "Query regarding tally codebrewers hackathon",
  "from": "Internshala Helpdesk <helpdesk@internshala.com>",
  "date": "Sun, 5 Jul 2026 15:51:34 +0530",
  "label": "action"
}
```

**Assertion Checks:**

| Check | Result |
|---|---|
| `status == 200` | ✅ |
| `emails` array present | ✅ |
| `emails` not empty | ✅ |
| `pagination` present with `page`, `per_page`, `has_more` | ✅ |
| All emails have `id, subject, from, date, label` | ✅ |

**Result: ✅ PASS** — Email list works perfectly on Railway, classification labels applied correctly.

---

## Final Verdict

| Metric | Value |
|---|---|
| Tested Against | `https://inboxiq-production-ec9c.up.railway.app` |
| Total Tests Run | 6 |
| **Passed** | **4 / 6** |
| **Failed** | **2 / 6** |
| Railway Backend | ✅ Live and healthy |
| GCP Pub/Sub Webhook (endpoint) | ✅ Accepting and decoding payloads |
| `GET /emails` list + pagination | ✅ Working |
| **Watch Registration (Test 1)** | ❌ Code fix applied — re-test with correct UUID after Railway redeploy |
| **Background Sync checkpoint (Test 3)** | ❌ Code fix applied — re-test with real historyId after Railway redeploy |

---

## Fix Tracking (from fix_implementation.md)

| # | Fix | File Changed | Status |
|---|---|---|---|
| 1 | Add `from datetime import datetime, timezone` | `services/gmail.py` | ✅ Applied |
| 2 | Raise `HTTPException(500)` on watch failure | `routes/email.py` | ✅ Applied |
| 3 | Add `[Sync]` checkpoint logs to all update paths | `services/sync_history_emails.py` | ✅ Applied |
| 4 | Use correct UUID `6bf24bf5-...` in test | Test script / Postman | ⏳ Manual |
| 5 | Use `actual_last_history_id + 1` in webhook payload | Test script | ⏳ Manual |
| 6 | Filter verification query by email, wait 30s | Test script | ⏳ Manual |

> **Next step:** Push to Railway, redeploy, then re-run Test 1 and Test 3 with the corrected test procedures above.
