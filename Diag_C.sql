-- Diag-C: For each misapplied taxonID, how many DISTINCT revised_taxon_id 
-- values appear across its manually-overridden observations?
SELECT
    t."taxonID" AS original_misapplied_taxon_id,
    t."scientificName",
    t."scientificnameAuthorship",
    COUNT(DISTINCT ov.revised_taxon_id) AS distinct_revised_targets,
    COUNT(DISTINCT ov.revised_taxon_id) FILTER (WHERE ov.revised_taxon_id = t."taxonID") AS confirms_self,
    STRING_AGG(DISTINCT ov.revised_taxon_id, ', ') AS revised_targets_list,
    COUNT(*) AS n_overridden_observations
FROM taxonomy t
JOIN observations o ON o."taxonID" = t."taxonID"
JOIN observation_taxonomy_override ov ON ov.observation_id = o."observationID"
WHERE t."taxonomicStatus" = 'misapplied'
GROUP BY t."taxonID", t."scientificName", t."scientificnameAuthorship"
ORDER BY distinct_revised_targets DESC, t."scientificName";
