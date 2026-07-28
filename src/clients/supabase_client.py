from supabase import create_client, Client
from src.configs.settings import SUPABASE_URL, SUPABASE_KEY

# Only create the client if we have the credentials, otherwise mock or error out.
if SUPABASE_URL and SUPABASE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    # A dummy mock or None depending on how you want to handle missing keys
    supabase = None
