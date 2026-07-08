# InboxIQ — Working Prototype Implementation Plan

> **Goal:** New emails land in Gmail → appear in Supabase → get classified → show up in the frontend with label and summary.
> This document focuses ONLY on achieving that end-to-end working prototype.
> Security and optimization are out of scope here.

---

## The Target Flow (What We Are Building)

```
New Email Arrives in Gmail
        |
        v
GCP Pub/Sub pushes to POST /emails/webhook
        |
        v
Backend decodes payload, runs sync_history_emails()
        |
        v
New email rows upserted into Supabase `emails` table
        |
        v  <-- THIS STEP IS CURRENTLY MISSING
background_classify_emails() triggered automatically
        |
        v
Classification row inserted into Supabase `classifications` table
        |
        v
Frontend GET /emails returns email + label + summary  <-- THIS STEP HAS A BUG
        |
        v
User sees new email in the list with tag badge + summary in detail view
```

---

## Current State Snapshot

### What Is Already Working

| Part | Status |
|---|---|
| Gmail watch registered via POST /emails/watch | Done |
| GCP Pub/Sub pushing to POST /emails/webhook | Done |
| Webhook decodes Pub/Sub payload | Done |
| sync_history_emails() fetches new emails via history.list | Done |
| New emails upserted into Supabase emails table | Done |
| GET /emails reads from Supabase + returns classifications | Done |
| Frontend Emaillist.jsx renders email list with label badge | Done |
| Frontend Emaildetail.jsx renders summary from classification | Done |

### What Is Broken / Missing (Prototype Blockers)

| # | Problem | Where | Effect |
|---|---|---|---|
| B1 | Classification NOT triggered after webhook sync | sync_history_emails.py | New emails arrive in Supabase with no classification ever |
| B2 | inbox/page.jsx does not wire up EmailDetail | inbox/page.jsx line 12 | Clicking an email shows nothing — detail panel is a comment |
| B3 | Emaillist.jsx not passed onEmailClick in inbox/page.jsx | inbox/page.jsx line 9 | Email clicks are not propagated up |
| B4 | Frontend has no refresh mechanism after new emails arrive | Emaillist.jsx | User must manually reload to see new emails |

---

## Fix 1 — Trigger Classification After Webhook Sync (Backend)

**File:** `backend/services/sync_history_emails.py`

**Problem:** After emails are upserted at line 99, nothing calls `background_classify_emails()`.
New emails sit in the database forever with no label or summary.

**What to add** at the end of `sync_history_emails()`, right after the upsert:

```python
# After:  supabase.table("emails").upsert(emails_to_store).execute()

# Step: fetch back the upserted rows to get their Supabase UUIDs
gmail_ids = [e["gmail_id"] for e in emails_to_store]
rows_res = supabase.table("emails") \
    .select("id, subject, body") \
    .in_("gmail_id", gmail_ids) \
    .execute()
rows_for_classification = rows_res.data

# Step: classify each new email inline (sync — we are already in a background task)
if rows_for_classification:
    batch_payload = [
        {
            "db_uuid": r["id"],
            "subject": r["subject"],
            "body": r["body"] or ""
        }
        for r in rows_for_classification
    ]
    from ml_model.predict import classify_batch
    classified = classify_batch(batch_payload)

    priority_map = {"urgent": 1, "action": 2, "fyi": 3, "spam": 4}
    classifications_to_store = [
        {
            "email_id": item["db_uuid"],
            "label":    item["tag"],
            "priority": priority_map.get(item["tag"], 3),
            "summary":  item["reason"]
        }
        for item in classified
    ]
    supabase.table("classifications").insert(classifications_to_store).execute()
    print(f"[Webhook Sync] Classified {len(classifications_to_store)} new emails.")
```

**Why this works:** `sync_history_emails` is already called inside a FastAPI
`BackgroundTask`, so it is already off the main thread. We can safely run
`classify_batch()` synchronously inside it without blocking any HTTP response.

---

## Fix 2 — Wire Up EmailDetail in the Inbox Page (Frontend)

**File:** `frontend/inbox-iq/app/inbox/page.jsx`

**Problem:** `<Emaillist />` has an `onEmailClick` prop but it is not passed.
`<Emaildetail />` component exists but is never rendered — it is replaced with
a comment on line 12. Clicking any email does nothing visible.

**Replace the entire file with:**

```jsx
"use client"
import React, { useState } from 'react'
import Sidebar from '../Components/Sidebar'
import Emaillist from '../Components/Emaillist'
import Emaildetail from '../Components/Emaildetail'

export default function InboxPage() {
  const [selectedEmailId, setSelectedEmailId] = useState(null)

  return (
    <div style={{ display: "flex", height: "100vh", background: "#0a0a0a" }}>
      <Sidebar />
      <div style={{ width: "340px", background: "#0d0d0d", borderRight: "1px solid #1e1e1e", color: "#fff" }}>
        <Emaillist onEmailClick={(id) => setSelectedEmailId(id)} />
      </div>
      <div style={{ flex: 1, background: "#0a0a0a", overflow: "auto" }}>
        <Emaildetail emailId={selectedEmailId} />
      </div>
    </div>
  )
}
```

**What this fixes:**
- Passes `onEmailClick` down into `Emaillist` so `handleClick` actually works
- Renders `<Emaildetail emailId={selectedEmailId} />` in the right panel
- Clicking an email now updates `selectedEmailId` → triggers the `useEffect`
  in `Emaildetail` → fetches `GET /emails/{emailId}` → shows subject, body, summary

---

## Fix 3 — Auto-Refresh the Email List After New Emails Arrive (Frontend)

**File:** `frontend/inbox-iq/app/Components/Emaillist.jsx`

**Problem:** The `useEffect` only fires when `page` changes. If a new email
arrives via webhook, the user must manually reload the browser to see it.

**Add a polling interval** that re-fetches every 30 seconds:

```jsx
// Change the useEffect in Emaillist.jsx from:
useEffect(() => {
  fetch(`http://localhost:5003/emails?page=${page}&per_page=${per_page}`)
  ...
}, [page]);

// To:
useEffect(() => {
  const loadEmails = () => {
    fetch(`http://localhost:5003/emails?page=${page}&per_page=${per_page}`)
      .then((res) => {
        if (!res.ok) throw new Error('Failed to fetch emails');
        return res.json();
      })
      .then((data) => {
        if (data.error) {
          setError(data.error);
          setEmails([]);
        } else {
          setEmails(data.emails || []);
          setHasMore(data.pagination?.has_more || false);
          setError(null);
        }
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setEmails([]);
        setLoading(false);
      });
  };

  loadEmails(); // run immediately

  const interval = setInterval(loadEmails, 30000); // re-fetch every 30s
  return () => clearInterval(interval); // cleanup on unmount or page change
}, [page]);
```

**Why 30 seconds:** Fast enough to feel responsive for a prototype. The webhook
lands in ~1-3 seconds; classification takes ~5-15 seconds via Ollama.
So the user will see the new email in at most ~45 seconds with no page reload.

---

## End-to-End Test Checklist

After applying all three fixes, verify the complete flow manually:

```
Step 1: Start backend
  uvicorn main:app --reload --port 5003

Step 2: Confirm watch is active
  POST http://localhost:5003/emails/watch?user_id=<your-user-uuid>
  Expected: {"status": "watch started", "data": {"historyId": "...", "expiration": "..."}}

Step 3: Confirm webhook is reachable by Pub/Sub
  - If local: run ngrok http 5003 to get a public HTTPS URL
  - Update Pub/Sub push subscription endpoint to: https://<ngrok-url>/emails/webhook

Step 4: Start frontend
  cd frontend/inbox-iq && npm run dev   (port 3000)

Step 5: Open http://localhost:3000/inbox
  - You should see your existing emails with label badges
  - Click any email -- the right panel should now show subject, body, and AI summary

Step 6: Send a test email to your Gmail account

Step 7: Watch the backend terminal:
  Expected logs within ~5 seconds:
    [Webhook] Received notification for user@gmail.com with History ID: XXXXX
    [Background Task started]
    Synced 1 new emails from history update.
    Classifying 1/1: <subject>...
    [Webhook Sync] Classified 1 new emails.

Step 8: Wait up to 30 seconds (one poll cycle)
  - The new email should appear at the top of the list in the frontend
  - It should have a colored label badge (urgent / action / fyi / spam)
  - Clicking it should show the AI summary in the detail panel
```

---

## Summary of Changes

| File | Type | Change |
|---|---|---|
| `backend/services/sync_history_emails.py` | Modify | Add classify_batch() call after upsert |
| `frontend/inbox-iq/app/inbox/page.jsx` | Modify | Wire up EmailDetail + pass onEmailClick |
| `frontend/inbox-iq/app/Components/Emaillist.jsx` | Modify | Add 30-second polling interval |

**That is 3 file changes total to get the full prototype working.**

---

## What Comes After The Prototype

Once the above is working end-to-end, the natural next steps are:
- Replace 30s polling with Supabase Realtime subscription (instant updates)
- Add watch auto-renewal so the pipeline does not expire after 7 days
- Implement proper multi-user OAuth instead of hardcoded .env tokens
