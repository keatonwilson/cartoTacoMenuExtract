"""Promote approved staging rows to production tables."""

from src.supabase_client import get_client
from src.staging import get_extraction, set_status


def get_all_sites() -> list[dict]:
    """Return all sites for the est_id picker."""
    client = get_client()
    return client.table("sites").select("est_id, name").order("name").execute().data


def promote(row_id: str, est_id: int | None = None) -> int:
    """Promote a staging row to production.

    If est_id is None, creates a new site and returns the new est_id.
    Otherwise upserts into the existing est_id.

    Returns the est_id used.
    """
    client = get_client()
    row = get_extraction(row_id)
    site_data = row["site_data"]
    menu_data = row["menu_data"]
    protein_data = row["protein_data"]
    hours_data = row["hours_data"]
    salsa_data = row["salsa_data"]
    description_data = row["description_data"]

    # --- Sites ---
    site_row = {
        "name": site_data.get("name") or row["restaurant_name"],
        "type": site_data.get("type") or None,
        "address": site_data.get("address") or None,
        "phone": site_data.get("phone") or None,
        "website": site_data.get("website") or None,
        "instagram": site_data.get("instagram") or None,
        "facebook": site_data.get("facebook") or None,
        "contact": site_data.get("contact") or None,
        "lat_1": site_data.get("lat_1"),
        "lon_1": site_data.get("lon_1"),
        "days_loc_1": site_data.get("days_loc_1") or None,
        "lat_2": site_data.get("lat_2"),
        "lon_2": site_data.get("lon_2"),
        "days_loc_2": site_data.get("days_loc_2") or None,
    }

    if est_id is None:
        result = client.table("sites").insert(site_row).execute()
        est_id = result.data[0]["est_id"]
    else:
        site_row["est_id"] = est_id
        client.table("sites").upsert(site_row, on_conflict="est_id").execute()

    # --- Menu ---
    menu_row = {"est_id": est_id}
    # Copy boolean and text fields, skip specialty_items (text list, needs manual FK)
    for key, val in menu_data.items():
        if key == "specialty_items":
            continue
        menu_row[key] = val
    client.table("menu").upsert(menu_row, on_conflict="est_id").execute()

    # --- Protein ---
    prot_row = {"est_id": est_id}
    for key, val in protein_data.items():
        prot_row[key] = val
    client.table("protein").upsert(prot_row, on_conflict="est_id").execute()

    # --- Hours ---
    hours_row = {"est_id": est_id}
    for key, val in hours_data.items():
        hours_row[key] = val or None
    client.table("hours").upsert(hours_row, on_conflict="est_id").execute()

    # --- Salsa ---
    salsa_row = {"est_id": est_id}
    for key, val in salsa_data.items():
        salsa_row[key] = val
    client.table("salsa").upsert(salsa_row, on_conflict="est_id").execute()

    # --- Descriptions ---
    desc_row = {
        "est_id": est_id,
        "short_descrip": description_data.get("short_descrip") or None,
        "long_descrip": description_data.get("long_descrip") or None,
        "region": description_data.get("region") or None,
    }
    client.table("descriptions").upsert(desc_row, on_conflict="est_id").execute()

    # Mark staging row as promoted
    set_status(row_id, "promoted")

    return est_id
