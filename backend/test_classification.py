import sys
import os
from database import supabase

# Add the ml_model directory to the path so we can import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "ml_model"))

# Set stdout/stderr to use utf-8 to prevent charmap print crashes on Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

from predict import classify_email

def run_test():
    print("Step 1: Fetching a sample email from Supabase...")
    try:
        res = supabase.table("emails").select("*").limit(1).execute()
        if not res.data:
            print("No emails found in the database. Please seed the database first.")
            return
        
        email = res.data[0]
        db_id = email["id"]
        gmail_id = email["gmail_id"]
        subject = email["subject"]
        body = email["body"]
        
        print(f"Found email in DB:")
        print(f"  - Database ID (UUID): {db_id}")
        print(f"  - Gmail ID: {gmail_id}")
        print(f"  - Subject: {subject}")
        print(f"  - Body length: {len(body) if body else 0} chars")
        
    except Exception as e:
        print(f"Error fetching email from Supabase: {e}")
        return

    print("\nStep 2: Classifying the email using the local Ollama LLM...")
    try:
        classification = classify_email(subject=subject, body=body)
        print("Classification result:")
        print(f"  - Tag/Label: {classification.get('tag')}")
        print(f"  - Reason/Explanation: {classification.get('reason')}")
    except Exception as e:
        print(f"Error during LLM classification: {e}")
        print("Please make sure Ollama is running ('ollama serve') and 'llama3' is pulled.")
        return

    print("\nStep 3: Storing the classification in the 'classifications' table...")
    try:
        # Priority mapping: 1 for urgent, 2 for action, 3 for fyi, 4 for spam
        priority_map = {
            "urgent": 1,
            "action": 2,
            "fyi": 3,
            "spam": 4
        }
        tag = classification.get("tag", "fyi")
        reason = classification.get("reason", "")
        
        classification_data = {
            "email_id": db_id,
            "label": tag,
            "priority": priority_map.get(tag, 3),
            "summary": reason
        }
        
        print(f"Inserting into classifications: {classification_data}")
        # Insert the row into the classifications table
        insert_res = supabase.table("classifications").insert(classification_data).execute()
        
        if insert_res.data:
            inserted = insert_res.data[0]
            print("Successfully stored in database!")
            print(f"  - ID: {inserted.get('id')}")
            print(f"  - Email ID: {inserted.get('email_id')}")
            print(f"  - Label: {inserted.get('label')}")
            print(f"  - Priority: {inserted.get('priority')}")
            print(f"  - Summary: {inserted.get('summary')}")
            print(f"  - Created At: {inserted.get('created_at')}")
        else:
            print("Insert execution returned empty data.")
            
    except Exception as e:
        print(f"Error saving to classifications table: {e}")

if __name__ == "__main__":
    run_test()
