# InboxIQ — Further GCP Implementation Plan

> Written after endpoint testing is complete.
> This document identifies what is working, what is missing, and the concrete
> next steps to make the real-time GCP pipeline production-ready.

---

## 1. Current State Assessment

### What Is Working (Post-Test)

| Endpoint | Status | Notes |
|---|---|---|
| `GET /emails` | Working | Fetches, syncs, paginates, and returns classified emails |
| `GET /emails/{id}` | Working | Returns single email with on-demand classification |
| `POST /emails/watch` | Working | Registers Gmail watch and saves historyId to Supabase |
| `POST /emails/webhook` | Working | Receives Pub/Sub push, decodes payload, triggers background sync |
| ML classification (batch) | Working | Runs via Ollama (llama3) locally |
| Supabase sync | Working | Emails upserted correctly, page tokens managed |

### What Is Incomplete / Missing

| Gap | Risk Level | Detail |
|---|---|---|
| Watch renewal | CRITICAL | Watch expires every ~7 days with no auto-renewal |
| Webhook auth (no token validation) | HIGH | Any HTTP client can POST to /emails/webhook and trigger sync |
| Single-user hardcoded credentials | HIGH | GMAIL_ACCESS_TOKEN/REFRESH_TOKEN are static in .env |
| Classification not triggered on webhook | MEDIUM | New emails synced via history are never classified |
| GROQ_API_KEY and CLAUDE_API_KEY unused | MEDIUM | Keys configured but no routes or services use them |
| Auth routes stub (empty) | MEDIUM | routes/auth.py has no implementation |
| Ollama runs locally | MEDIUM | ML model cannot work in a deployed / cloud environment |
| No dead-letter / retry handling | MEDIUM | Failed webhook processing is silently dropped |
| No watch status endpoint | LOW | No way to check if watch is active or expiring |
| .env contains secrets in plaintext | HIGH | Tokens and API keys committed/accessible in env file |

---

## 2. Implementation Priorities

### Priority 1 — CRITICAL: Auto Watch Renewal

**Problem:** `users().watch()` expires every ~7 days. If it expires, the entire
real-time pipeline stops silently. The `watch_expiration` column is already stored
in Supabase but nothing reads or acts on it.

**Solution: GCP Cloud Scheduler + a renewal endpoint**

```
Implementation Steps:
─────────────────────
1. Add POST /emails/watch/renew endpoint
   - Queries Supabase for all users where watch_expiration < NOW() + 24h
   - Calls watch_inbox(user_id) for each expiring user
   - Returns renewal summary

2. Create a GCP Cloud Scheduler job
   - Schedule: every 24 hours  (cron: 0 8 * * *)
   - Target: HTTP POST to https://<your-domain>/emails/watch/renew
   - Auth: use OIDC token or a shared secret header

3. Alternatively: trigger renewal inside the webhook itself
   - On every webhook call, check if watch_expiration < 3 days away
   - If yes, call watch_inbox() inline before returning
```

**File to create:** `routes/watch.py`
**File to modify:** `services/gmail.py` — add `renew_expiring_watches()`

---

### Priority 2 — HIGH: Webhook Authentication

**Problem:** `POST /emails/webhook` accepts any request with no validation.
A malicious actor could send fake Pub/Sub messages and trigger expensive sync jobs.

**Solution: Validate the Pub/Sub push JWT**

GCP Pub/Sub push subscriptions include a signed JWT Bearer token in the
`Authorization` header. FastAPI should verify it.

```python
# Proposed addition to routes/email.py

from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

PUBSUB_AUDIENCE = "https://<your-domain>/emails/webhook"

def verify_pubsub_token(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = authorization.split(" ")[1]
    try:
        claim = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            audience=PUBSUB_AUDIENCE
        )
        return claim
    except Exception:
        raise HTTPException(status_code=403, detail="Invalid Pub/Sub token")

@router.post("/emails/webhook")
def gmail_webhook(
    payload: PubSubOuterJson,
    background_tasks: BackgroundTasks,
    claim: dict = Depends(verify_pubsub_token)   # <-- add this
):
    ...
```

**Config required:** Set the Pub/Sub subscription's push endpoint auth to
"Add authentication" with a service account that has the `iam.serviceAccountTokenCreator` role.

---

### Priority 3 — HIGH: Multi-User OAuth Flow

**Problem:** The current system has one hardcoded Gmail user via static tokens
in `.env`. This makes it impossible to onboard any second user.

**Solution: Implement proper OAuth 2.0 flow**

```
Proposed OAuth Flow:
─────────────────────
1. GET /auth/gmail/login
   - Generates a Google OAuth consent URL with gmail.readonly + pubsub scopes
   - Redirects user to Google

2. GET /auth/gmail/callback?code=...
   - Exchanges code for access_token + refresh_token
   - Calls get_or_create_user(email_address)
   - Stores tokens in Supabase users table (encrypted)
   - Calls watch_inbox(user_id) automatically on first login
   - Returns a session JWT to the frontend

3. Per-request credential loading
   - Replace static config.py tokens with DB lookup
   - get_gmail_service(user_id) fetches creds from Supabase
   - Auto-refreshes expired access tokens and persists new token
```

**Files to implement:**
- `routes/auth.py` — currently a stub with no routes
- `services/oauth.py` — NEW: token exchange, refresh, storage
- `services/gmail.py` — modify `get_gmail_service()` to accept `user_id`

**Supabase schema change required:**
```sql
ALTER TABLE users
  ADD COLUMN access_token  TEXT,
  ADD COLUMN refresh_token TEXT,
  ADD COLUMN token_expiry  TIMESTAMPTZ;
```

---

### Priority 4 — MEDIUM: Classify Emails After Webhook Sync

**Problem:** When `sync_history_emails()` upserts new emails from the webhook,
it does NOT trigger ML classification. New emails sit in the `emails` table
unclassified until the frontend calls `GET /emails`.

**Solution: Add classification at end of sync_history_emails**

```python
# Addition to services/sync_history_emails.py (end of function)

if emails_to_store:
    supabase.table("emails").upsert(emails_to_store).execute()

    # Fetch the upserted rows back to get their Supabase UUIDs
    gmail_ids = [e["gmail_id"] for e in emails_to_store]
    rows = supabase.table("emails").select("id, subject, body") \
        .in_("gmail_id", gmail_ids).execute().data

    # Classify in background
    from routes.email import background_classify_emails
    # (already runs in a BackgroundTask context — call directly)
    background_classify_emails(rows)
```

This ensures the inbox is always pre-classified before the user opens the app.

---

### Priority 5 — MEDIUM: Use CLAUDE_API_KEY / GROQ_API_KEY

**Observation:** Both `CLAUDE_API_KEY` and `GROQ_API_KEY` are configured in `.env`
and `config.py` but neither is used anywhere in the codebase.

**Options (pick one):**

#### Option A — Replace Ollama with Groq (Recommended for Cloud)
Groq provides a fast, cloud-hosted LLaMA3 inference endpoint. This removes the
Ollama local server dependency, making deployment possible.

```python
# services/groq_classify.py  (NEW FILE)
from groq import Groq
from config import GROQ_API_KEY

client = Groq(api_key=GROQ_API_KEY)

def classify_email_groq(subject: str, body: str) -> dict:
    response = client.chat.completions.create(
        model="llama3-8b-8192",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": build_user_prompt(subject, body)},
        ],
        temperature=0,
        max_tokens=100,
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)
```

#### Option B — Use Claude for Reasoning / Summaries
Use `CLAUDE_API_KEY` for generating richer email summaries or reply drafts,
while keeping llama3/Groq for tag classification.

---

### Priority 6 — MEDIUM: Dead Letter & Retry Handling

**Problem:** If `sync_history_emails()` crashes (network error, Gmail 429, etc.),
the background task fails silently. The `historyId` checkpoint is never updated,
meaning the next webhook will re-process the same history window, but if
the task errors again, emails will be permanently missed.

**Solution: Structured error handling with Supabase logging**

```python
# Addition to services/sync_history_emails.py

def sync_history_emails(email_address: str, current_history_id: int):
    try:
        _do_sync(email_address, current_history_id)
    except Exception as e:
        # Log failure to a new Supabase table: webhook_errors
        supabase.table("webhook_errors").insert({
            "email_address": email_address,
            "history_id": current_history_id,
            "error": str(e),
            "created_at": datetime.utcnow().isoformat()
        }).execute()
        raise  # Let GCP Pub/Sub retry via its backoff policy
```

**New Supabase table:**
```sql
CREATE TABLE webhook_errors (
  id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  email_address TEXT NOT NULL,
  history_id  BIGINT,
  error       TEXT,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);
```

GCP Pub/Sub will automatically retry the push (up to the subscription's
retry policy) as long as the endpoint returns a non-2xx status.
Currently the webhook always returns 200 even on error — this must be fixed.

---

### Priority 7 — LOW: Watch Status & Admin Endpoint

**Add:** `GET /emails/watch/status`

```python
@router.get("/emails/watch/status")
def watch_status(user_id: str):
    res = supabase.table("users") \
        .select("last_history_id, watch_expiration") \
        .eq("id", user_id).execute()
    if not res.data:
        return {"error": "user not found"}
    user = res.data[0]
    exp = user.get("watch_expiration")
    days_left = None
    if exp:
        from datetime import datetime, timezone
        expiry = datetime.fromisoformat(exp)
        days_left = (expiry - datetime.now(timezone.utc)).days
    return {
        "last_history_id": user.get("last_history_id"),
        "watch_expiration": exp,
        "days_until_expiry": days_left,
        "status": "active" if (days_left and days_left > 0) else "expired"
    }
```

---

## 3. Security Hardening

### Secrets Management
- Move all secrets from `.env` to **GCP Secret Manager** or environment
  variables set at the server/container level.
- Never store OAuth tokens in plaintext — encrypt `access_token` and
  `refresh_token` columns in Supabase at rest.

### CORS
- `main.py` currently allows `http://localhost:3000` only. Before deployment,
  set `allow_origins` to the actual production frontend domain.

### Rate Limiting
- Add rate limiting on `POST /emails/webhook` to prevent abuse even after
  JWT validation is added. Use `slowapi` (Starlette rate limiter).

```python
# requirements.txt addition
slowapi==0.1.9

# main.py
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# routes/email.py — on the webhook handler
@limiter.limit("60/minute")
@router.post("/emails/webhook")
def gmail_webhook(...):
    ...
```

---

## 4. Deployment Readiness

### Local → Cloud Migration Checklist

| Item | Status | Action Needed |
|---|---|---|
| Ollama (local LLM) | NOT deployable | Switch to Groq API (Priority 5) |
| `.env` secrets | Not cloud-safe | Move to GCP Secret Manager |
| Webhook URL | localhost | Deploy backend; update Pub/Sub push endpoint URL |
| Watch renewal | Manual | Add Cloud Scheduler job |
| Multi-user tokens | Hardcoded | Implement OAuth flow (Priority 3) |
| CORS origin | localhost:3000 | Update to production frontend URL |
| Backend hosting | Not deployed | Deploy to Cloud Run (recommended) |

### Recommended Cloud Run Deployment

```dockerfile
# Dockerfile (NEW FILE)
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
```

```bash
# Deploy to Cloud Run
gcloud run deploy inboxiq-backend \
  --source . \
  --region asia-south1 \
  --allow-unauthenticated \
  --set-env-vars GCP_PUB_SUB_TOPIC=projects/oceanic-throne-491015-b1/topics/inbox-updates
```

After deployment, update the Pub/Sub push subscription endpoint:
```
https://inboxiq-backend-<hash>-<region>.a.run.app/emails/webhook
```

---

## 5. Implementation Order (Suggested Sequence)

```
Week 1 — Foundation
────────────────────
[ ] Priority 2: Add Pub/Sub JWT webhook validation
[ ] Priority 6: Add dead letter logging + fix 200-always bug in webhook
[ ] Harden .env: move secrets to GCP Secret Manager

Week 2 — Core Features
────────────────────────
[ ] Priority 3: Implement OAuth flow in routes/auth.py + services/oauth.py
[ ] Priority 5: Replace Ollama with Groq API for cloud-compatible classification
[ ] Priority 4: Auto-classify emails after webhook sync

Week 3 — Reliability & Ops
────────────────────────────
[ ] Priority 1: Add watch renewal endpoint + GCP Cloud Scheduler job
[ ] Priority 7: Add watch status endpoint
[ ] Add rate limiting (slowapi)
[ ] Deploy to GCP Cloud Run
[ ] Update Pub/Sub subscription push URL to Cloud Run endpoint

Week 4 — Polish
─────────────────
[ ] Implement Dockerfile
[ ] CI/CD pipeline (Cloud Build or GitHub Actions)
[ ] Monitor webhook delivery in GCP Pub/Sub console
[ ] Add Supabase RLS (Row Level Security) policies
```

---

## 6. Files To Create / Modify

### New Files

| File | Purpose |
|---|---|
| `routes/watch.py` | Watch status, renewal, and admin endpoints |
| `services/oauth.py` | Google OAuth token exchange and refresh logic |
| `services/groq_classify.py` | Cloud-compatible classification using Groq API |
| `Dockerfile` | Container image for Cloud Run deployment |

### Modified Files

| File | Change |
|---|---|
| `routes/email.py` | Add Pub/Sub JWT validation, fix error response codes |
| `routes/auth.py` | Implement OAuth login + callback routes |
| `services/gmail.py` | Make `get_gmail_service()` accept `user_id`, add `renew_expiring_watches()` |
| `services/sync_history_emails.py` | Add classification trigger + structured error logging |
| `config.py` | Add `GROQ_API_KEY`, `PUBSUB_AUDIENCE`, `FRONTEND_URL` |
| `main.py` | Add rate limiter, update CORS for production |
| `requirements.txt` | Add `slowapi`, `groq`, `google-auth` (already present) |

---

> **Note on CLAUDE_API_KEY and GROQ_API_KEY:**
> Both keys are already configured. The recommended path is to use
> **Groq** for email classification (replaces Ollama, works in cloud)
> and optionally use **Claude** for a premium "Smart Reply" or
> "Email Summary" feature — a natural next product feature for InboxIQ.
