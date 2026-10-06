"""CRUD operations for item_spec and protein_spec reference tables."""

import uuid
from src.supabase_client import get_client


# --- Name matching ---
# Mirrors public.normalize_spec_name() in cartoTaco migration 034 — keep the
# two in sync so promotion and the database triggers agree on what matches.

def normalize_spec_name(name: str | None) -> str:
    """Lowercase, trim, and collapse internal whitespace."""
    return " ".join((name or "").split()).lower()


def build_spec_index(client, table: str) -> dict[str, list[int]]:
    """Map normalized spec name -> ids for one spec table (tables are small)."""
    index: dict[str, list[int]] = {}
    for row in client.table(table).select("id, name").execute().data:
        key = normalize_spec_name(row.get("name"))
        if key:
            index.setdefault(key, []).append(row["id"])
    return index


def resolve_spec_id(index: dict[str, list[int]], name: str | None) -> int | None:
    """Return the spec id only when exactly one spec matches; ambiguous or
    missing names resolve to None and are left for review."""
    ids = index.get(normalize_spec_name(name), [])
    return ids[0] if len(ids) == 1 else None


# --- Item Spec ---

def list_item_specs() -> list[dict]:
    client = get_client()
    return client.table("item_spec").select("*").order("name").execute().data


def get_item_spec(spec_id: int) -> dict:
    client = get_client()
    return client.table("item_spec").select("*").eq("id", spec_id).single().execute().data


def create_item_spec(data: dict) -> dict:
    client = get_client()
    return client.table("item_spec").insert(data).execute().data[0]


def update_item_spec(spec_id: int, data: dict) -> dict:
    client = get_client()
    return client.table("item_spec").update(data).eq("id", spec_id).execute().data[0]


def delete_item_spec(spec_id: int) -> None:
    client = get_client()
    client.table("item_spec").delete().eq("id", spec_id).execute()


# --- Protein Spec ---

def list_protein_specs() -> list[dict]:
    client = get_client()
    return client.table("protein_spec").select("*").order("name").execute().data


def get_protein_spec(spec_id: int) -> dict:
    client = get_client()
    return client.table("protein_spec").select("*").eq("id", spec_id).single().execute().data


def create_protein_spec(data: dict) -> dict:
    client = get_client()
    return client.table("protein_spec").insert(data).execute().data[0]


def update_protein_spec(spec_id: int, data: dict) -> dict:
    client = get_client()
    return client.table("protein_spec").update(data).eq("id", spec_id).execute().data[0]


def delete_protein_spec(spec_id: int) -> None:
    client = get_client()
    client.table("protein_spec").delete().eq("id", spec_id).execute()


# --- Image Upload ---

def upload_spec_image(file_bytes: bytes, filename: str) -> str:
    """Upload an image to the spec-images bucket, return its public URL."""
    client = get_client()
    path = f"{uuid.uuid4().hex}_{filename}"
    client.storage.from_("spec-images").upload(path, file_bytes, {"content-type": "image/jpeg"})
    url = client.storage.from_("spec-images").get_public_url(path)
    return url
