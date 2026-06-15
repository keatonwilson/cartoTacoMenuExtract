-- Master schema migration — idempotent, supersedes 004–007.
-- Reflects the ACTUAL live production schema. Run this on a database that
-- already has the base sites/menu/protein/salsa/hours/descriptions tables to
-- bring it up to the current schema. Safe to run multiple times.
--
-- NOTE: the live tables store specialty/protein/salsa FK ids in spec_id_*
-- columns (NOT specialty_item_id_*/protein_spec_id_*/salsa_spec_id_*), and the
-- live sites table has no `contact` column. Earlier drafts of 004–007 diverged
-- from this; do not reintroduce those names.

-- ============================================================
-- sites: nothing to add — the live table has no additional columns.
-- (SiteData.contact is captured during extraction but is not promoted; there
--  is no `contact` column in the live sites table.)
-- ============================================================

-- ============================================================
-- menu: add missing columns
-- ============================================================
ALTER TABLE menu
  ADD COLUMN IF NOT EXISTS burro_perc numeric,
  ADD COLUMN IF NOT EXISTS taco_perc numeric,
  ADD COLUMN IF NOT EXISTS torta_perc numeric,
  ADD COLUMN IF NOT EXISTS dog_perc numeric,
  ADD COLUMN IF NOT EXISTS plate_perc numeric,
  ADD COLUMN IF NOT EXISTS cocktail_perc numeric,
  ADD COLUMN IF NOT EXISTS gordita_perc numeric,
  ADD COLUMN IF NOT EXISTS huarache_perc numeric,
  ADD COLUMN IF NOT EXISTS cemita_perc numeric,
  ADD COLUMN IF NOT EXISTS flauta_perc numeric,
  ADD COLUMN IF NOT EXISTS chalupa_perc numeric,
  ADD COLUMN IF NOT EXISTS molote_perc numeric,
  ADD COLUMN IF NOT EXISTS tostada_perc numeric,
  ADD COLUMN IF NOT EXISTS enchilada_perc numeric,
  ADD COLUMN IF NOT EXISTS tamale_perc numeric,
  ADD COLUMN IF NOT EXISTS sope_perc numeric,
  ADD COLUMN IF NOT EXISTS caldo_perc numeric,
  ADD COLUMN IF NOT EXISTS specialty_item_1 text,
  ADD COLUMN IF NOT EXISTS specialty_item_2 text,
  ADD COLUMN IF NOT EXISTS specialty_item_3 text,
  ADD COLUMN IF NOT EXISTS specialty_item_4 text,
  ADD COLUMN IF NOT EXISTS spec_id_1 integer,
  ADD COLUMN IF NOT EXISTS spec_id_2 integer,
  ADD COLUMN IF NOT EXISTS spec_id_3 integer;

-- ============================================================
-- protein: add missing columns
-- ============================================================
ALTER TABLE protein
  ADD COLUMN IF NOT EXISTS chicken_perc numeric,
  ADD COLUMN IF NOT EXISTS beef_perc numeric,
  ADD COLUMN IF NOT EXISTS pork_perc numeric,
  ADD COLUMN IF NOT EXISTS fish_perc numeric,
  ADD COLUMN IF NOT EXISTS veg_perc numeric,
  ADD COLUMN IF NOT EXISTS protein_spec_1 text,
  ADD COLUMN IF NOT EXISTS protein_spec_2 text,
  ADD COLUMN IF NOT EXISTS protein_spec_3 text,
  ADD COLUMN IF NOT EXISTS spec_id_1 integer,
  ADD COLUMN IF NOT EXISTS spec_id_2 integer,
  ADD COLUMN IF NOT EXISTS spec_id_3 integer;

-- ============================================================
-- salsa: add missing columns
-- ============================================================
ALTER TABLE salsa
  ADD COLUMN IF NOT EXISTS heat_overall integer,
  ADD COLUMN IF NOT EXISTS other_1_heat integer,
  ADD COLUMN IF NOT EXISTS other_2_heat integer,
  ADD COLUMN IF NOT EXISTS other_3_heat integer,
  ADD COLUMN IF NOT EXISTS salsa_spec_1 text,
  ADD COLUMN IF NOT EXISTS salsa_spec_2 text,
  ADD COLUMN IF NOT EXISTS spec_id_1 integer,
  ADD COLUMN IF NOT EXISTS spec_id_2 integer;

-- ============================================================
-- descriptions: add missing columns
-- ============================================================
ALTER TABLE descriptions
  ADD COLUMN IF NOT EXISTS last_updated timestamptz;
