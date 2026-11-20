"""One-time copy of the curated Salsa Atlas from the staging DB to prod.

Atlas curation (styles, links, sighting photos) happened on staging; prod only
has migration 036's seed. This copies staging's curation over it:

    python3 -m scripts.promote_atlas            # dry run: preflight + report, writes nothing
    python3 -m scripts.promote_atlas --apply    # copy photos, then styles, then links

- salsa_styles are upserted by slug, never by id: the id is GENERATED ALWAYS AS
  IDENTITY, so a style new to prod gets a prod id. spec_id is resolved through
  salsa_spec.name, because spec ids differ between the two databases.
- site_salsas are upserted on (est_id, style_id), with the style id mapped
  staging id → slug → prod id.
- Photos under salsas/sightings/ and salsas/styles/ are copied at the same path,
  and photo_url / img_url are rewritten from the staging host to prod's.
- Not copied: draft styles prod doesn't have (an existing slug is still set to
  draft), links to draft styles, links on spots that aren't live on prod, and
  user_favorite_salsas (staging users aren't prod users).

Nothing is deleted on prod. Preflight problems abort before any write.
"""
import argparse
import os
from collections import defaultdict

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

BUCKET = "salsas"
FOLDERS = ["sightings", "styles"]
# Columns the database fills in itself
SKIP_COLUMNS = {"id", "created_at", "updated_at"}


# ── Pure functions (tested in tests/test_promote_atlas.py) ───────────────────

def public_prefix(supabase_url: str) -> str:
    return f"{supabase_url.rstrip('/')}/storage/v1/object/public/{BUCKET}/"


def rewrite_url(url, src_prefix, dst_prefix):
    """Point a staging bucket URL at prod; any other URL (or None) is returned as is."""
    if url and url.startswith(src_prefix):
        return dst_prefix + url[len(src_prefix):]
    return url


def walk(list_fn, folder):
    """Every object under `folder` as (path, size, mimetype).

    Storage list isn't recursive: an entry with no id is a subfolder, listed in turn.
    """
    found = []
    for entry in list_fn(folder):
        path = f"{folder}/{entry['name']}"
        if entry.get("id") is None:
            found += walk(list_fn, path)
        else:
            meta = entry.get("metadata") or {}
            found.append((path, meta.get("size", 0), meta.get("mimetype", "image/jpeg")))
    return found


def is_sighting(link):
    return bool(link.get("photo_url") or link.get("observed_at") or link.get("palette"))


def live_est_ids(prod_sites):
    """Spots the public site shows as open: vetted and not closed."""
    return {s["est_id"] for s in prod_sites if s.get("vetting_status", "vetted") == "vetted" and not s.get("closed_at")}


def preflight(staging_styles, staging_links, staging_specs, prod_specs, prod_sites, objects, src_prefix):
    """Every reason the copy can't go ahead; empty means go."""
    problems = []
    prod_est_ids = {s["est_id"] for s in prod_sites}
    for link in staging_links:
        if (is_sighting(link) or not link["synced"]) and link["est_id"] not in prod_est_ids:
            problems.append(f"site_salsas ({link['est_id']}, {link['style_id']}): spot {link['est_id']} is not in prod")

    spec_names = {s["id"]: s["name"] for s in staging_specs}
    prod_spec_names = [s["name"] for s in prod_specs]
    for style in staging_styles:
        if style.get("spec_id") is not None:
            name = spec_names.get(style["spec_id"])
            if prod_spec_names.count(name) != 1:
                problems.append(f"style {style['slug']}: salsa_spec {name!r} matches {prod_spec_names.count(name)} prod specs")

    paths = {p for p, _, _ in objects}
    for row in staging_styles + staging_links:
        for col in ("img_url", "photo_url"):
            url = row.get(col)
            if url and url.startswith(src_prefix) and url[len(src_prefix):].split("?")[0] not in paths:
                problems.append(f"{col} {url} is not under {'/'.join(FOLDERS)} in the staging bucket")
    return problems


def resolve_spec_id(spec_id, staging_specs, prod_specs):
    if spec_id is None:
        return None
    name = next(s["name"] for s in staging_specs if s["id"] == spec_id)
    return next(s["id"] for s in prod_specs if s["name"] == name)


def diff_fields(new, old):
    return sorted(k for k, v in new.items() if old.get(k) != v)


def plan_styles(staging_styles, prod_styles, staging_specs, prod_specs, src_prefix, dst_prefix):
    """(rows to upsert by slug, slugs to insert, {slug: changed fields} to update)."""
    prod_by_slug = {s["slug"]: s for s in prod_styles}
    rows, inserts, updates = [], [], {}
    for style in staging_styles:
        if style["status"] == "draft" and style["slug"] not in prod_by_slug:
            continue
        row = {k: v for k, v in style.items() if k not in SKIP_COLUMNS}
        row["spec_id"] = resolve_spec_id(style.get("spec_id"), staging_specs, prod_specs)
        row["img_url"] = rewrite_url(style.get("img_url"), src_prefix, dst_prefix)
        old = prod_by_slug.get(style["slug"])
        if old is None:
            inserts.append(style["slug"])
        elif changed := diff_fields(row, old):
            updates[style["slug"]] = changed
        else:
            continue
        rows.append(row)
    return rows, inserts, updates


def skip_reason(link, draft_ids, live):
    if link["style_id"] in draft_ids:
        return "draft style"
    if link["est_id"] not in live:
        return "spot not live on prod"
    return None


def plan_links(staging_links, staging_styles, prod_ids_by_slug, live, prod_links, src_prefix, dst_prefix):
    """(rows to upsert, inserts, updates, {reason: count} skipped).

    A slug missing from prod_ids_by_slug is a style the copy will insert; its
    links count as inserts with style_id None (only possible in a dry run).
    """
    slug_of = {s["id"]: s["slug"] for s in staging_styles}
    draft = {s["id"] for s in staging_styles if s["status"] == "draft"}
    prod_by_key = {(l["est_id"], l["style_id"]): l for l in prod_links}
    rows, inserts, updates, skipped = [], [], [], defaultdict(int)
    for link in staging_links:
        if reason := skip_reason(link, draft, live):
            skipped[reason] += 1
            continue
        row = {k: v for k, v in link.items() if k not in SKIP_COLUMNS}
        row["style_id"] = prod_ids_by_slug.get(slug_of[link["style_id"]])
        row["photo_url"] = rewrite_url(link.get("photo_url"), src_prefix, dst_prefix)
        old = prod_by_key.get((row["est_id"], row["style_id"]))
        if old is None:
            inserts.append(row)
        elif diff_fields(row, old):
            updates.append(row)
        else:
            continue
        rows.append(row)
    return rows, inserts, updates, dict(skipped)


def expected_counts(style_rows, prod_styles, prod_links, staging_styles, staging_links, live):
    """Per slug after the copy: (status, live spots, synced, hand-made, sightings).

    Same columns as staging_atlas.py's table, so the two can be compared.
    """
    status = {s["slug"]: s["status"] for s in prod_styles} | {r["slug"]: r["status"] for r in style_rows}
    slug_of_prod = {s["id"]: s["slug"] for s in prod_styles}
    slug_of_staging = {s["id"]: s["slug"] for s in staging_styles}
    draft = {s["id"] for s in staging_styles if s["status"] == "draft"}
    links = {(l["est_id"], slug_of_prod[l["style_id"]]): l for l in prod_links}
    for l in staging_links:
        if not skip_reason(l, draft, live):
            links[(l["est_id"], slug_of_staging[l["style_id"]])] = l

    counts = {slug: [st, set(), 0, 0, 0] for slug, st in status.items()}
    for (est_id, slug), link in links.items():
        c = counts[slug]
        if est_id in live:
            c[1].add(est_id)
        c[2 if link["synced"] else 3] += 1
        c[4] += is_sighting(link)
    return {slug: (st, len(spots), syn, hand, sig) for slug, (st, spots, syn, hand, sig) in counts.items()}


# ── Supabase ─────────────────────────────────────────────────────────────────

def _client(url_var, key_var):
    return create_client(os.environ[url_var], os.environ[key_var])


def fetch_all(client, table, columns="*"):
    # shortcut: one page of 10k rows, fine at ~40 spots; paginate if a table grows past that
    return client.table(table).select(columns).limit(10000).execute().data


def lister(client):
    # shortcut: one page of 1000 entries per folder; paginate with offset past that
    return lambda folder: client.storage.from_(BUCKET).list(folder, {"limit": 1000})


def check_prod_schema(prod):
    """Abort unless prod has the atlas tables with 039's columns, and the bucket."""
    try:
        prod.table("salsa_styles").select("id, slug, status").limit(1).execute()
        prod.table("site_salsas").select("est_id, photo_url, synced").limit(1).execute()
        prod.storage.get_bucket(BUCKET)
    except Exception as e:
        raise SystemExit(f"Prod is missing the atlas (migrations 036–039 and the `{BUCKET}` bucket): {e}")


def main(argv=None):
    p = argparse.ArgumentParser(description="Copy the curated Salsa Atlas from staging to prod.")
    p.add_argument("--apply", action="store_true", help="write to prod (default is a dry run)")
    args = p.parse_args(argv)

    if os.environ["SUPABASE_URL"].rstrip("/") == os.environ["SUPABASE_STAGING_URL"].rstrip("/"):
        raise SystemExit("SUPABASE_URL points at staging; unset the staging swap before promoting.")
    prod = _client("SUPABASE_URL", "SUPABASE_SERVICE_KEY")
    staging = _client("SUPABASE_STAGING_URL", "SUPABASE_STAGING_SERVICE_KEY")
    src_prefix = public_prefix(os.environ["SUPABASE_STAGING_URL"])
    dst_prefix = public_prefix(os.environ["SUPABASE_URL"])

    check_prod_schema(prod)
    s_styles, s_links, s_specs = (fetch_all(staging, t) for t in ("salsa_styles", "site_salsas", "salsa_spec"))
    p_styles, p_links, p_specs = (fetch_all(prod, t) for t in ("salsa_styles", "site_salsas", "salsa_spec"))
    p_sites = fetch_all(prod, "sites", "est_id, vetting_status, closed_at")
    objects = [o for folder in FOLDERS for o in walk(lister(staging), folder)]

    problems = preflight(s_styles, s_links, s_specs, p_specs, p_sites, objects, src_prefix)
    if problems:
        raise SystemExit("Preflight failed, nothing written:\n  " + "\n  ".join(problems))

    live = live_est_ids(p_sites)
    style_rows, inserts, updates = plan_styles(s_styles, p_styles, s_specs, p_specs, src_prefix, dst_prefix)
    prod_ids = {s["slug"]: s["id"] for s in p_styles}
    _, l_inserts, l_updates, skipped = plan_links(s_links, s_styles, prod_ids, live, p_links, src_prefix, dst_prefix)

    print(f"Storage: {len(objects)} objects, {sum(size for _, size, _ in objects) / 1e6:.1f} MB to copy")
    print(f"salsa_styles: {len(inserts)} to insert {inserts}, {len(updates)} to update")
    for slug, fields in updates.items():
        print(f"  {slug}: {', '.join(fields)}")
    print(f"site_salsas: {len(l_inserts)} to insert, {len(l_updates)} to update, skipped {skipped or 'none'}")

    counts = expected_counts(style_rows, p_styles, p_links, s_styles, s_links, live)
    print(f"\nExpected prod atlas: {len(counts)} styles, {sum(c[0] == 'published' for c in counts.values())} published")
    print(f"{'slug':<22}{'status':<10}{'spots':>6}{'synced':>7}{'hand':>5}{'sight':>6}")
    for slug, (st, spots, syn, hand, sig) in sorted(counts.items(), key=lambda kv: -kv[1][1]):
        print(f"{slug:<22}{st:<10}{spots:>6}{syn:>7}{hand:>5}{sig:>6}")

    if not args.apply:
        print("\nDry run. Re-run with --apply to write to prod.")
        return

    for path, _, mimetype in objects:
        data = staging.storage.from_(BUCKET).download(path)
        prod.storage.from_(BUCKET).upload(path, data, {"content-type": mimetype, "upsert": "true"})
    print(f"Copied {len(objects)} objects")

    if style_rows:
        prod.table("salsa_styles").upsert(style_rows, on_conflict="slug").execute()
    print(f"Upserted {len(style_rows)} styles")

    # Re-plan with the prod ids the new styles just got
    prod_ids = {s["slug"]: s["id"] for s in fetch_all(prod, "salsa_styles", "id, slug")}
    link_rows = plan_links(s_links, s_styles, prod_ids, live, fetch_all(prod, "site_salsas"), src_prefix, dst_prefix)[0]
    if link_rows:
        prod.table("site_salsas").upsert(link_rows, on_conflict="est_id,style_id").execute()
    print(f"Upserted {len(link_rows)} links")


if __name__ == "__main__":
    main()
