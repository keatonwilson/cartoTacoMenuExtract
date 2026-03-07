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

## Production Database Schema (Supabase)

All main tables keyed by `est_id`. Reference tables keyed by `id`.

### sites
`est_id` (int, PK, NOT auto-generated), `name`, `type`, `address`, `phone`, `website`, `instagram`, `facebook`, `contact`, `lat_1` (float), `lon_1` (float), `days_loc_1`, `lat_2`, `lon_2`, `days_loc_2`, `last_updated`, `created_at`

### menu
`est_id` (int, PK/FK), `burro_yes` (bool), `taco_yes`, `torta_yes`, `dog_yes`, `plate_yes`, `cocktail_yes`, `gordita_yes`, `huarache_yes`, `cemita_yes`, `flauta_yes`, `chalupa_yes`, `molote_yes`, `tostada_yes`, `enchilada_yes`, `tamale_yes`, `sope_yes`, `caldo_yes`, `burro_perc` (numeric), `taco_perc`, `torta_perc`, `dog_perc`, `plate_perc`, `cocktail_perc`, `gordita_perc`, `huarache_perc`, `cemita_perc`, `flauta_perc`, `chalupa_perc`, `molote_perc`, `tostada_perc`, `enchilada_perc`, `tamale_perc`, `sope_perc`, `caldo_perc`, `flour_corn`, `handmade_tortilla` (bool), `specialty_item_1`, `specialty_item_2`, `specialty_item_3`, `specialty_item_4`, `specialty_item_id_1` (FK→item_spec), `specialty_item_id_2`, `specialty_item_id_3`

### protein
`est_id` (int, PK/FK), `chicken_yes` (bool), `beef_yes`, `pork_yes`, `fish_yes`, `veg_yes`, `chicken_perc` (numeric), `beef_perc`, `pork_perc`, `fish_perc`, `veg_perc`, `chicken_style_1`, `chicken_style_2`, `chicken_style_3`, `beef_style_1-3`, `pork_style_1-3`, `fish_style_1-3`, `veg_style_1-3`, `protein_spec_1`, `protein_spec_2`, `protein_spec_3`, `protein_spec_id_1` (FK→protein_spec), `protein_spec_id_2`, `protein_spec_id_3`

### hours
`est_id` (int, PK/FK), `mon_start`, `mon_end`, `tue_start`, `tue_end`, `wed_start`, `wed_end`, `thu_start`, `thu_end`, `fri_start`, `fri_end`, `sat_start`, `sat_end`, `sun_start`, `sun_end`

### salsa
`est_id` (int, PK/FK), `total_num` (int), `heat_overall` (int), `verde_yes` (bool), `rojo_yes`, `pico_yes`, `pickles_yes`, `chipotle_yes`, `avo_yes`, `molcajete_yes`, `macha_yes`, `salsa_spec_1`, `salsa_spec_2`, `salsa_spec_id_1`, `salsa_spec_id_2`, `other_1_name`, `other_1_heat`, `other_1_descrip`, `other_2_name`, `other_2_heat`, `other_2_descrip`, `other_3_name`, `other_3_heat`, `other_3_descrip`

### descriptions
`est_id` (int, PK/FK), `short_descrip`, `long_descrip`, `region`, `last_updated`

### item_spec (reference)
`id` (int, PK, serial), `name`, `short_descrip`, `long_descrip`, `origin`, `img_url`

### protein_spec (reference)
`id` (int, PK, serial), `name`, `short_descrip`, `long_descrip`, `origin`

### staging_extractions
`id` (uuid, PK), `status`, `est_id`, `restaurant_name`, `site_data` (jsonb), `menu_data` (jsonb), `protein_data` (jsonb), `hours_data` (jsonb), `salsa_data` (jsonb), `description_data` (jsonb), `source_image_urls` (jsonb), `extraction_model`, `raw_extraction` (jsonb), `notes`, `created_at`, `updated_at`

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
