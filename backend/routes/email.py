from fastapi import APIRouter
from services.gmail import fetch_emails, fetch_email_detail, sync_emails_to_supabase,get_gmail_service,get_or_create_user
from services.nlp import classify_email
from services.parser import extract_body, extract_plain_text
from pagination.paginator import EmailPaginator
from services.gmail import get_gmail_service
from database import supabase
import base64
from config import (
    GMAIL_ACCESS_TOKEN,
    GMAIL_REFRESH_TOKEN,
    CLIENT_ID,
    CLIENT_SECRET
)

router = APIRouter()


@router.get("/emails")
def get_emails(page : int =1 , per_page: int = 10):
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
        service = get_gmail_service()#this is for talking to gmail api
        profile = service.users().getProfile(userId="me" , fields = "emailAddress").execute()
        email_address = profile.get("emailAddress")
       
        user_id = get_or_create_user(email_address) #this is for grabbing the uuid from the user table
        if not user_id:
            return {"error": "user not found"}
        gmail_token = None
        if page>1:
            gmail_token = EmailPaginator.get_token_for_page(user_id, page)
            if not gmail_token:
                page = 1
        page_token_exists = supabase.table("page_tokens").select("token").eq("user_id",user_id).eq("page",page).execute().data
        next_page_token = None
        if page_token_exists:
            next_page_token = page_token_exists[0]["token"]

        if not page_token_exists:
            synced_emails , next_page_token,_ = sync_emails_to_supabase(page_token = gmail_token)
        if next_page_token:
            EmailPaginator.save_next_page_token(user_id, page, next_page_token)
        db_emails = EmailPaginator.get_emails_from_db(user_id, page, per_page)
        
        # 2. Format the data for the frontend and apply NLP classification
        frontend_emails = []
        for email in db_emails:
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
            
        return {"emails": frontend_emails,
         "pagination": {
                "page": page,
                "per_page": per_page,
                "has_more": next_page_token is not None or len(frontend_emails) == per_page
            }
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}


@router.get("/emails/{email_id}")
def get_email(email_id: str):
    return fetch_email_detail(email_id)