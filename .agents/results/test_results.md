# InboxIQ — Pub/Sub API Test Results (Railway Production)

**Date:** 2026-07-08 (Re-test after fix deployment) | **Tested Against:** `https://inboxiq-production-ec9c.up.railway.app` | **Overall: ⚠️ 5/6 PASSED**

> **Fix deployment:** Code fixes from `fix_implementation.md` deployed to Railway. Re-test run on 2026-07-08T07:18 UTC.

---

## Summary

| # | Test | Method | Endpoint | HTTP | Result |
|---|---|---|---|---|---|
| 0 | Health Check | `GET` | `/` | `200` | ✅ PASS |
| Pre | Supabase User Lookup | `INTERNAL` | `supabase.users` | `—` | ✅ PASS |
| 1 | Register Gmail Watch | `POST` | `/emails/watch` | `200` | ✅ PASS ← **Fixed** |
| 2 | Simulate Pub/Sub Webhook Push | `POST` | `/emails/webhook` | `200` | ✅ PASS |
| 3 | Background Sync Verification | `INTERNAL` | `supabase.users + supabase.emails` | `—` | ❌ FAIL (new root cause found) |
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
| Method | `INTERNAL` (Supabase REST API) |
| Table | `supabase.users` |
| Query | `SELECT id, email, last_history_id, watch_expiration WHERE email = 'bhaweshcs@gmail.com'` |
| Result | ⚠️ **0 rows returned** — `bhaweshcs@gmail.com` does not exist in the `users` table |
| Fallback | Only user present: `bhaweshjoshi689@gmail.com` (UUID: `e6a49a7c-cf70-4810-ac4f-d2c3d2fa9bd4`) |

> **Finding:** `bhaweshcs@gmail.com` (UUID: `6bf24bf5-8012-40c0-af85-91bfb4a0ac06`) was assumed to exist in Supabase but was never inserted. The `GET /emails` endpoint auto-creates user rows via `get_or_create_user()` — but only for `bhaweshjoshi689@gmail.com` (the account whose Gmail tokens are in the env). The UUID `6bf24bf5-...` does not exist in Supabase.

---

## Test 1 — Register Gmail Watch (`POST /emails/watch`) ✅ FIXED

| Field | Value |
|---|---|
| Method | `POST` |
| URL | `https://inboxiq-production-ec9c.up.railway.app/emails/watch?user_id=6bf24bf5-8012-40c0-af85-91bfb4a0ac06` |
| HTTP Status | `200` |
| Response | `{"status": "watch started", "data": {"historyId": "965186", "expiration": "1784099907082"}}` |

**Assertion Checks:**

| Check | Result |
|---|---|
| `status == 200` | ✅ |
| `response.status == "watch started"` | ✅ |
| `response.data.historyId` present | ✅ — value: `965186` |
| `response.data.expiration` present | ✅ — value: `1784099907082` |

**Result: ✅ PASS**

**Fix confirmed:** The `from datetime import datetime, timezone` import fix resolved the `NameError`. `watch_inbox()` now runs to completion and returns a valid watch response from the Gmail API.

> ⚠️ **Side note:** The Supabase update inside `watch_inbox()` (`UPDATE users SET last_history_id WHERE id = 6bf24bf5-...`) silently does nothing because UUID `6bf24bf5-...` does not exist in the `users` table. The Gmail watch itself is active, but the checkpoint was not persisted to DB. This is a data setup gap, not a code bug.

---

## Test 2 — Simulate Pub/Sub Webhook Push (`POST /emails/webhook`) ✅

Payload constructed using `historyId = 965186 + 1 = 965187` (real value from Test 1).

Base64 encoded: `eyJlbWFpbEFkZHJlc3MiOiJiaGF3ZXNoY3NAZ21haWwuY29tIiwiaGlzdG9yeUlkIjoiOTY1MTg3In0=`

Decoded: `{"emailAddress":"bhaweshcs@gmail.com","historyId":"965187"}`

| Field | Value |
|---|---|
| Method | `POST` |
| URL | `https://inboxiq-production-ec9c.up.railway.app/emails/webhook` |
| HTTP Status | `200` |
| `message.data` (decoded) | `{"emailAddress": "bhaweshcs@gmail.com", "historyId": "965187"}` |
| `message.messageId` | `test-msg-railway-002` |
| Response | `{"status": "accepted"}` |

**Assertion Checks:**

| Check | Result |
|---|---|
| `status == 200` | ✅ |
| `response.status == "accepted"` | ✅ |
| No `error` field in response | ✅ |

**Result: ✅ PASS** — Webhook decoded and accepted the realistic payload. Background sync triggered for `bhaweshcs@gmail.com`.

---

## Test 3 — Background Sync Supabase Verification ❌

Waited **30 seconds** after webhook push, then queried Supabase for `bhaweshcs@gmail.com` specifically.

| Field | Value |
|---|---|
| `historyId` sent in webhook | `965187` |
| Query | `SELECT last_history_id FROM users WHERE email = 'bhaweshcs@gmail.com'` |
| Rows returned | `0` — user does not exist in `users` table |
| `last_history_id` updated | ❌ — impossible, no row to update |
| Emails exist in DB (any user) | ✅ yes (for `bhaweshjoshi689@gmail.com`) |

**Assertion Checks:**

| Check | Result |
|---|---|
| `last_history_id` updated to `965187` | ❌ |
| `bhaweshcs@gmail.com` row exists in `users` | ❌ |
| Emails exist in DB | ✅ (for the other user) |

**Result: ❌ FAIL**

**Root Cause (new — not a code bug):**

`sync_history_emails` starts with:
```python
res = supabase.table("users").select("id", "last_history_id").eq("email", email_address).execute()
if not res.data:
    print(f"User with email {email_address} not found.")
    return
```

`bhaweshcs@gmail.com` is not in the `users` table — only `bhaweshjoshi689@gmail.com` is. So `sync_history_emails` returns immediately after "User not found." The `historyId` is never checkpointed.

**Why is `bhaweshcs@gmail.com` missing from Supabase?**

The `GET /emails` endpoint calls `get_or_create_user(email_address)` using the Gmail profile of the env-var token owner. The env-var tokens on Railway belong to `bhaweshjoshi689@gmail.com` — so `get_or_create_user` always creates/finds **that** user. `bhaweshcs@gmail.com` and UUID `6bf24bf5-...` were assumed to exist from a previous session but were never inserted.

**Fix Required:**

| Fix | Action |
|---|---|
| Insert `bhaweshcs@gmail.com` user row | Run `INSERT INTO users (id, email, name) VALUES ('6bf24bf5-8012-40c0-af85-91bfb4a0ac06', 'bhaweshcs@gmail.com', 'bhaweshcs')` in Supabase, **OR** update Railway env-var tokens to use `bhaweshcs@gmail.com` credentials so `get_or_create_user` creates it automatically |
| Clarify which Gmail account the system is actually connected to | Railway env-var tokens currently belong to `bhaweshjoshi689@gmail.com` — confirm intended account |

---

## Test 4 — `GET /emails` Returns Emails ✅

| Field | Value |
|---|---|
| Method | `GET` |
| URL | `https://inboxiq-production-ec9c.up.railway.app/emails?page=1&per_page=10` |
| HTTP Status | `200` |
| Emails Returned | `10` |
| `has_more` | `true` |

**Top 3 emails:**

| Gmail ID | Subject | From | Label |
|---|---|---|---|
| `19f31ccc51fc1a01` | Query regarding tally codebrewers hackathon | Internshala Helpdesk | `action` |
| `19f32e32e9a3a6bf` | "Cleaning services" | Reddit | `fyi` |
| `19f34675d13c7637` | Build failed for graceful-balance | Railway | `action` |

**Assertion Checks:**

| Check | Result |
|---|---|
| `status == 200` | ✅ |
| `emails` array present | ✅ |
| `emails` not empty | ✅ — 10 emails returned |
| `pagination` present with `page`, `per_page`, `has_more` | ✅ |
| All emails have `id, subject, from, date, label` | ✅ |
| `label` values are valid (`action`, `fyi`, `spam`, `urgent`) | ✅ |

**Result: ✅ PASS** — Email list, pagination, and ML classification all working correctly on Railway.

---

## Final Verdict

| Metric | Value |
|---|---|
| Tested Against | `https://inboxiq-production-ec9c.up.railway.app` |
| Test Run Date | 2026-07-08T07:18 UTC (post-fix redeploy) |
| Total Tests Run | 6 |
| **Passed** | **5 / 6** |
| **Failed** | **1 / 6** |
| Railway Backend | ✅ Live and healthy |
| GCP Pub/Sub Webhook (endpoint) | ✅ Accepting and decoding payloads |
| `GET /emails` list + pagination | ✅ Working |
| **Watch Registration (Test 1)** | ✅ **FIXED** — `datetime` import fix confirmed working |
| **Background Sync checkpoint (Test 3)** | ❌ `bhaweshcs@gmail.com` not in `users` table — data setup gap |

---

## Remaining Action Item

| # | Issue | Fix | Owner |
|---|---|---|---|
| 1 | `bhaweshcs@gmail.com` missing from Supabase `users` table | Insert the row manually in Supabase dashboard: `INSERT INTO users (id, email, name) VALUES ('6bf24bf5-8012-40c0-af85-91bfb4a0ac06', 'bhaweshcs@gmail.com', 'bhaweshcs')` — then re-run Test 1 (watch will checkpoint) and Test 3 (sync will find the user) | Manual / Supabase dashboard |

> **Expected after fix:** Test 3 will pass and overall score will be **6/6 PASS**.
