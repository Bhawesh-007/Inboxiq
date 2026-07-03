import sys
import os

# Add the backend and ml_model directories to python path
backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, backend_dir)
sys.path.insert(0, os.path.join(backend_dir, "ml_model"))

# Set console encoding to UTF-8
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

from database import supabase
from predict import classify_email

def main():
    print("Fetching all emails from Supabase...")
    emails_res = supabase.table("emails").select("id, subject, body").execute()
    emails = emails_res.data or []
    print(f"Found {len(emails)} total emails in database.")

    priority_map = {"urgent": 1, "action": 2, "fyi": 3, "spam": 4}
    success_count = 0

    for idx, email in enumerate(emails):
        email_id = email["id"]
        subject = email["subject"]
        body = email["body"] or ""

        # Check if already classified
        cls_check = supabase.table("classifications").select("id").eq("email_id", email_id).execute()
        if cls_check.data:
            print(f"[{idx+1}/{len(emails)}] Email already classified: '{subject[:40]}...'")
            continue

        print(f"[{idx+1}/{len(emails)}] Classifying: '{subject[:40]}...'")
        try:
            classification = classify_email(subject=subject, body=body)
            tag = classification.get("tag", "fyi")
            reason = classification.get("reason", "")
            
            # If Ollama is not running, we want to warn the user
            if "Connection error" in reason or "Ollama error" in reason:
                print("⚠️ Warning: Cannot connect to Ollama. Please make sure Ollama is running ('ollama run llama3') before continuing.")
                break

            classification_data = {
                "email_id": email_id,
                "label": tag,
                "priority": priority_map.get(tag, 3),
                "summary": reason
            }
            
            supabase.table("classifications").insert(classification_data).execute()
            print(f"  └ Saved tag: {tag}")
            success_count += 1
        except Exception as e:
            print(f"  └ Failed: {e}")
            break

    print(f"\nCompleted! Classified {success_count} new emails.")

if __name__ == "__main__":
    main()
