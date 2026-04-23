from dotenv import load_dotenv
import os

load_dotenv()

GMAIL_ACCESS_TOKEN = os.getenv("GMAIL_ACCESS_TOKEN")
GMAIL_REFRESH_TOKEN = os.getenv("GMAIL_REFRESH_TOKEN")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")