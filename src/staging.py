"""Staging table CRUD operations."""

import uuid
from src.supabase_client import get_client
from src.models import ExtractedEstablishment


def save_extraction(
    extraction: ExtractedEstablishment,
    raw_json: dict,
    image_urls: list[str],
    model: str = "claude-sonnet-4-20250514",
) -> str:
    """Save an extraction to the staging table. Returns the new row ID."""
    client = get_client()
    row = {
        "restaurant_name": extraction.restaurant_name,
        "site_data": extraction.site.model_dump(),
        "menu_data": extraction.menu.model_dump(),
        "protein_data": extraction.protein.model_dump(),
        "hours_data": extraction.hours.model_dump(),
        "salsa_data": extraction.salsa.model_dump(),
        "description_data": extraction.description.model_dump(),
        "source_image_urls": image_urls,
        "extraction_model": model,
        "raw_extraction": raw_json,
    }
    result = client.table("staging_extractions").insert(row).execute()
    return result.data[0]["id"]


def list_extractions(status: str | None = None) -> list[dict]:
    """List staging extractions, optionally filtered by status."""
    client = get_client()
    query = client.table("staging_extractions").select("*").order("created_at", desc=True)
    if status:
        query = query.eq("status", status)
    return query.execute().data


def get_extraction(row_id: str) -> dict:
    """Get a single staging extraction by ID."""
    client = get_client()
    return client.table("staging_extractions").select("*").eq("id", row_id).single().execute().data


def update_extraction(row_id: str, updates: dict) -> dict:
    """Update fields on a staging extraction."""
    client = get_client()
    return client.table("staging_extractions").update(updates).eq("id", row_id).execute().data


def set_status(row_id: str, status: str) -> dict:
    """Set the status of a staging extraction."""
    return update_extraction(row_id, {"status": status})


def upload_image(file_bytes: bytes, filename: str) -> str:
    """Upload an image to Supabase Storage and return its storage path.

    Returns the storage path (not a public URL) since the bucket may be private.
    Use get_image_url() to generate a signed URL for display.
    """
    client = get_client()
    path = f"{uuid.uuid4().hex}_{filename}"
    client.storage.from_("menu-photos").upload(path, file_bytes, {"content-type": "image/jpeg"})
    return path


def get_image_url(path: str) -> str:
    """Get a signed URL for a stored image (valid for 1 hour).

    Handles both legacy full public URLs and new storage paths.
    """
    client = get_client()
    # Legacy: if path is already a full URL, extract just the storage path
    marker = "/menu-photos/"
    if marker in path:
        path = path.split(marker, 1)[1]
    resp = client.storage.from_("menu-photos").create_signed_url(path, 3600)
    return resp["signedURL"]
