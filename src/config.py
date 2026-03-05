import os
from functools import lru_cache
from dotenv import load_dotenv

load_dotenv()

EXTRACTION_MODEL = "claude-sonnet-4-20250514"
MAX_IMAGE_DIMENSION = 1500


def _require(var: str) -> str:
    val = os.getenv(var)
    if not val:
        raise RuntimeError(f"Missing required env var: {var}")
    return val


@lru_cache
def get_anthropic_key() -> str:
    return _require("ANTHROPIC_API_KEY")


@lru_cache
def get_supabase_url() -> str:
    return _require("SUPABASE_URL")


@lru_cache
def get_supabase_key() -> str:
    return _require("SUPABASE_SERVICE_KEY")
