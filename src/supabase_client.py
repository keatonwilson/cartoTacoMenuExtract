import httpx
from supabase import ClientOptions, create_client, Client
from src.config import get_supabase_url, get_supabase_key

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        # ponytail: no keep-alive. The client lives as long as the app, and a
        # pooled connection left idle gets closed by the server, so the next
        # request failed with "Server disconnected". A fresh connection per
        # request costs a TLS handshake; pool with a retry if that ever shows.
        http = httpx.Client(
            timeout=120, follow_redirects=True, limits=httpx.Limits(max_keepalive_connections=0)
        )
        _client = create_client(get_supabase_url(), get_supabase_key(), ClientOptions(httpx_client=http))
    return _client
