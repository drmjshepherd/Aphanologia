-- 1. Add the new column
ALTER TABLE taxonomy
    ADD COLUMN IF NOT EXISTS "acceptedNameUsageID" TEXT REFERENCES taxonomy("taxonID");

-- 2. Populate for true synonyms
UPDATE taxonomy
SET "acceptedNameUsageID" = "parentNameUsageID"
WHERE "taxonomicStatus" = 'synonym';

-- 3. Populate for pinned ("sensu") misapplications only
UPDATE taxonomy
SET "acceptedNameUsageID" = "parentNameUsageID"
WHERE "taxonomicStatus" = 'misapplied'
  AND "scientificnameAuthorship" ILIKE '%sensu%';

-- 4. doubtful, and unpinned misapplied rows: acceptedNameUsageID stays NULL
