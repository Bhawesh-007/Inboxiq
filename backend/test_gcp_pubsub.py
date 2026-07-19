import base64
from email.message import EmailMessage
import time
import sys
import os

# Ensure we can import from backend
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.gmail import get_gmail_service
from database import supabase

def send_test_email():
    service = get_gmail_service()
    
    message = EmailMessage()
    message.set_content("This is a test email to verify GCP Pub/Sub integration.")
    # get my own email address
    profile = service.users().getProfile(userId="me").execute()
    my_email = profile.get("emailAddress")
    
    message['To'] = my_email
    message['From'] = my_email
    message['Subject'] = f'GCP Pub/Sub Integration Test {int(time.time())}'
    
    encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
    create_message = {'raw': encoded_message}
    
    print("Sending email...")
    send_message = service.users().messages().send(userId="me", body=create_message).execute()
    print(f"Email sent, Message ID: {send_message['id']}")
    return send_message['id']

def check_db(gmail_id, retries=10):
    for i in range(retries):
        print(f"Checking DB (Attempt {i+1}/{retries})...")
        res = supabase.table("emails").select("*").eq("gmail_id", gmail_id).execute()
        if res.data:
            print("Found email in DB!")
            print(res.data[0])
            return True
        time.sleep(3)
    print("Email not found in DB after retries.")
    return False

if __name__ == "__main__":
    msg_id = send_test_email()
    check_db(msg_id)
