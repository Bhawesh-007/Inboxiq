from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from services.parser import extract_body,extract_plain_text,extract_headings_and_paragraphs
import base64
from database import supabase
from config import (
    GMAIL_ACCESS_TOKEN,
    GMAIL_REFRESH_TOKEN,
    CLIENT_ID,
    CLIENT_SECRET
)


def get_gmail_service():
    creds = Credentials(
        token=GMAIL_ACCESS_TOKEN,
        refresh_token=GMAIL_REFRESH_TOKEN,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token"
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    return build("gmail", "v1", credentials=creds)


def fetch_emails():
    try:
        service = get_gmail_service()
    
        results = service.users().messages().list(
            userId="me",
            maxResults=10
        ).execute()
    
        messages = results.get("messages", [])
        emails = []
    
        for msg in messages:
            detail = service.users().messages().get(
                userId="me",
                id=msg["id"],
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"]
            ).execute()
    
            headers = detail["payload"]["headers"]
    
            emails.append({
                "id": msg["id"],
                "subject": next((h["value"] for h in headers if h["name"] == "Subject"), "No Subject"),
                "from": next((h["value"] for h in headers if h["name"] == "From"), "Unknown"),
                "date": next((h["value"] for h in headers if h["name"] == "Date"), ""),
            })
    
        return emails
    except Exception as e:
        print(f"Error fetching emails: {e}")
        return []


def fetch_email_detail(email_id: str):
    service = get_gmail_service()

    detail = service.users().messages().get(
        userId="me",
        id=email_id,
        format="full"
    ).execute()

    payload = detail.get("payload", {})
    headers = payload.get("headers", [])

    
    body = extract_body(payload)

    
    if not body:
        body = extract_plain_text(payload)
    return {
        "id": email_id,
        "subject": next((h["value"] for h in headers if h["name"] == "Subject"), "No Subject"),
        "from": next((h["value"] for h in headers if h["name"] == "From"), "Unknown"),
        "date": next((h["value"] for h in headers if h["name"] == "Date"), ""),
        "body": body
    }
def ensure_user_exists(user_id: str) -> None:
    """
    Upsert a minimal user row so that foreign‑key constraints are satisfied.
    Adjust the payload if your `users` table requires extra columns.
    """
    # Minimal user payload; add more fields if required by your schema
    payload = {"id": user_id}
    supabase.table("users").upsert(payload, on_conflict="id").execute()

# Service to store fetched emails in Supabase

def sync_emails_to_supabase(user_id: str):
    """Fetch recent emails and upsert them into the Supabase `emails` table.

    Ensures the related user exists before upserting email rows.
    """
    # Ensure the user row exists first
    ensure_user_exists(user_id)

    full_email_details: list[dict] = []
    raw_emails = fetch_emails()
    for email in raw_emails:
        detail = fetch_email_detail(email["id"])
        body_text = detail.get("body") or ""
        full_email_details.append({
            "user_id": user_id,
            "gmail_id": detail["id"],
            "subject": detail["subject"],
            "sender": detail["from"],
            "body": body_text[:3000],
        })

    if full_email_details:
        response = (
            supabase.table("emails")
            .upsert(full_email_details, on_conflict="gmail_id")
            .execute()
        )
        return response
    return []
def export_emails_to_file(user_id: str, file_path: str = "data.txt") -> None:
    """Fetch emails for the given user and write them to a local JSON file.

    The file will be created/overwritten in the same directory as this module.
    Each email is stored as a JSON object in a list.
    """
    # Ensure the user exists (optional, reuse existing helper)
    # ensure_user_exists(user_id)  # Skipped for file export; user may not exist in Supabase

    emails_to_store = []
    raw_emails = fetch_emails()
    for email in raw_emails:
        detail = fetch_email_detail(email["id"])  # Get full detail
        raw_body = detail.get("body") or ""
        cleaned_parts = extract_headings_and_paragraphs(raw_body)
        cleaned_body = "\n".join(cleaned_parts)
        emails_to_store.append({
            "user_id": user_id,
            "gmail_id": detail["id"],
            "subject": detail["subject"],
            "sender": detail["from"],
            "date": detail.get("date", ""),
            "body": cleaned_body,
        })

    # Write JSON to file
    import json, os
    full_path = os.path.join(os.path.dirname(__file__), file_path)
    with open(full_path, "w", encoding="utf-8") as f:
        json.dump(emails_to_store, f, ensure_ascii=False, indent=2)
    print(f"Exported {len(emails_to_store)} emails to {full_path}")
