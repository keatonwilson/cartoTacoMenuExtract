-- Add contact field to sites table
ALTER TABLE sites ADD COLUMN IF NOT EXISTS contact text;
