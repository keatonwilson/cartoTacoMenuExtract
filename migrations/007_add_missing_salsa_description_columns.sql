-- Add columns to salsa and descriptions tables that may be missing from original creation.
-- Safe to run multiple times (IF NOT EXISTS).

ALTER TABLE salsa
  ADD COLUMN IF NOT EXISTS heat_overall integer,
  ADD COLUMN IF NOT EXISTS other_1_heat integer,
  ADD COLUMN IF NOT EXISTS other_2_heat integer,
  ADD COLUMN IF NOT EXISTS other_3_heat integer,
  ADD COLUMN IF NOT EXISTS salsa_spec_1 text,
  ADD COLUMN IF NOT EXISTS salsa_spec_2 text,
  ADD COLUMN IF NOT EXISTS salsa_spec_id_1 integer,
  ADD COLUMN IF NOT EXISTS salsa_spec_id_2 integer;

ALTER TABLE descriptions
  ADD COLUMN IF NOT EXISTS last_updated timestamptz;
