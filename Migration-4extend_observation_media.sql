ALTER TABLE observation_media
    ADD COLUMN IF NOT EXISTS sample_id TEXT REFERENCES samples("eventID") ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS demographic_id TEXT REFERENCES observation_demographics("demographicID") ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS taxon_id TEXT REFERENCES taxonomy("taxonID") ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS link_level TEXT;

ALTER TABLE observation_media
    ADD CONSTRAINT chk_media_link_level CHECK (
        (link_level = 'sample'       AND sample_id IS NOT NULL AND observation_id IS NULL AND demographic_id IS NULL AND specimen_id IS NULL AND taxon_id IS NULL)
     OR (link_level = 'observation'  AND observation_id IS NOT NULL AND sample_id IS NULL AND demographic_id IS NULL AND specimen_id IS NULL AND taxon_id IS NULL)
     OR (link_level = 'demographic'  AND demographic_id IS NOT NULL AND sample_id IS NULL AND observation_id IS NULL AND specimen_id IS NULL AND taxon_id IS NULL)
     OR (link_level = 'specimen'     AND specimen_id IS NOT NULL AND sample_id IS NULL AND observation_id IS NULL AND demographic_id IS NULL AND taxon_id IS NULL)
     OR (link_level = 'taxon'        AND taxon_id IS NOT NULL AND sample_id IS NULL AND observation_id IS NULL AND demographic_id IS NULL AND specimen_id IS NULL)
    );
