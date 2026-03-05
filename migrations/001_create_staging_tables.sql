-- Run this in the Supabase SQL editor to create the staging table.

CREATE TABLE IF NOT EXISTS public.staging_extractions (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    status text NOT NULL DEFAULT 'pending_review'
        CHECK (status IN ('pending_review', 'approved', 'promoted', 'rejected')),
    est_id integer REFERENCES public.sites(est_id),
    restaurant_name text NOT NULL,
    site_data jsonb NOT NULL DEFAULT '{}',
    menu_data jsonb NOT NULL DEFAULT '{}',
    protein_data jsonb NOT NULL DEFAULT '{}',
    hours_data jsonb NOT NULL DEFAULT '{}',
    salsa_data jsonb NOT NULL DEFAULT '{}',
    description_data jsonb NOT NULL DEFAULT '{}',
    source_image_urls text[] DEFAULT '{}',
    extraction_model text DEFAULT 'claude-sonnet-4-20250514',
    raw_extraction jsonb,
    notes text,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);

-- Auto-update updated_at on row changes.
CREATE OR REPLACE FUNCTION update_staging_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER staging_extractions_updated_at
    BEFORE UPDATE ON public.staging_extractions
    FOR EACH ROW
    EXECUTE FUNCTION update_staging_updated_at();

-- Create storage bucket for menu photos (run via Supabase dashboard or API).
-- INSERT INTO storage.buckets (id, name, public) VALUES ('menu-photos', 'menu-photos', true);
