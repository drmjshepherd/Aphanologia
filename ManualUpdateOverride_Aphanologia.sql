CREATE OR REPLACE VIEW view_effective_observations AS
SELECT 
    o."observationID",
    o."eventID",
    -- Override misapplications first, fallback to recorded taxonID
    COALESCE(ov.revised_taxon_id, o."taxonID") AS raw_effective_taxon_id,
    -- Automatically follow acceptednameusageid if raw_effective_taxon_id is a synonym
    COALESCE(t_accepted."taxonID", t_direct."taxonID") AS resolved_taxon_id,
    COALESCE(t_accepted."scientificName", t_direct."scientificName") AS resolved_scientific_name,
    COALESCE(t_accepted."taxonrank", t_direct."taxonrank") AS resolved_taxon_rank
FROM observations o
LEFT JOIN observation_taxonomy_override ov ON o."observationID" = ov.observation_id
LEFT JOIN taxonomy t_direct ON COALESCE(ov.revised_taxon_id, o."taxonID") = t_direct."taxonID"
LEFT JOIN taxonomy t_accepted ON t_direct."acceptednameusageid" = t_accepted."taxonID";
