from supabase import create_client, Client
from src.config import get_supabase_url, get_supabase_key

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(get_supabase_url(), get_supabase_key())
    return _client
