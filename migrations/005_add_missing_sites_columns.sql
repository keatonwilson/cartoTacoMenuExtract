-- Add columns to sites table that may be missing from the original manual creation.
-- Safe to run multiple times (IF NOT EXISTS).
--
-- NOTE: the live sites table only has lat_1, lon_1, days_loc_1 (already present).
-- It does NOT have contact, lat_2, lon_2, or days_loc_2 — those statements were
-- never applied and are commented out to keep this file aligned with live.
ALTER TABLE sites
  ADD COLUMN IF NOT EXISTS lat_1 float,
  ADD COLUMN IF NOT EXISTS lon_1 float,
  ADD COLUMN IF NOT EXISTS days_loc_1 text;
  -- ADD COLUMN IF NOT EXISTS contact text,
  -- ADD COLUMN IF NOT EXISTS lat_2 float,
  -- ADD COLUMN IF NOT EXISTS lon_2 float,
  -- ADD COLUMN IF NOT EXISTS days_loc_2 text;
