-- Migration 9: Backfill "acceptedNameUsageID" from the legacy lowercase
-- "acceptednameusageid" column, for taxa where the proper-cased column
-- was never populated.
--
-- WHY THIS IS NEEDED:
-- get_synonyms() and get_immediate_children() both rely ONLY on the
-- proper-cased "acceptedNameUsageID" column to decide whether a taxon
-- is a synonym/misapplication (and should be pulled out into the
-- dotted "synonyms" list) or an ordinary child taxon (and should
-- appear as a normal node in the tree).
--
-- 21 rows, all taxonomicStatus = 'misapplied', have "acceptedNameUsageID"
-- IS NULL, even though they DO have a value in the old lowercase
-- "acceptednameusageid" column left over from the original bulk import.
-- Because get_immediate_children() only excludes rows where
-- "acceptedNameUsageID" IS NOT NULL, these 21 rows currently render in
-- the taxonomy tree as if they were ordinary valid child taxa, sitting
-- underneath their parentNameUsageID as siblings to real children -
-- instead of being correctly grouped as a misapplication/synonym of
-- their true accepted taxon.
--
-- We already confirmed (via a prior diagnostic query) that wherever
-- BOTH columns are populated, they always agree - so this backfill is
-- safe: we are not overwriting any conflicting value, only filling in
-- gaps.
--
-- This migration does NOT drop the old "acceptednameusageid" column.
-- That's a separate decision to be made once we've confirmed
-- nothing else in the codebase still reads it.

-- STEP 1: Sanity check - confirm we still see exactly 21 affected rows
-- before making any changes. If this returns a different number than
-- 21, STOP and check what changed before proceeding.
SELECT COUNT(*) AS rows_to_be_fixed
FROM taxonomy
WHERE "taxonomicStatus" IN ('synonym', 'misapplied')
  AND "acceptedNameUsageID" IS NULL
  AND acceptednameusageid IS NOT NULL;

-- STEP 2: Do the backfill.
-- Only touches rows where the proper-cased column is empty AND the
-- legacy column has something to offer - never overwrites an existing
-- "acceptedNameUsageID" value.
UPDATE taxonomy
SET "acceptedNameUsageID" = acceptednameusageid
WHERE "acceptedNameUsageID" IS NULL
  AND acceptednameusageid IS NOT NULL;

-- STEP 3: Verify the fix.
-- This should now return 0 for synonym/misapplied rows with no
-- accepted ID at all (both columns empty), and the earlier "21 to fix"
-- count should now show 0 remaining.
SELECT
    COUNT(*) FILTER (WHERE "taxonomicStatus" IN ('synonym','misapplied') AND "acceptedNameUsageID" IS NULL) AS still_missing_accepted_id,
    COUNT(*) FILTER (WHERE "taxonomicStatus" IN ('synonym','misapplied')) AS total_synonyms_and_misapplied
FROM taxonomy;

-- If still_missing_accepted_id is 0, the fix is complete and every
-- synonym/misapplied taxon now has a proper "acceptedNameUsageID",
-- meaning get_immediate_children() will correctly exclude them from
-- the main tree and get_synonyms() will correctly pick them up.
