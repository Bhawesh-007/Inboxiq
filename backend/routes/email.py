from fastapi import APIRouter, BackgroundTasks
from services.gmail import fetch_emails, fetch_email_detail, sync_emails_to_supabase,get_gmail_service,get_or_create_user
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

def background_classify_emails(emails_to_classify: list):
    if not emails_to_classify:
        return
    batch_payload = []
    for email in emails_to_classify:
        batch_payload.append({
            "db_uuid": email["id"],
            "subject": email["subject"],
            "body": email["body"] or ""
        })
    try:
        from ml_model.predict import classify_batch
        from database import supabase
        
        print(f"[Background] Starting classification for {len(batch_payload)} emails...")
        classified_data = classify_batch(batch_payload)
        priority_map = {"urgent": 1, "action": 2, "fyi": 3, "spam": 4}
        classifications_to_store = []
        for item in classified_data:
            email_uuid = item["db_uuid"]
            tag = item["tag"]
            reason = item["reason"]
            classifications_to_store.append({
                "email_id": email_uuid,
                "label": tag,
                "priority": priority_map.get(tag, 3),
                "summary": reason
            })
            
        if classifications_to_store:
            supabase.table("classifications").insert(
                classifications_to_store
               
            ).execute()
        print(f"[Background] Classification completed and saved to database.")
    except Exception as e:
        print(f"[Background] Error in classification: {e}")


@router.get("/emails")
def get_emails(background_tasks: BackgroundTasks, page : int =1 , per_page: int = 10):
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
        offset = (page-1)*per_page
        res = supabase.table("emails") \
        .select("*, classifications(*)") \
        .eq("user_id", user_id) \
        .order("date", desc=True) \
        .range(offset, offset + per_page - 1) \
        .execute()
        db_emails = res.data
        
        unclassified_emails = []
        for email in db_emails:
            cls_list = email.get("classifications")
            if not cls_list:
                unclassified_emails.append(email)
                
        if unclassified_emails:
            background_tasks.add_task(background_classify_emails, unclassified_emails)
        
        # 2. Format the data for the frontend and apply NLP classification
        frontend_emails = []
        for email in db_emails:
            # Add NLP classification
           cls_list = email.get("classifications")
           classification = cls_list[0] if cls_list else None
           frontend_emails.append({
            "id": email["gmail_id"],      # frontend expects 'id'
            "subject": email["subject"],
            "from": email["sender"],      # frontend expects 'from'
            "date": email["date"],
            "label": classification["label"] if classification else "unknown",
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
      # Fetch email details along with its classification record
    res = supabase.table("emails") \
        .select("*, classifications(*)") \
        .eq("gmail_id", email_id) \
        .execute()
        
    if not res.data:
        return {"error": "Email not found"}
        
    email_data = res.data[0]
    cls_list = email_data.get("classifications")
    classification = cls_list[0] if cls_list else None
    
    if not classification:
        try:
            from ml_model.predict import classify_email
            result = classify_email(email_data["subject"], email_data["body"] or "")
            priority_map = {"urgent": 1, "action": 2, "fyi": 3, "spam": 4}
            tag = result.get("tag", "fyi")
            reason = result.get("reason", "")
            
            classification = {
                "email_id": email_data["id"],
                "label": tag,
                "priority": priority_map.get(tag, 3),
                "summary": reason
            }
            supabase.table("classifications").insert(classification).execute()
        except Exception as e:
            print(f"Error classifying single email on the fly: {e}")
    
    return {
        "id": email_data["gmail_id"],
        "subject": email_data["subject"],
        "from": email_data["sender"],
        "date": email_data["date"],
        "body": email_data["body"],
        "classification": classification # Passed directly to Next.js Emaildetail
    }