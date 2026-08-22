CREATE OR REPLACE VIEW view_effective_observations AS
SELECT 
    o."observationID",
    o."eventID",
    COALESCE(ov.revised_taxon_id, o."taxonID") AS raw_effective_taxon_id,
    COALESCE(t_accepted."taxonID", t_direct."taxonID") AS resolved_taxon_id,
    COALESCE(t_accepted."scientificName", t_direct."scientificName") AS resolved_scientific_name,
    COALESCE(t_accepted."taxonrank", t_direct."taxonrank") AS resolved_taxon_rank,
    (
        t_direct."taxonomicStatus" = 'misapplied' 
        AND t_direct."acceptedNameUsageID" IS NULL 
        AND ov.observation_id IS NULL
    ) AS is_unresolved_misapplication
FROM observations o
LEFT JOIN observation_taxonomy_override ov ON o."observationID" = ov.observation_id
LEFT JOIN taxonomy t_direct ON COALESCE(ov.revised_taxon_id, o."taxonID") = t_direct."taxonID"
LEFT JOIN taxonomy t_accepted ON t_direct."acceptedNameUsageID" = t_accepted."taxonID";
