#now this is the file for connecting to supabase via fastapi
import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()
supabase: Client = create_client(
    supabase_url=os.getenv("SUPABASE_URL"),
    supabase_key=os.getenv("SUPABASE_KEY")
)


def verify_connection():
    """Simple health check to verify we can reach the DB."""
    try:
        # We try to reach any table (e.g., 'users') just to check connectivity
        supabase.table("users").select("id").limit(1).execute()
        return True
    except Exception as e:
        print(f"Database connection failed: {e}")
        return False