"""Promote approved staging rows to production tables."""

from datetime import datetime, timezone

from src.supabase_client import get_client
from src.staging import get_extraction, set_status


def get_all_sites() -> list[dict]:
    """Return all sites for the est_id picker (vetting_status marks pending targets)."""
    client = get_client()
    return client.table("sites").select("est_id, name, vetting_status").order("name").execute().data


def find_sites_by_name(name: str) -> list[dict]:
    """Return sites whose name closely matches the given string (case-insensitive)."""
    client = get_client()
    return (
        client.table("sites")
        .select("est_id, name, address, vetting_status")
        .ilike("name", f"%{name}%")
        .execute()
        .data
    )


def _next_est_id(client) -> int:
    """est_id is not auto-generated; find the next available value."""
    max_row = client.table("sites").select("est_id").order("est_id", desc=True).limit(1).execute().data
    return (max_row[0]["est_id"] + 1) if max_row else 1


def has_menu_data(row: dict) -> bool:
    """True when the admin filled in menu/protein tabs on a scouted row."""
    merged = {**(row.get("menu_data") or {}), **(row.get("protein_data") or {})}
    return any(v for k, v in merged.items() if k.endswith("_yes"))


def promote(row_id: str, est_id: int | None = None) -> int:
    """Promote a staging row to production.

    If est_id is None, creates a new site and returns the new est_id.
    Otherwise upserts into the existing est_id.

    web_scrape rows take the pending path (_promote_scraped): sites row with
    vetting_status='pending' plus descriptions/hours only — unless the admin
    hand-filled the menu/protein tabs, in which case the row takes the full
    six-table path like a menu_photo row. Full promotion into a pending
    est_id flips it to vetted (the vetting loop).

    Returns the est_id used.
    """
    client = get_client()
    row = get_extraction(row_id)

    if row.get("pipeline") == "web_scrape" and not has_menu_data(row):
        return _promote_scraped(client, row_id, row, est_id)

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
        est_id = _next_est_id(client)
    else:
        # Vetting loop: promoting full menu-photo data into a pending spot
        # (originally web-scraped) flips it to vetted
        existing = (
            client.table("sites")
            .select("vetting_status")
            .eq("est_id", est_id)
            .limit(1)
            .execute()
            .data
        )
        if existing and existing[0].get("vetting_status") == "pending":
            site_row["vetting_status"] = "vetted"
            site_row["vetted_at"] = datetime.now(timezone.utc).isoformat()
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
    # Coerce null _perc values to 0.0 — DB columns have NOT NULL constraints
    for key in MENU_DB_COLUMNS:
        if key.endswith("_perc") and menu_row.get(key) is None:
            menu_row[key] = 0.0
    # Tortilla category is stored lowercase (flour/corn/both)
    if menu_row.get("flour_corn"):
        menu_row["flour_corn"] = menu_row["flour_corn"].lower()
    # Map specialty_items list to specialty_item_1..4 columns + resolve IDs
    specialty = menu_data.get("specialty_items", [])
    for i in range(1, 5):
        menu_row[f"specialty_item_{i}"] = specialty[i - 1] if i <= len(specialty) else None
    # Look up item_spec IDs by name for columns 1..3.
    # NOTE: the live menu/protein/salsa tables store the FK in `spec_id_{i}`
    # columns. The `specialty_item_id_*`/`protein_spec_id_*` columns named in
    # migrations 006/009 were never applied to the database — do not rename
    # these to match the migrations or promotion will break (PGRST204).
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


def _promote_scraped(client, row_id: str, row: dict, est_id: int | None) -> int:
    """Promote a web-scouted staging row as a pending (unvetted) site.

    Writes sites (with vetting_status='pending' + provenance) and, only when
    they contain data, descriptions and hours. menu/protein/salsa are skipped
    entirely — no stub rows; the sites_complete view's LEFT JOINs handle their
    absence and the frontend renders the preliminary card.
    """
    site_data = row["site_data"]
    hours_data = row.get("hours_data") or {}
    description_data = row.get("description_data") or {}
    source_urls = row.get("source_urls") or []

    SITE_DB_COLUMNS = {
        "name", "type", "address", "phone", "website", "instagram", "facebook",
        "lat_1", "lon_1", "days_loc_1",
    }
    site_row = {"name": site_data.get("name") or row["restaurant_name"]}
    for key in SITE_DB_COLUMNS - {"name"}:
        val = site_data.get(key)
        site_row[key] = val if val not in (None, "") else None

    site_row["vetting_status"] = "pending"
    site_row["source"] = "web_scrape"
    site_row["source_url"] = source_urls[0] if source_urls else None
    site_row["scraped_at"] = row.get("created_at")

    if est_id is None:
        est_id = _next_est_id(client)
    site_row["est_id"] = est_id
    client.table("sites").upsert(site_row, on_conflict="est_id").execute()

    # Hours: only when the scout actually found some
    if any(v for v in hours_data.values()):
        hours_row = {"est_id": est_id}
        for key, val in hours_data.items():
            hours_row[key] = val or None
        client.table("hours").upsert(hours_row, on_conflict="est_id").execute()

    # Descriptions: only when non-empty
    if any(description_data.get(k) for k in ("short_descrip", "long_descrip", "region")):
        desc_row = {
            "est_id": est_id,
            "short_descrip": description_data.get("short_descrip") or None,
            "long_descrip": description_data.get("long_descrip") or None,
            "region": description_data.get("region") or None,
        }
        client.table("descriptions").upsert(desc_row, on_conflict="est_id").execute()

    set_status(row_id, "promoted")
    return est_id


# --- Pending site management ---

def list_pending_sites() -> list[dict]:
    """Return all production sites still awaiting vetting."""
    client = get_client()
    return (
        client.table("sites")
        .select("est_id, name, address, source_url, scraped_at, created_at")
        .eq("vetting_status", "pending")
        .order("created_at", desc=True)
        .execute()
        .data
    )


def retract_pending_site(est_id: int) -> None:
    """Delete a pending site that turned out to be closed/bogus/duplicate.

    Refuses to touch vetted sites. Child rows are removed explicitly (their
    FKs are NO ACTION); user_favorites/vibe_votes cascade via the FKs added
    in cartoTaco migration 030.
    """
    client = get_client()
    rows = client.table("sites").select("vetting_status").eq("est_id", est_id).limit(1).execute().data
    if not rows:
        raise ValueError(f"No site with est_id {est_id}")
    if rows[0].get("vetting_status") != "pending":
        raise ValueError(f"Site {est_id} is vetted — refusing to delete a vetted site")

    for table in ("descriptions", "hours", "menu", "protein", "salsa"):
        client.table(table).delete().eq("est_id", est_id).execute()
    client.table("sites").delete().eq("est_id", est_id).execute()


def mark_vetted(est_id: int) -> None:
    """Manually flip a pending site to vetted (escape hatch; normally the
    vetting flip happens inside promote())."""
    client = get_client()
    client.table("sites").update(
        {"vetting_status": "vetted", "vetted_at": datetime.now(timezone.utc).isoformat()}
    ).eq("est_id", est_id).execute()
