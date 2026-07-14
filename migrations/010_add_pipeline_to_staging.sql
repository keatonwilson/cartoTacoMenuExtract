-- Migration 010: Add pipeline + scrape provenance columns to staging_extractions.
-- Supports the unvetted-spots feature: web-scraped preliminary spots share the
-- staging table (and most of the review UI) with menu-photo extractions, and
-- are promoted to production as sites with vetting_status = 'pending'.
--
-- Requires cartoTaco migrations 030/031 on the production side
-- (vetting_status/source/source_url/scraped_at/vetted_at on sites).

ALTER TABLE public.staging_extractions
  ADD COLUMN IF NOT EXISTS pipeline TEXT NOT NULL DEFAULT 'menu_photo'
    CHECK (pipeline IN ('menu_photo', 'web_scrape')),
  ADD COLUMN IF NOT EXISTS source_urls JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS scrape_confidence JSONB;

COMMENT ON COLUMN public.staging_extractions.pipeline IS
  'menu_photo = vetted-data extraction; web_scrape = preliminary pending-spot scouting';
COMMENT ON COLUMN public.staging_extractions.source_urls IS
  'URLs the scouting run cited as evidence; the first becomes sites.source_url on promotion';
COMMENT ON COLUMN public.staging_extractions.scrape_confidence IS
  'Per-section extraction confidence (admin-facing only, never promoted)';
