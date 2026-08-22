CREATE OR REPLACE FUNCTION get_ancestor_chain(start_taxon_id TEXT)
RETURNS TABLE(taxon_id TEXT, depth INT) AS $$
WITH RECURSIVE resolved AS (
    -- If the starting taxon is a synonym/pinned misapplication, jump
    -- straight to its accepted name's hierarchy position first
    SELECT COALESCE(t."acceptedNameUsageID", t."taxonID") AS hierarchy_taxon_id
    FROM taxonomy t
    WHERE t."taxonID" = start_taxon_id
),
climb AS (
    SELECT t."taxonID", t."parentNameUsageID", 0 AS depth
    FROM taxonomy t
    JOIN resolved r ON t."taxonID" = r.hierarchy_taxon_id

    UNION ALL

    SELECT p."taxonID", p."parentNameUsageID", climb.depth + 1
    FROM taxonomy p
    JOIN climb ON p."taxonID" = climb."parentNameUsageID"
)
SELECT "taxonID" AS taxon_id, depth FROM climb ORDER BY depth DESC;
$$ LANGUAGE sql STABLE;
