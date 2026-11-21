# CartoTaco Menu Extract

An internal admin tool for [CartoTaco](https://github.com/keatonwilson/cartoTacoMenuExtract) — a guide to Mexican food in Tucson, AZ. Upload menu photos, extract structured data with Claude Vision, review and edit it, then promote to the CartoTaco production database.

## What It Does

1. **Upload & Extract** — Upload menu photo(s), send them to Claude Vision, and get back structured data: menu items, proteins, hours, salsas, site info, and AI-estimated item proportions.
2. **Staging Review** — Browse, edit, and approve/reject extracted data before it hits production. Includes web enrichment (auto-fills phone, address, hours from the web) and AI description generation.
3. **Promote** — Push approved extractions into the CartoTaco production database across 6 tables.
4. **Spec Tables** — Manage `item_spec` and `protein_spec` global reference tables with CRUD UI and AI-generated descriptions.
5. **Salsa Field Notes** — Turn a photo taken at a spot into a Salsa Atlas sighting: the spot is suggested from the photo's GPS, colours are sampled after white-balancing against a grey card, and new salsa styles are saved as drafts until published. Each visit can also correct the spot's survey markings (which of the 8 salsa types it serves, and how many salsas), which add or drop the spot's links in the atlas. Needs cartoTaco migrations 036–039.

   Re-promoting a menu extraction for a spot re-writes those markings from the extraction, undoing the fieldwork. Re-check them on the Sightings tab afterwards.

## Tech Stack

- **Python + Streamlit** — Web UI
- **Claude Vision API** (`claude-sonnet-4-20250514`) — Menu photo extraction, description generation, web enrichment
- **Supabase** — Staging table (JSONB), production tables, image storage
- **Pydantic** — Data validation

## Setup

### Prerequisites

- Python 3.10+
- Anthropic API key
- Supabase project with service role key

### Install

```bash
git clone https://github.com/keatonwilson/cartoTacoMenuExtract.git
cd cartoTacoMenuExtract
/opt/homebrew/bin/python3.12 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt   # one-time setup
cp .env.example .env
```

Edit `.env` with your keys:

```
ANTHROPIC_API_KEY=sk-ant-...
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=eyJ...
```

### Database Setup

1. Execute `migrations/001_create_staging_tables.sql` in the Supabase SQL editor
2. Create a `menu-photos` storage bucket (public) in Supabase Dashboard > Storage
3. Create a `spec-images` storage bucket (public) for item_spec images

### Run

```bash
.venv/bin/python -m streamlit run app.py   # prod (default)
```

`.env` holds two Supabase projects. `SUPABASE_URL`/`SUPABASE_SERVICE_KEY` are
**prod**, and the app uses them for everything: menu extraction, promotion and
Salsa Field Notes (the atlas is curated on prod; staging is seeded from it).
`SUPABASE_STAGING_URL`/`SUPABASE_STAGING_SERVICE_KEY` are for scripts that also
touch staging. To run one against staging, swap them in for that run
(`load_dotenv()` doesn't override variables already set in the shell):

```bash
SUPABASE_URL=$(grep ^SUPABASE_STAGING_URL= .env | cut -d= -f2-) \
SUPABASE_SERVICE_KEY=$(grep ^SUPABASE_STAGING_SERVICE_KEY= .env | cut -d= -f2-) \
.venv/bin/python -m src.similarity --dry-run
```

Use `.venv/bin/python` for everything: on this machine `python3` is Homebrew 3.15
with no packages, and a bare `pip` is a dead Python 2.7 shim.

## Production Tables

All keyed by `est_id`:

| Table | Description |
|-------|-------------|
| `sites` | Name, type, address, phone, website, social, coordinates |
| `menu` | Boolean flags + proportions for 17 item types, tortilla info, specialty items |
| `protein` | Boolean flags + proportions for 5 protein categories, up to 3 styles each |
| `hours` | Open/close times for each day of the week (24h format) |
| `salsa` | Total count, boolean flags for 8 types, up to 3 custom salsas |
| `descriptions` | Short/long descriptions, region |

Reference tables:

| Table | Description |
|-------|-------------|
| `item_spec` | Specialty item definitions (name, descriptions, origin, image) |
| `protein_spec` | Protein preparation definitions (name, descriptions, origin) |

## Testing

```bash
.venv/bin/python -m pytest tests/   # pytest once: .venv/bin/python -m pip install pytest
```

## Project Structure

```
app.py                          # Home dashboard
pages/
  1_Upload_and_Extract.py       # Upload → extract → review → save
  2_Staging_Review.py           # Browse/edit staging, approve/reject
  3_Promote.py                  # Promote approved rows to production
  4_Spec_Tables.py              # CRUD for item_spec / protein_spec
src/
  config.py                     # Env vars and constants
  supabase_client.py            # Supabase client singleton
  models.py                     # Pydantic models (mirrors production schema)
  extraction.py                 # Claude Vision extraction
  staging.py                    # Staging table CRUD
  promotion.py                  # Staging → production upserts
  spec_tables.py                # Spec table CRUD
  description_gen.py            # AI descriptions + web enrichment
tests/
  test_models.py                # Model validation tests
  test_extraction.py            # Image resize tests
migrations/
  001_create_staging_tables.sql # Staging table DDL
  002_spec_images_bucket.md     # Spec images bucket setup note
```
