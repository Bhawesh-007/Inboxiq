from googleapiclient.errors import HttpError
from services.parser import extract_headings_and_paragraphs
from email.utils import parsedate_to_datetime
from database import supabase
from services.gmail import (
    get_gmail_service,
    sync_emails_to_supabase,
    fetch_email_detail
)


def sync_history_emails(email_address: str, current_history_id: int):
    """
    Fetches only the new emails since the user's last synchronized history ID.
    """
    # 1. Retrieve the user from Supabase
    res = supabase.table("users").select("id", "last_history_id").eq("email", email_address).execute()
    if not res.data:
        print(f"User with email {email_address} not found.")
        return
        
    user = res.data[0]
    user_id = user["id"]
    last_history_id = user.get("last_history_id")
    
    service = get_gmail_service()
    new_message_ids = set()
    
    # 2. If we have a stored history ID, try to fetch only incremental changes
    if last_history_id:
        try:
            page_token = None
            while True:
                history_res = service.users().history().list(
                    userId="me",
                    startHistoryId=last_history_id,
                    pageToken=page_token
                ).execute()
                
                histories = history_res.get("history", [])
                for history_item in histories:
                    # We only care about new messages added to the mailbox
                    added_messages = history_item.get("messagesAdded", [])
                    for added in added_messages:
                        msg_id = added.get("message", {}).get("id")
                        if msg_id:
                            new_message_ids.add(msg_id)
                
                page_token = history_res.get("nextPageToken")
                if not page_token:
                    break
                    
        except HttpError as error:
            # If history ID is too old/expired (usually >7 days), Gmail returns 404/410/400
            if error.resp.status in [400, 404, 410]:
                print(f"[Sync] History ID expired/invalid. Falling back to full sync.")
                # Trigger a standard full/recent sync instead of failing
                sync_emails_to_supabase()
                # Update history ID to current
                supabase.table("users").update({"last_history_id": current_history_id}).eq("id", user_id).execute()
                print(f"[Sync] Checkpointed last_history_id={current_history_id} for user_id={user_id} (fallback path)")
                return
            else:
                raise error
    else:
        # If no last history ID is stored, do a fresh sync
        sync_emails_to_supabase()
        supabase.table("users").update({"last_history_id": current_history_id}).eq("id", user_id).execute()
        print(f"[Sync] Checkpointed last_history_id={current_history_id} for user_id={user_id} (fresh sync path)")
        return
    # 3. If there are new messages, fetch details and upsert to Supabase
    if new_message_ids:
        emails_to_store = []
        for msg_id in new_message_ids:
            try:
                # Reuse your existing detail-fetching function
                detail = fetch_email_detail(msg_id)
                raw_body = detail.get("body") or ""
                cleaned_parts = extract_headings_and_paragraphs(raw_body)
                cleaned_body = "\n".join(cleaned_parts)
                
                raw_date = detail.get("date", "")
                parsed_date = raw_date
                try:
                    parsed_date = parsedate_to_datetime(raw_date).isoformat()
                except Exception:
                    pass
                
                emails_to_store.append({
                    "user_id": user_id,
                    "gmail_id": detail["id"],
                    "subject": detail["subject"],
                    "sender": detail["from"],
                    "date": parsed_date,
                    "body": cleaned_body,
                })
            except Exception as e:
                print(f"Error fetching detail for message {msg_id}: {e}")
        
        if emails_to_store:
            supabase.table("emails").upsert(emails_to_store).execute()
            print(f"Synced {len(emails_to_store)} new emails from history update.")
            
            # Optional: Trigger your background classifier on these new emails
            # from routes.email import background_classify_emails
            # background_classify_emails(emails_to_store)
    # 4. Save the current history ID as the new checkpoint
    supabase.table("users").update({"last_history_id": current_history_id}).eq("id", user_id).execute()
    print(f"[Sync] Checkpointed last_history_id={current_history_id} for user_id={user_id}")
    