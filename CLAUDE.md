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
- `pages/1_Upload_and_Extract.py` — Primary workflow: upload → extract → review → save
- `pages/2_Staging_Review.py` — Browse/edit staging data, approve/reject
- `pages/3_Promote.py` — Promote approved rows to production

## Production Tables (CartoTaco)

`sites`, `descriptions`, `menu`, `hours`, `salsa`, `protein` — all keyed by `est_id`.

## Running

```bash
cp .env.example .env  # Fill in API keys
pip install -r requirements.txt
streamlit run app.py
```

## Before First Run

Execute `migrations/001_create_staging_tables.sql` in Supabase SQL editor.
Create a `menu-photos` storage bucket (public) in Supabase dashboard.

## Testing

```bash
python -m pytest tests/
```

## Design Decisions

- Staging uses single table with JSONB columns (simpler than 6 mirror tables)
- `_perc` fields and `heat_overall` are skipped in extraction (editorial/subjective)
- Specialty item FKs left null — manual linking after promotion
- Service role key only (admin tool, no public access)
