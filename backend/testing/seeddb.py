from database import supabase
#now this is a scrpt that will seed the database and will test
def seed_db():
    
   
    try:
        print("creating user")
        user_data = {
            "name":"Bhawesh",
            "email":"testing@gmail.com",
        }
        user_res = supabase.table("users").insert(user_data).execute()
        user_id = user_res.data[0]["id"]
        print(f"user id:{user_id}")
        email_data = {
            "user_id": user_id,
            "gmail_id": "msg_backend_test_001",
            "sender": "hr@techcorp.com",
            "subject": "Backend Engineer Interview",
            "body": "We were very impressed by your architecture for InboxIQ. We would like to schedule a technical round."
        }
            
        supabase.table("emails").insert(email_data).execute()
        print("email created")
    except Exception as e:
        print("error:", e)
    
    
if __name__ == "__main__":
    seed_db()   
    