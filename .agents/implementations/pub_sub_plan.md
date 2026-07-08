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