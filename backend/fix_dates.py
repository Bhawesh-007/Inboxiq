from database import supabase
from email.utils import parsedate_to_datetime

res = supabase.table("emails").select("id, date").execute()
for r in res.data:
    date_str = r["date"]
    if not date_str.startswith("202"):
        try:
            iso_date = parsedate_to_datetime(date_str).isoformat()
            supabase.table("emails").update({"date": iso_date}).eq("id", r["id"]).execute()
            print(f"Updated {r['id']} to {iso_date}")
        except Exception as e:
            print(f"Failed {r['id']}: {e}")
