-- Add columns to menu and protein tables that may be missing from original creation.
-- Safe to run multiple times (IF NOT EXISTS).

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
  -- FK columns to item_spec; the live table names these spec_id_*, not specialty_item_id_*
  ADD COLUMN IF NOT EXISTS spec_id_1 integer,
  ADD COLUMN IF NOT EXISTS spec_id_2 integer,
  ADD COLUMN IF NOT EXISTS spec_id_3 integer;

ALTER TABLE protein
  ADD COLUMN IF NOT EXISTS chicken_perc numeric,
  ADD COLUMN IF NOT EXISTS beef_perc numeric,
  ADD COLUMN IF NOT EXISTS pork_perc numeric,
  ADD COLUMN IF NOT EXISTS fish_perc numeric,
  ADD COLUMN IF NOT EXISTS veg_perc numeric,
  ADD COLUMN IF NOT EXISTS protein_spec_1 text,
  ADD COLUMN IF NOT EXISTS protein_spec_2 text,
  ADD COLUMN IF NOT EXISTS protein_spec_3 text,
  -- FK columns to protein_spec; the live table names these spec_id_*, not protein_spec_id_*
  ADD COLUMN IF NOT EXISTS spec_id_1 integer,
  ADD COLUMN IF NOT EXISTS spec_id_2 integer,
  ADD COLUMN IF NOT EXISTS spec_id_3 integer;
