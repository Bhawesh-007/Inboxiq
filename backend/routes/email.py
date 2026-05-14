from fastapi import APIRouter
from services.gmail import fetch_emails, fetch_email_detail, sync_emails_to_supabase
from services.nlp import classify_email
from services.parser import extract_body, extract_plain_text
import base64
from config import (
    GMAIL_ACCESS_TOKEN,
    GMAIL_REFRESH_TOKEN,
    CLIENT_ID,
    CLIENT_SECRET
)

router = APIRouter()


@router.get("/emails")
def get_emails():
    if not all([
        GMAIL_ACCESS_TOKEN,
        GMAIL_REFRESH_TOKEN,
        CLIENT_ID,
        CLIENT_SECRET
    ]):
        return {"error": "environment variables are missing"}

    try:
        # 1. This hits Gmail API, cleans data, and saves to Supabase
        # We must assign the result to a variable!
        synced_emails = sync_emails_to_supabase()
        
        # 2. Format the data for the frontend and apply NLP classification
        frontend_emails = []
        for email in synced_emails:
            # Add NLP classification
            label = classify_email(
                subject=email["subject"],
                sender=email["sender"]
            )
            
            frontend_emails.append({
                "id": email["gmail_id"],      # frontend expects 'id'
                "subject": email["subject"],
                "from": email["sender"],      # frontend expects 'from'
                "date": email["date"],
                "label": label,
                "body": email["body"]
            })
            
        return {"emails": frontend_emails}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}


@router.get("/emails/{email_id}")
def get_email(email_id: str):
    return fetch_email_detail(email_id)