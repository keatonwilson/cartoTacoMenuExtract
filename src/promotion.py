"""Promote approved staging rows to production tables."""

from src.supabase_client import get_client
from src.staging import get_extraction, set_status


def get_all_sites() -> list[dict]:
    """Return all sites for the est_id picker."""
    client = get_client()
    return client.table("sites").select("est_id, name").order("name").execute().data


def find_sites_by_name(name: str) -> list[dict]:
    """Return sites whose name closely matches the given string (case-insensitive)."""
    client = get_client()
    return client.table("sites").select("est_id, name, address").ilike("name", f"%{name}%").execute().data


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
    SITE_DB_COLUMNS = {
        "name", "type", "address", "phone", "website", "instagram", "facebook",
        "lat_1", "lon_1", "days_loc_1",
    }
    site_row = {"name": site_data.get("name") or row["restaurant_name"]}
    for key in SITE_DB_COLUMNS - {"name"}:
        val = site_data.get(key)
        site_row[key] = val if val not in (None, "") else None

    if est_id is None:
        # est_id is not auto-generated; find the next available value
        max_row = client.table("sites").select("est_id").order("est_id", desc=True).limit(1).execute().data
        est_id = (max_row[0]["est_id"] + 1) if max_row else 1
    site_row["est_id"] = est_id
    client.table("sites").upsert(site_row, on_conflict="est_id").execute()

    # --- Menu ---
    MENU_DB_COLUMNS = {
        "burro_yes", "taco_yes", "torta_yes", "dog_yes", "plate_yes", "cocktail_yes",
        "gordita_yes", "huarache_yes", "cemita_yes", "flauta_yes", "chalupa_yes",
        "molote_yes", "tostada_yes", "enchilada_yes", "tamale_yes", "sope_yes", "caldo_yes", "snacks_yes",
        "quesadilla_yes",
        "burro_perc", "taco_perc", "torta_perc", "dog_perc", "plate_perc", "cocktail_perc",
        "gordita_perc", "huarache_perc", "cemita_perc", "flauta_perc", "chalupa_perc",
        "molote_perc", "tostada_perc", "enchilada_perc", "tamale_perc", "sope_perc", "caldo_perc", "snacks_perc",
        "quesadilla_perc",
        "flour_corn", "handmade_tortilla",
    }
    menu_row = {"est_id": est_id}
    for key, val in menu_data.items():
        if key in MENU_DB_COLUMNS:
            menu_row[key] = val
    # Map specialty_items list to specialty_item_1..4 columns + resolve IDs
    specialty = menu_data.get("specialty_items", [])
    for i in range(1, 5):
        menu_row[f"specialty_item_{i}"] = specialty[i - 1] if i <= len(specialty) else None
    # Look up item_spec IDs by name for columns 1..3
    for i in range(1, 4):
        name = menu_row.get(f"specialty_item_{i}")
        if name:
            result = client.table("item_spec").select("id").eq("name", name).limit(1).execute().data
            menu_row[f"spec_id_{i}"] = result[0]["id"] if result else None
        else:
            menu_row[f"spec_id_{i}"] = None
    client.table("menu").upsert(menu_row, on_conflict="est_id").execute()

    # --- Protein ---
    PROTEIN_DB_COLUMNS = {
        "chicken_yes", "beef_yes", "pork_yes", "fish_yes", "veg_yes",
        "chicken_perc", "beef_perc", "pork_perc", "fish_perc", "veg_perc",
        "chicken_style_1", "chicken_style_2", "chicken_style_3",
        "beef_style_1", "beef_style_2", "beef_style_3",
        "pork_style_1", "pork_style_2", "pork_style_3",
        "fish_style_1", "fish_style_2", "fish_style_3",
        "veg_style_1", "veg_style_2", "veg_style_3",
    }
    prot_row = {"est_id": est_id}
    for key, val in protein_data.items():
        if key in PROTEIN_DB_COLUMNS:
            prot_row[key] = val
    prot_specs = protein_data.get("protein_specs", [])
    for i in range(1, 4):
        prot_row[f"protein_spec_{i}"] = prot_specs[i - 1] if i <= len(prot_specs) else None
    # Look up protein_spec IDs by name
    for i in range(1, 4):
        name = prot_row.get(f"protein_spec_{i}")
        if name:
            result = client.table("protein_spec").select("id").eq("name", name).limit(1).execute().data
            prot_row[f"spec_id_{i}"] = result[0]["id"] if result else None
        else:
            prot_row[f"spec_id_{i}"] = None
    client.table("protein").upsert(prot_row, on_conflict="est_id").execute()

    # --- Hours ---
    hours_row = {"est_id": est_id}
    for key, val in hours_data.items():
        hours_row[key] = val or None
    client.table("hours").upsert(hours_row, on_conflict="est_id").execute()

    # --- Salsa ---
    SALSA_DB_COLUMNS = {
        "total_num", "heat_overall", "verde_yes", "rojo_yes", "pico_yes", "pickles_yes",
        "chipotle_yes", "avo_yes", "molcajete_yes", "macha_yes",
        "other_1_name", "other_1_descrip", "other_2_name", "other_2_descrip",
        "other_3_name", "other_3_descrip",
    }
    salsa_row = {"est_id": est_id}
    for key, val in salsa_data.items():
        if key in SALSA_DB_COLUMNS:
            salsa_row[key] = val
    salsa_spec_list = salsa_data.get("salsa_specs", [])
    for i in range(1, 3):
        salsa_row[f"salsa_spec_{i}"] = salsa_spec_list[i - 1] if i <= len(salsa_spec_list) else None
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
