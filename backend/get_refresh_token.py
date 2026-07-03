#this script is to get a fresh accesss token for querying the gmail api
import os
import re
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow
load_dotenv()

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")


SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
def get_access_token():
    
    client_config = {
        "web":{
            "client_id": CLIENT_ID,
            "client_secret":CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
    print("Starting local server on port 8080.  Opening browser for consent...")
    creds = flow.run_local_server(
        port = 8080,
        prompt = 'consent',
        access_type = 'offline',
    )
    return creds.token , creds.refresh_token
#now i will update the env file with new access and refresh tokens
def update_env(access_token , refresh_token):
    with open(".env", "r") as f:
        lines = f.readlines()
    with open(".env", "w") as f:
        for line in lines:
            if line.startswith("GMAIL_ACCESS_TOKEN="):
                f.write(f"GMAIL_ACCESS_TOKEN={access_token}\n")
            elif line.startswith("GMAIL_REFRESH_TOKEN="):
                f.write(f"GMAIL_REFRESH_TOKEN={refresh_token}\n")
            else:
                f.write(line)
    print(f"updated with new tokens")
if __name__ == "__main__":
    access_token, refresh_token = get_access_token()

    if refresh_token:
        update_env(access_token, refresh_token)
    else:
        print(
            "Warning: No Refresh Token was returned. "
            "Delete the app's access in your Google Account and try again."
        )

