# Diagnosis: Webhook Authentication Vulnerability

## Overview
The `POST /emails/webhook` endpoint defined in `backend/routes/email.py` (line 189) currently processes incoming requests without any authentication or origin verification. This means it accepts any payload that matches the `PubSubOuterJson` schema.

## Vulnerability Details
The current implementation:
```python
@router.post("/emails/webhook")
def gmail_webhook(payload:PubSubOuterJson , background_tasks:BackgroundTasks):
    try:
        decoded_data = base64.b64decode(payload.message.data).decode('utf-8')
        data_json = json.loads(decoded_data)
        email_address = data_json.get("emailAddress")
        history_id = data_json.get("historyId")
        #triggering the background sync task
        background_tasks.add_task(sync_history_emails, email_address, int(history_id))
        
        return {"status" : "accepted"}
    # ...
```
1.  **No Origin Verification**: The endpoint does not verify that the request actually originated from Google Cloud Pub/Sub. 
2.  **Unvalidated Inputs**: It blindly trusts the `emailAddress` and `historyId` provided in the base64-encoded payload.

## Threat Model & Impact
If this webhook URL is internet-facing and discovered by a malicious actor, they can send forged POST requests to it.

*   **Resource Exhaustion / Denial of Service (DoS)**: An attacker could write a script to continuously send payloads with various email addresses and history IDs. This would enqueue a massive amount of `sync_history_emails` background tasks, potentially overloading the server's CPU/memory and rapidly exhausting Gmail API quotas.
*   **Logical Flaws & Sync Disruption**: Sending spoofed `historyId` values (e.g., extremely large numbers or invalid states) for a user's `emailAddress` could disrupt the incremental sync logic, forcing unintended full syncs or leaving the user's local database in an inconsistent state.

## Recommended Fix
To properly secure this endpoint, you should implement Push Subscription Authentication:

1.  **OIDC Token Verification (Recommended)**: 
    *   Configure the GCP Pub/Sub push subscription to enable authentication. GCP will then attach an OpenID Connect (OIDC) JWT token in the `Authorization: Bearer <token>` header of every push request.
    *   Update the FastAPI route to extract this token and verify its signature using Google's public certificates.
    *   Verify that the token's `aud` (audience) claim matches your webhook URL.
    
2.  **Shared Secret / Token (Alternative)**:
    *   If configuring OIDC is too complex for the current stage, you can add a secret token query parameter to the webhook URL registered in GCP (e.g., `https://your-domain.com/emails/webhook?token=SECURE_RANDOM_STRING`).
    *   Update the FastAPI endpoint to require and validate this `token` query parameter before processing the payload.

> [!CAUTION]
> It is highly recommended to implement one of the above authentication mechanisms before exposing the webhook in a production environment.
