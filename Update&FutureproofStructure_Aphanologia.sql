-- =========================================================================
-- 1. EXTEND LITERATURE JUNCTION FOR IDENTIFICATION KEYS & ONLINE RESOURCES
-- =========================================================================
ALTER TABLE taxonomy_literature_junction 
  ADD COLUMN IF NOT EXISTS is_identification_key BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS key_scope_rank VARCHAR(50),
  ADD COLUMN IF NOT EXISTS online_resource_url TEXT,
  ADD COLUMN IF NOT EXISTS access_notes TEXT;

-- =========================================================================
-- 2. ADD VERIFICATION STATUS & GBIF / NBN ATLAS SYNC FIELDS TO OBSERVATIONS
-- =========================================================================
ALTER TABLE observations 
  ADD COLUMN IF NOT EXISTS verification_status VARCHAR(30) DEFAULT 'unverified',
  ADD COLUMN IF NOT EXISTS verified_by VARCHAR(150),
  ADD COLUMN IF NOT EXISTS verified_date TIMESTAMP WITH TIME ZONE,
  ADD COLUMN IF NOT EXISTS verification_notes TEXT,
  ADD COLUMN IF NOT EXISTS dwc_occurrence_id UUID DEFAULT gen_random_uuid(),
  ADD COLUMN IF NOT EXISTS share_with_nbn BOOLEAN DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS share_with_gbif BOOLEAN DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS nbn_export_date TIMESTAMP WITH TIME ZONE,
  ADD COLUMN IF NOT EXISTS coordinate_uncertainty_meters INT DEFAULT 100;

-- =========================================================================
-- 3. SPECIMEN MEDIA / PHOTOGRAPHS TABLE (TYPE MATCHED)
-- =========================================================================
CREATE TABLE IF NOT EXISTS observation_media (
    media_id SERIAL PRIMARY KEY,
    observation_id TEXT REFERENCES observations("observationID") ON DELETE CASCADE,
    specimen_id TEXT REFERENCES specimens("specimenID") ON DELETE SET NULL,
    media_type VARCHAR(50) DEFAULT 'photo',
    file_url TEXT NOT NULL,
    thumbnail_url TEXT,
    caption TEXT,
    photographer VARCHAR(150),
    license VARCHAR(50) DEFAULT 'CC-BY-4.0',
    is_primary_for_taxon BOOLEAN DEFAULT FALSE,
    community_votes INT DEFAULT 0,
    uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================================
-- 4. MOLECULAR / DNA BARCODE TABLE (TYPE MATCHED)
-- =========================================================================
CREATE TABLE IF NOT EXISTS specimen_barcodes (
    barcode_id SERIAL PRIMARY KEY,
    specimen_id TEXT REFERENCES specimens("specimenID") ON DELETE CASCADE,
    gene_target VARCHAR(50) NOT NULL,
    ncbi_genbank_accession VARCHAR(50),
    bold_process_id VARCHAR(50),
    sequence_data TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================================
-- 5. INDEXES FOR FAST API / SPATIAL LOOKUPS
-- =========================================================================
CREATE INDEX IF NOT EXISTS idx_obs_verification ON observations(verification_status);
CREATE INDEX IF NOT EXISTS idx_media_obs ON observation_media(observation_id);
CREATE INDEX IF NOT EXISTS idx_tax_lit_key ON taxonomy_literature_junction(is_identification_key);
