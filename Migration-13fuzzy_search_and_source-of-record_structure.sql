-- Migration 13: Fuzzy search + source-of-record structure.
--
-- Three things in one migration, since they're all needed together
-- for the "where did this sample come from" feature:
--
-- 1. pg_trgm - PostgreSQL's trigram-matching extension. This is what
--    makes typo-tolerant ("fuzzy") search possible at the database
--    level, rather than needing every search box to fetch the whole
--    taxonomy/literature/project list and fuzzy-match client-side.
--    It also naturally fixes the "Nothrus buried under 15
--    Ameronothrus results" ranking problem, once combined with a
--    prefix-match boost in the search queries themselves.
--
-- 2. recording_projects + sample_project_junction - a new lightweight
--    reference table for formal survey/monitoring programmes and
--    biological records centre bulk downloads (e.g. England
--    Ecosystem Survey, Natural England LTM, ERCCIS), mirroring the
--    existing literature/sample_literature_junction pattern.
--
-- 3. web_litid_seq - so contributors can add a new literature entry
--    from the submission form when the reference they need isn't
--    already catalogued, the same way web_eventid_seq etc. already
--    let contributors create new samples/observations safely
--    alongside the ~25,000 imported historic rows.

-- ==========================================================
-- STEP 1: Fuzzy search infrastructure
-- ==========================================================

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS idx_taxonomy_scientificname_trgm
    ON taxonomy USING GIN ("scientificName" gin_trgm_ops);

-- A generated column so the same combined author/title/year text is
-- always used consistently for both searching AND the index - rather
-- than repeating a long CONCAT_WS expression in every query and
-- risking the index and the query drifting out of sync with each other.
ALTER TABLE literature ADD COLUMN IF NOT EXISTS search_text text
    GENERATED ALWAYS AS (
        COALESCE("authorName", '') || ' ' ||
        COALESCE("articleTitle", '') || ' ' ||
        COALESCE("yearPublished", '') || ' ' ||
        COALESCE("publicationTitle", '')
    ) STORED;

CREATE INDEX IF NOT EXISTS idx_literature_search_trgm
    ON literature USING GIN (search_text gin_trgm_ops);


-- ==========================================================
-- STEP 2: recording_projects + its junction to samples
-- ==========================================================

CREATE TABLE IF NOT EXISTS recording_projects (
    project_id SERIAL PRIMARY KEY,
    project_name text NOT NULL,
    project_category text NOT NULL CHECK (
        project_category IN ('Survey or monitoring programme', 'Biological records centre bulk download')
    ),
    website_url text,
    description text,
    submitted_by_user_id integer REFERENCES users(user_id),
    entered_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_recording_projects_name_trgm
    ON recording_projects USING GIN (project_name gin_trgm_ops);

CREATE TABLE IF NOT EXISTS sample_project_junction (
    "eventID" text NOT NULL REFERENCES samples("eventID"),
    project_id integer NOT NULL REFERENCES recording_projects(project_id),
    type text NOT NULL DEFAULT 'source of record',
    PRIMARY KEY ("eventID", project_id, type)
);


-- ==========================================================
-- STEP 3: sequence for contributor-added literature entries
-- ==========================================================

CREATE SEQUENCE IF NOT EXISTS web_litid_seq START WITH 1;


-- Verify:
SELECT 'recording_projects' AS check_item, COUNT(*) AS row_count FROM recording_projects
UNION ALL
SELECT 'sample_project_junction', COUNT(*) FROM sample_project_junction;

SELECT extname FROM pg_extension WHERE extname = 'pg_trgm';
