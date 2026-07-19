# Watch Renewal Diagnosis

## Issue Overview
Gmail API `watch()` registrations are designed to expire after 7 days (or sooner). Currently, the application only registers the watch when an explicit `POST /emails/watch` request is made (handled in `routes/email.py` and processed in `services/gmail.py`). There is no automated process (like a cron job or a scheduled task) in place to renew this registration before it expires. As a result, after 7 days, the Gmail Pub/Sub webhook will silently stop receiving notifications for new emails.

## Technical Details
- **Current Registration**: `watch_inbox` (in `services/gmail.py`) properly initiates the watch and saves both `history_id` and `watch_expiration` into the Supabase `users` table.
- **Missing Component**: A background scheduler or cron job is needed to periodically query the `users` table for records where `watch_expiration` is approaching (e.g., within 24 hours) and automatically re-arm the `watch()` for those users.
- **Authentication State**: As noted, the GCP integration requires a valid OAuth refresh token. Before the webhook and automated watch renewal can be fully tested, the OAuth refresh token must be regenerated.

## Recommended Fixes
1. **Implement a Scheduler**: Add a background scheduler (e.g., using APScheduler, Celery, or a cloud-native cron solution like Google Cloud Scheduler triggering an endpoint).
2. **Renewal Endpoint/Task**: Create a task that checks all users in Supabase, identifies those whose `watch_expiration` is less than 24 hours away, and re-invokes the `watch_inbox` logic using their refreshed credentials.
3. **Regenerate Refresh Token**: Run `get_refresh_token.py` to obtain a valid OAuth refresh token so the integration can be verified and the `watch_inbox` can authenticate successfully.

## Next Steps
- Re-run `get_refresh_token.py` to restore OAuth functionality.
- Implement the automated background renewal mechanism.
