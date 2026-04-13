from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from dotenv import load_dotenv
import os

app = FastAPI()
load_dotenv()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def health_check():
    return {"status": "InboxIQ backend is running"}

@app.get("/emails")
def get_emails():
    if not all([
        os.getenv("GMAIL_ACCESS_TOKEN"),
        os.getenv("GMAIL_REFRESH_TOKEN"),
        os.getenv("CLIENT_ID"),
        os.getenv("CLIENT_SECRET"),
    ]):
        return {"error": "environment variables are missing"}

    creds = Credentials(
        token=os.getenv("GMAIL_ACCESS_TOKEN"),
        refresh_token=os.getenv("GMAIL_REFRESH_TOKEN"),
        client_id=os.getenv("CLIENT_ID"),
        client_secret=os.getenv("CLIENT_SECRET"),
        token_uri="https://oauth2.googleapis.com/token"
    )

   
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    try:
        service = build("gmail", "v1", credentials=creds)

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

        return {"emails": emails}

    except Exception as e:
        return {"error": str(e)}
@app.get("/emails/{email_id}")
def get_email(email_id: str):

    creds = Credentials(
        token=os.getenv("GMAIL_ACCESS_TOKEN"),
        refresh_token=os.getenv("GMAIL_REFRESH_TOKEN"),
        client_id=os.getenv("CLIENT_ID"),
        client_secret=os.getenv("CLIENT_SECRET"),
        token_uri="https://oauth2.googleapis.com/token"
    )

    service = build("gmail", "v1", credentials=creds)

    detail = service.users().messages().get(
        userId="me",
        id=email_id,
        format="full"
    ).execute()

    headers = detail["payload"]["headers"]

    import base64

    body = ""

    parts = detail["payload"].get("parts", [])

    # 1. Try plain text first
    for part in parts:
        if part.get("mimeType") == "text/html" and part.get("body", {}).get("data"):
            body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
            break

    # 2. Fallback to HTML
    if not body:
        for part in parts:
            if part.get("mimeType") == "text/html" and part.get("body", {}).get("data"):
                body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
                break

    return {
        "id": email_id,
        "subject": next((h["value"] for h in headers if h["name"] == "Subject"), "No Subject"),
        "from": next((h["value"] for h in headers if h["name"] == "From"), "Unknown"),
        "date": next((h["value"] for h in headers if h["name"] == "Date"), ""),
        "body": body
    }