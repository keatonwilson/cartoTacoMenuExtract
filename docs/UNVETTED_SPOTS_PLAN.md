# Unvetted Spots — Scraping Pipeline Plan (Streamlit side)

Status: **IMPLEMENTED** (see CLAUDE.md for the shipped layout)

> **Implementation deviation from §2:** instead of `requests`+`beautifulsoup4`
> scraping, the shipped `src/scraping.py` uses Claude's `web_search` tool — the
> same pattern as the existing `enrich_from_web` — so the app fetches nothing
> itself, adds zero dependencies, and sidesteps robots.txt/copy concerns. The
> page shipped as `pages/5_Scout_New_Spots.py` ("scout" beats "scrape" in the
> UI). Geocoding reuses the existing Nominatim `geocode_address`. Everything
> else (staging migration 010, `ScrapedSpot`, dedup, pending promotion path,
> vetting flip, retraction) landed as planned.
Master plan (schema, frontend, rollout phases): `cartoTaco/docs/UNVETTED_SPOTS_PLAN.md`

This doc covers the `cartoTacoMenuExtract` half of the feature: a web-scraping
pipeline that discovers **pending (unvetted) spots**, stages them for human review,
and promotes them to production as `sites` rows with `vetting_status='pending'` —
plus the vetting loop that later flips them to `vetted` via the existing menu-photo
flow.

## Prerequisites (from the master plan)

- cartoTaco migration `030_add_vetting_status_to_sites.sql` — adds
  `vetting_status`, `source`, `source_url`, `scraped_at`, `vetted_at` to `sites`.
- cartoTaco migration `031_add_vetting_status_to_view.sql` — exposes
  `vetting_status`/`source`/`source_url` in `sites_complete`.

---

## 1. Pipeline Overview

```
name/URL input ──► scrape (requests+bs4) ──► Claude structuring ──► geocode
                                                                      │
      production ◄── promote-as-pending ◄── human review ◄── stage (+ dedup check)
```

Everything is admin-initiated and human-in-the-loop, mirroring the menu-photo flow:
nothing reaches production without a review step, and all writes use the service-role
key as today.

## 2. New Module: `src/scraping.py`

**Input modes (page UI offers both):**
1. **Direct URL(s)** — the spot's own website, Instagram page, or a listing page the
   admin found manually. This is the primary, most reliable mode.
2. **Name search** — "El Ejemplo Tucson" → optional search-API step (Tavily or
   SerpAPI, key via `.env`, feature-gated: if no key configured, the UI only offers
   URL mode) → admin picks which result URLs to fetch.

**Functions:**
- `fetch_page(url) -> str` — `requests` GET with a real UA string, timeout, and
  `robots.txt` check; raises a clear error on non-200.
- `clean_html(html) -> str` — `beautifulsoup4`: strip script/style/nav, collapse
  whitespace, cap length (~20k chars) before sending to Claude.
- `scrape_spot(urls: list[str]) -> tuple[ScrapedSpot, dict]` — fetch + clean each
  URL, assemble a text bundle labeled per-source, call Claude (same
  prompt-plus-schema pattern as `extraction.py`), validate, return
  `(model, raw_json)`.

**Compliance rules (encode in module docstring + system prompt):**
- Scrape the business's own site and general public listings only. Do **not** scrape
  Google Maps/Places content (ToS prohibits storing it); do not bypass paywalls or
  logins; honor robots.txt.
- Descriptions are AI-*written from* scraped facts, never copied text — the
  short_descrip prompt should say "write an original 2–3 sentence description".

**New dependencies (`requirements.txt`):** `beautifulsoup4`, and optionally
`tavily-python` (or plain `requests` against the SerpAPI endpoint) behind the env
flag. `requests` comes in transitively today but should be pinned explicitly once
imported directly.

## 3. New Model: `ScrapedSpot` (`src/models.py`)

A deliberately thin subset — **no menu/protein/salsa**; that data is what vetting
produces later:

```python
class ScrapedSpot(BaseModel):
    """Preliminary spot data assembled from web scraping (pending vetting)."""
    restaurant_name: str
    site: SiteData = Field(default_factory=SiteData)          # reuse as-is
    hours: HoursData = Field(default_factory=HoursData)        # reuse (normalize_time applies)
    description: DescriptionData = Field(default_factory=DescriptionData)
    confidence: dict[str, str] = Field(                        # per-section: high/medium/low
        default_factory=dict,
        description="Per-section extraction confidence, e.g. {'hours': 'low'}",
    )
    evidence_urls: list[str] = Field(default_factory=list)
```

Claude is instructed to fill `confidence` per section ("high" only when the source
states it explicitly) and leave anything unstated empty rather than guessing.
Confidence is admin-facing only — it renders in review UI and is stored in staging,
never in production.

## 4. Geocoding + Dedup (`src/scraping.py` or small `src/geocode.py`)

- `geocode_address(address) -> tuple[lat, lon] | None` — Mapbox Geocoding API
  (`MAPBOX_KEY` in `.env`; the org already has one for the main app) with Nominatim
  as a keyless fallback. Bias results to a Tucson bounding box.
- Dedup, run before staging and surfaced in the page UI:
  1. `find_sites_by_name(name)` (exists in `promotion.py`) — case-insensitive
     substring match against production sites.
  2. Proximity check: any existing site within ~150 m of the geocoded point.
  3. Staging check: any non-rejected `staging_extractions` row with a similar
     `restaurant_name`.
  Matches render as warnings with the matched name/address; the admin explicitly
  clicks past them ("Stage anyway") or aborts.

## 5. Staging Changes

**Reuse `staging_extractions`** (single-table JSONB staging is this repo's design
decision) rather than a parallel table — the review UI carries over almost entirely.

**Migration `010_add_pipeline_to_staging.sql`:**

```sql
ALTER TABLE public.staging_extractions
  ADD COLUMN IF NOT EXISTS pipeline TEXT NOT NULL DEFAULT 'menu_photo'
    CHECK (pipeline IN ('menu_photo', 'web_scrape')),
  ADD COLUMN IF NOT EXISTS source_urls JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS scrape_confidence JSONB;

COMMENT ON COLUMN public.staging_extractions.pipeline IS
  'menu_photo = vetted-data extraction; web_scrape = preliminary pending-spot scouting';
```

Also update `009_master_schema.sql` and this repo's `CLAUDE.md` schema section.

**`src/staging.py`:** add `save_scraped_spot(spot, raw_json, urls) -> str` — writes a
row with `pipeline='web_scrape'`, `site_data`/`hours_data`/`description_data`
populated, `menu_data`/`protein_data`/`salsa_data` as empty `{}`, `source_urls`, and
`scrape_confidence`. `list_extractions()` gains an optional `pipeline=` filter.

## 6. Pages

### New `pages/5_Scrape_New_Spots.py`

Workflow (mirrors `1_Upload_and_Extract.py`'s extract → review → save shape):

1. **Input**: URL text-area (one per line) and/or name search (if search API
   configured).
2. **Scrape & structure**: spinner → `scrape_spot()` → show the `ScrapedSpot` in an
   editable form (name, type, address, phone, website, socials, hours grid,
   short/long description) with per-section confidence chips (🟢/🟡/🔴).
3. **Geocode**: auto-run on the address; show lat/lon with a small `st.map` preview;
   manual lat/lon override fields.
4. **Dedup panel**: warnings per §4; block the save button until acknowledged.
5. **Save to staging** → status `pending_review`, `pipeline='web_scrape'`.

### `pages/2_Staging_Review.py`

- Add a pipeline filter (All / Menu photos / Scraped spots).
- For `web_scrape` rows: hide the menu/protein/salsa edit sections, show
  `source_urls` as links + confidence chips. Approve/reject unchanged.

### `pages/3_Promote.py`

- For `web_scrape` rows, the promote panel labels the action **"Promote as pending
  spot"** and shows what will (and won't) be written.
- **Pending sites section** (new): list production sites where
  `vetting_status='pending'`, each with a "Retract" (delete) button for
  closed/bogus spots, and a "Mark vetted manually" escape hatch.

## 7. Promotion Changes (`src/promotion.py`)

`promote(row_id, est_id=None)` branches on the staging row's `pipeline`:

**`web_scrape` path (new):**
- `sites` upsert gains: `vetting_status='pending'`, `source='web_scrape'`,
  `source_url=source_urls[0]`, `scraped_at=row.created_at`, plus geocoded
  `lat_1`/`lon_1`.
- Write `descriptions` and `hours` rows **only if they contain data** (an all-empty
  hours row would make the frontend's "Open now" logic see explicit nulls — harmless,
  but skipping keeps production clean).
- **Skip `menu`/`protein`/`salsa` entirely** — no stub rows. The `sites_complete`
  view's LEFT JOINs handle their absence, and the frontend renders the preliminary
  card for `vetting_status='pending'`.
- est_id allocation unchanged (max+1 pattern).

**`menu_photo` path — the vetting flip:**
- When promoting into an existing `est_id`, read the current site row first; if
  `vetting_status='pending'`, include `vetting_status='vetted'`,
  `vetted_at=now()` (and leave `source`/`source_url`/`scraped_at` as provenance
  history) in the sites upsert.
- The est_id picker (`get_all_sites`) returns `vetting_status` so pending targets
  render with a "⏳ pending" suffix, and the name-dedup match pre-selects the pending
  row as the default target — visiting a scouted spot should funnel into its
  existing `est_id`, not create a duplicate.

**New helper:** `retract_pending_site(est_id)` — guard-checked delete
(`vetting_status='pending'` only; refuses to delete vetted sites) that removes the
site row and any descriptions/hours children. Requires the master plan's §2.3 FK
cascade check for favorites.

## 8. Testing (`pytest`, mirroring existing test style)

- `test_models.py`: `ScrapedSpot` validation — hours normalization via
  `normalize_time`, empty-by-default sections, confidence dict shape.
- New `test_scraping.py`: `clean_html` on fixture HTML (strips chrome, caps length);
  prompt assembly includes each source URL label; response-fence stripping (reuse the
  pattern from `extraction.py` — consider extracting the fence-stripper into a shared
  helper while here).
- `test_promotion.py` (new, mocked Supabase client):
  - web_scrape path writes sites (+status fields) and skips menu/protein/salsa;
  - hours/descriptions skipped when empty;
  - menu_photo promotion into a pending est_id flips `vetting_status` and sets
    `vetted_at`;
  - `retract_pending_site` refuses non-pending targets.

## 9. Work Order

1. Migration 010 + master-schema/CLAUDE.md updates (can ship with cartoTaco 030/031).
2. `ScrapedSpot` model + `scraping.py` (fetch/clean/structure) + tests.
3. Geocoding + dedup helpers + tests.
4. `staging.py` additions; page 5; Staging Review pipeline filter.
5. Promotion: pending path, vetting flip, pending-sites/retract section; tests.
6. Update `CLAUDE.md` (key files, schema, design decisions: "pending spots carry no
   menu/protein/salsa rows until vetted").

## 10. Non-Goals (v1)

- No scheduled/automated scraping — every run is admin-initiated in Streamlit.
- No bulk scraping (one candidate spot per run; the review step is the point).
- No confidence data promoted to production.
- No scraping of menu contents — menu data enters only through the vetted
  photo-extraction pipeline.
