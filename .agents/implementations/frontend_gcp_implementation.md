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