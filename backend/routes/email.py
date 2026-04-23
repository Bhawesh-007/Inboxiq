from fastapi import APIRouter
from services import fetch_emails, fetch_email_detail
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
        emails = fetch_emails()
        for email in emails:
            label = classify_email(
                subject=email["subject"],
                sender=email["from"]
            )
            email["label"] = label
        return {"emails": emails}
    except Exception as e:
        return {"error": str(e)}


@router.get("/emails/{email_id}")
def get_email(email_id: str):
    return fetch_email_detail(email_id)