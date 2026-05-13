import sys
import time
from services.gmail import fetch_emails
from services.nlp import classify_email

def main():
    print("1. Calling fetch_emails...")
    start_time = time.time()
    emails = fetch_emails()
    print(f"fetch_emails completed in {time.time() - start_time:.2f} seconds. Found {len(emails)} emails.")

    if emails:
        print("2. Calling classify_email on the first email...")
        start_time = time.time()
        label = classify_email(emails[0]["subject"], emails[0]["from"])
        print(f"classify_email completed in {time.time() - start_time:.2f} seconds. Label: {label}")

if __name__ == "__main__":
    main()
