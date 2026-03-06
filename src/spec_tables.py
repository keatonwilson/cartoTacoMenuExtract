"""CRUD operations for item_spec and protein_spec reference tables."""

import uuid
from src.supabase_client import get_client


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
