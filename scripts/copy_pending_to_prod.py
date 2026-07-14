"""One-off: copy web-scraped PENDING spots from one Supabase project to another.

Fixes the case where pending spots were promoted into the wrong project
(e.g. staging) because the menuextract .env pointed at the wrong database.

Reads pending web_scrape `sites` rows (+ their `descriptions`/`hours`) from
SRC and inserts them into DST with freshly-allocated est_ids, skipping any
whose name already exists in DST. est_ids are re-mapped (not reused) so they
can never collide with real spots already in DST — nothing external references
these brand-new pending rows yet, so the key is free to change.

Prerequisite: DST must already have cartoTaco migrations 030 + 031 applied.

Usage (SRC = the wrong DB you scouted into, DST = where you want them):

    # dry run (default) — prints what would be copied, writes nothing
    SRC_SUPABASE_URL=... SRC_SUPABASE_SERVICE_KEY=... \
    DST_SUPABASE_URL=... DST_SUPABASE_SERVICE_KEY=... \
    python scripts/copy_pending_to_prod.py

    # actually write to DST
    ... python scripts/copy_pending_to_prod.py --apply
"""

import os
import sys

from supabase import create_client

# Must match the live sites schema (contact/lat_2/lon_2/days_loc_2 were dropped
# in cartoTaco migration 020; scraped_at added in 030).
SITE_COLS = [
    "name", "type", "address", "phone", "website", "instagram", "facebook",
    "lat_1", "lon_1", "days_loc_1",
    "vetting_status", "source", "source_url", "scraped_at",
]
DESC_COLS = ["short_descrip", "long_descrip", "region"]
HOURS_COLS = [
    f"{day}_{part}"
    for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
    for part in ("start", "end")
]


def env(name: str) -> str:
    val = os.getenv(name)
    if not val:
        sys.exit(f"Missing env var: {name}")
    return val


def main() -> None:
    apply = "--apply" in sys.argv

    src = create_client(env("SRC_SUPABASE_URL"), env("SRC_SUPABASE_SERVICE_KEY"))
    dst = create_client(env("DST_SUPABASE_URL"), env("DST_SUPABASE_SERVICE_KEY"))

    print(f"SOURCE (copy from): {os.getenv('SRC_SUPABASE_URL')}")
    print(f"DEST   (copy to)  : {os.getenv('DST_SUPABASE_URL')}")
    print(f"MODE              : {'APPLY — writing to DEST' if apply else 'DRY RUN — no writes'}\n")

    # Prereq: DEST must have the vetting columns (030/031 applied)
    try:
        dst.table("sites").select("vetting_status").limit(1).execute()
    except Exception as e:  # noqa: BLE001 - surface any schema/connection issue
        sys.exit(
            "DEST is missing `vetting_status` — run cartoTaco migrations 030 + 031 "
            f"on the DEST project first, then re-run.\n{e}"
        )

    # Pending web-scraped spots in SRC
    pending = (
        src.table("sites")
        .select("*")
        .eq("vetting_status", "pending")
        .eq("source", "web_scrape")
        .order("est_id")
        .execute()
        .data
    )
    if not pending:
        print("No pending web_scrape spots in SOURCE. Nothing to do.")
        return

    # DEST dedup set (by name) + next free est_id
    dst_sites = dst.table("sites").select("est_id, name").execute().data
    existing_names = {(r.get("name") or "").strip().lower() for r in dst_sites}
    next_id = max((r["est_id"] for r in dst_sites), default=0) + 1

    copied = skipped = 0
    for spot in pending:
        name = (spot.get("name") or "").strip()
        if name.lower() in existing_names:
            print(f"  skip (name already in DEST): {name}")
            skipped += 1
            continue

        old_id = spot["est_id"]
        new_id = next_id
        next_id += 1

        desc = src.table("descriptions").select("*").eq("est_id", old_id).execute().data
        hours = src.table("hours").select("*").eq("est_id", old_id).execute().data

        print(
            f"  copy: {name}  (est_id {old_id} -> {new_id})"
            + ("  +desc" if desc else "")
            + ("  +hours" if hours else "")
        )

        if apply:
            site_row = {c: spot.get(c) for c in SITE_COLS}
            site_row["est_id"] = new_id
            dst.table("sites").upsert(site_row, on_conflict="est_id").execute()

            if desc:
                d = {c: desc[0].get(c) for c in DESC_COLS}
                d["est_id"] = new_id
                dst.table("descriptions").upsert(d, on_conflict="est_id").execute()

            if hours:
                h = {c: hours[0].get(c) for c in HOURS_COLS}
                h["est_id"] = new_id
                dst.table("hours").upsert(h, on_conflict="est_id").execute()

        existing_names.add(name.lower())
        copied += 1

    verb = "Copied" if apply else "Would copy"
    print(f"\n{verb}: {copied}   Skipped (name dup): {skipped}")
    if not apply and copied:
        print("Re-run with --apply to write to DEST.")


if __name__ == "__main__":
    main()
