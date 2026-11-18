"""Copy prod content rows into the staging DB, additively.

Staging holds Salsa Atlas data (salsa_styles, site_salsas, ...) that prod lacks,
so re-seeding staging with TRUNCATE ... CASCADE would erase it. This upserts
prod's rows into staging instead: new and changed rows are written, nothing is
deleted, and the atlas tables are never touched. est_ids and spec ids are kept,
so sightings made on staging still line up with prod when the atlas ships.

    python3 -m src.sync_to_staging            # dry run: list what would change
    python3 -m src.sync_to_staging --write    # back up the atlas, then write to staging

Why it can't erase the atlas: it never deletes, so no FK cascade fires. The one
trigger that deletes from site_salsas (sync_site_salsas, on salsa writes) only
removes links it made itself that carry no photo/palette/date/heat/name/note.
--write also dumps the atlas tables to backups/ first, and stops if that fails.
"""
import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

# Reference tables first, so menu/protein/salsa spec FKs resolve; sites before its children.
TABLES = [
    ("item_spec", "id"), ("protein_spec", "id"), ("salsa_spec", "id"),
    ("sites", "est_id"),
    ("hours", "est_id"), ("descriptions", "est_id"),
    ("menu", "est_id"), ("protein", "est_id"), ("salsa", "est_id"),
]
ATLAS_TABLES = ["salsa_styles", "site_salsas", "user_favorite_salsas"]


def _client(url_var, key_var):
    return create_client(os.environ[url_var], os.environ[key_var])


def fetch_all(client, table):
    # shortcut: one page of 10k rows, fine at ~40 spots; paginate if a table grows past that
    return client.table(table).select("*").limit(10000).execute().data


def diff(prod_rows, staging_rows, key):
    """Return (new, changed, staging_only_keys)."""
    staged = {r[key]: r for r in staging_rows}
    new = [r for r in prod_rows if r[key] not in staged]
    changed = [r for r in prod_rows if r[key] in staged and staged[r[key]] != r]
    prod_keys = {r[key] for r in prod_rows}
    return new, changed, sorted(k for k in staged if k not in prod_keys)


def backup_atlas(staging):
    """Write staging's atlas tables to backups/atlas-<timestamp>.json; return the path."""
    dump = {t: fetch_all(staging, t) for t in ATLAS_TABLES}
    path = Path("backups") / f"atlas-{datetime.now():%Y%m%d-%H%M%S}.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(dump, indent=1, default=str))
    return path, {t: len(rows) for t, rows in dump.items()}


def main(argv=None):
    p = argparse.ArgumentParser(description="Upsert prod content rows into staging (never deletes).")
    p.add_argument("--write", action="store_true", help="write to staging (default is a dry run)")
    args = p.parse_args(argv)

    prod = _client("SUPABASE_URL", "SUPABASE_SERVICE_KEY")
    staging = _client("SUPABASE_STAGING_URL", "SUPABASE_STAGING_SERVICE_KEY")
    if os.environ["SUPABASE_URL"] == os.environ["SUPABASE_STAGING_URL"]:
        raise SystemExit("SUPABASE_URL points at staging; unset the staging swap before syncing.")

    if args.write:
        path, counts = backup_atlas(staging)
        print(f"Atlas backed up to {path}: {counts}\n")

    for table, key in TABLES:
        new, changed, extra = diff(fetch_all(prod, table), fetch_all(staging, table), key)
        print(f"{table}: {len(new)} new {[r[key] for r in new]}, "
              f"{len(changed)} changed {[r[key] for r in changed]}"
              + (f", staging-only (left alone) {extra}" if extra else ""))
        if args.write and (new or changed):
            staging.table(table).upsert(new + changed, on_conflict=key).execute()

    if not args.write:
        print("\nDry run. Re-run with --write to apply.")


if __name__ == "__main__":
    main()
