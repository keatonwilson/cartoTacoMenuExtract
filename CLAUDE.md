# CartoTaco Menu Extract

Menu photo extraction toolkit for the CartoTaco project. Upload menu photos, extract structured data via Claude Vision, review/edit, then promote to the CartoTaco Supabase production database.

## Architecture

- **Python + Streamlit** web app
- **Claude Vision API** (claude-sonnet-4-20250514) for menu extraction
- **Supabase** for staging table + production tables + image storage

## Key Files

- `src/extraction.py` — Claude Vision prompt + API call (core intelligence)
- `src/models.py` — Pydantic models mirroring production DB schema
- `src/staging.py` — Staging table CRUD
- `src/promotion.py` — Staging → production upserts across 6 tables
- `src/spec_tables.py` — CRUD for `item_spec` and `protein_spec` reference tables
- `src/description_gen.py` — AI description generation (restaurants + spec entries)
- `pages/1_Upload_and_Extract.py` — Primary workflow: upload → extract → review → save
- `pages/2_Staging_Review.py` — Browse/edit staging data, approve/reject
- `pages/3_Promote.py` — Promote approved rows to production
- `pages/4_Spec_Tables.py` — CRUD UI for item_spec and protein_spec with AI descriptions

## Production Tables (CartoTaco)

`sites`, `descriptions`, `menu`, `hours`, `salsa`, `protein` — all keyed by `est_id`.
`item_spec`, `protein_spec` — global reference tables for specialty items and proteins.

## Running

```bash
cp .env.example .env  # Fill in API keys
pip install -r requirements.txt
streamlit run app.py
```

## Before First Run

Execute `migrations/001_create_staging_tables.sql` in Supabase SQL editor.
Create a `menu-photos` storage bucket (public) in Supabase dashboard.
Create a `spec-images` storage bucket (public) for item_spec images (see `migrations/002_spec_images_bucket.md`).

## Testing

```bash
python -m pytest tests/
```

## Design Decisions

- Staging uses single table with JSONB columns (simpler than 6 mirror tables)
- `_perc` fields are AI-estimated proportions (0.0-1.0, summing to 1.0) for menu item and protein prominence
- `heat_overall` is skipped in extraction (editorial/subjective)
- Specialty item FKs left null — manual linking after promotion
- Service role key only (admin tool, no public access)
