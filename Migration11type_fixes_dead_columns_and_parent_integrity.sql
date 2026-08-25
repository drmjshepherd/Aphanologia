-- Migration 11: Column type fixes, dead-column cleanup, and
-- parentNameUsageID integrity.
--
-- Run this top to bottom in pgAdmin's Query Tool. Each step is
-- independent and safe to review before the next one runs. If any
-- step errors, STOP and check the error message before continuing -
-- don't just re-run the whole script from the top.

-- ==========================================================
-- STEP 1: Fix columns mistyped as double precision that should be
-- text - the same "blank columns on bulk import got the wrong type"
-- bug you've hit before (samplingProtocol, samplesizeUnit,
-- identificationVerificationStatus, idText[free_text] were all fixed
-- this same way previously). These three are the ones flagged as
-- "likely same issue, not yet needed" plus one newly spotted via the
-- schema viewer.
-- ==========================================================

ALTER TABLE observations
    ALTER COLUMN "verifiedBy" TYPE text USING "verifiedBy"::text;

ALTER TABLE observations
    ALTER COLUMN "litID" TYPE text USING "litID"::text;

ALTER TABLE literature
    ALTER COLUMN "litNotes" TYPE text USING "litNotes"::text;

-- Verify: these should now all show 'text'
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public'
  AND (table_name, column_name) IN (
      ('observations', 'verifiedBy'),
      ('observations', 'litID'),
      ('literature', 'litNotes')
  );


-- ==========================================================
-- STEP 2: Drop specimens.specBarcode and specimens.specPhotos.
-- Confirmed these never held any data in the original import, and
-- have been functionally superseded: barcode data now belongs in
-- specimen_barcodes (supports multiple gene targets per specimen,
-- which a single column never could), and photos already go through
-- observation_media (which links directly to specimen_id). Keeping
-- these around would just be a second, wrong place for this data to
-- live, and their double-precision typing was never correct anyway.
-- ==========================================================

ALTER TABLE specimens DROP COLUMN IF EXISTS "specBarcode";
ALTER TABLE specimens DROP COLUMN IF EXISTS "specPhotos";


-- ==========================================================
-- STEP 3: Drop the two leftover "Unnamed" columns from
-- taxonomy_literature_junction. Confirmed these were a working
-- lookup formula (column E in the original spreadsheet) that was
-- never meant to be part of the upload - only columns A, B, and C
-- (taxonid, Type, litID) were intended to come across.
-- ==========================================================

ALTER TABLE taxonomy_literature_junction DROP COLUMN IF EXISTS "Unnamed: 3";
ALTER TABLE taxonomy_literature_junction DROP COLUMN IF EXISTS "Unnamed: 4";


-- ==========================================================
-- STEP 4: parentNameUsageID integrity check, then enforce it.
--
-- First, a diagnostic: any row where parentNameUsageID is set but
-- doesn't point at a real taxonID would be a genuine data problem
-- worth knowing about BEFORE we try to lock this down permanently.
-- Animalia (the root of the tree) is the one taxon that SHOULD have
-- a blank/NULL parentNameUsageID - everything else should point
-- somewhere real.
-- ==========================================================

-- 4a. Any orphaned parent references? (should return 0 rows)
SELECT "taxonID", "scientificName", "parentNameUsageID"
FROM taxonomy t
WHERE "parentNameUsageID" IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM taxonomy parent WHERE parent."taxonID" = t."parentNameUsageID"
  );

-- 4b. Confirm Animalia is the only taxon with a NULL parent (should
-- return exactly one row: Animalia)
SELECT "taxonID", "scientificName", "parentNameUsageID"
FROM taxonomy
WHERE "parentNameUsageID" IS NULL;

-- 4c. If (and only if) both checks above look right - 4a returns
-- zero rows, and 4b returns just Animalia - add a real foreign key
-- constraint so the database itself will refuse any future row that
-- breaks this rule, the same protection acceptedNameUsageID already
-- has. If either check above showed a problem, STOP here and fix
-- that data first - this ALTER TABLE will fail loudly (rather than
-- silently corrupt anything) if any row still violates it, which is
-- exactly what we want.
ALTER TABLE taxonomy
    ADD CONSTRAINT fk_taxonomy_parent
    FOREIGN KEY ("parentNameUsageID") REFERENCES taxonomy("taxonID");
