from os import get_terminal_size
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


def fetch_emails(page_token: str=None):
    try:
        service = get_gmail_service()
    
        req_kwargs = {
            "userId": "me",
            "maxResults": 10
        }
        if page_token:
            req_kwargs["pageToken"] = page_token
            
        results = service.users().messages().list(**req_kwargs).execute()
        
        next_page_token = results.get("nextPageToken")
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
    
        return emails, next_page_token
    except Exception as e:
        print(f"Error fetching emails: {e}")
        return [], None


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


# Service to store fetched emails in Supabase

def sync_emails_to_supabase(page_token: str=None):
    """Fetch recent emails and upsert them into the Supabase `emails` table.

    Ensures the related user exists before upserting email rows.
    """
    # Ensure the user row exists first
    service = get_gmail_service()
    profile = service.users().getProfile(userId="me", fields="emailAddress").execute()
    email_address = profile.get("emailAddress")
    res = supabase.table("users").select("id").eq("email",email_address).execute()
    if res.data:
        user_id = res.data[0]["id"]
    else:
        print("No user found")
        return None,None,None
    emails_to_store = []
    raw_emails ,next_page_token= fetch_emails(page_token)
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
    if(emails_to_store):
        supabase.table("emails").upsert(emails_to_store).execute()
    else:
        print("No emails to store")
    return emails_to_store , next_page_token,user_id;
        
   
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
