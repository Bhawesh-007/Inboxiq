from database import supabase

class EmailPaginator:
    @staticmethod
    def get_token_for_page(user_id: str, page: int):
        # We need the token that gets us TO this page (saved from page - 1)
        prev_page = page - 1
        res = supabase.table("page_tokens").select("token").eq("user_id", user_id).eq("page", prev_page).execute()
        if res.data:
            return res.data[0]["token"]
        return None

    @staticmethod
    def save_next_page_token(user_id: str, current_page: int, next_token: str):
        if next_token:
            payload = {
                "user_id": user_id,
                "page": current_page, # Saving the token needed to fetch page + 1
                "token": next_token
            }
            supabase.table("page_tokens").upsert(payload, on_conflict="user_id, page").execute()

    @staticmethod
    def get_emails_from_db(user_id: str, page: int, per_page: int = 10):
        offset = (page - 1) * per_page
        res = supabase.table("emails") \
            .select("*") \
            .eq("user_id", user_id) \
            .order("date", desc=True) \
            .range(offset, offset + per_page - 1) \
            .execute()
        return res.data
