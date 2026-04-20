from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from services.parser import extract_body,extract_plain_text
import base64

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