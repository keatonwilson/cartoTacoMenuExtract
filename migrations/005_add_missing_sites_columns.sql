-- Add columns to sites table that may be missing from the original manual creation.
-- Safe to run multiple times (IF NOT EXISTS).
ALTER TABLE sites
  ADD COLUMN IF NOT EXISTS contact text,
  ADD COLUMN IF NOT EXISTS lat_1 float,
  ADD COLUMN IF NOT EXISTS lon_1 float,
  ADD COLUMN IF NOT EXISTS days_loc_1 text,
  ADD COLUMN IF NOT EXISTS lat_2 float,
  ADD COLUMN IF NOT EXISTS lon_2 float,
  ADD COLUMN IF NOT EXISTS days_loc_2 text;
