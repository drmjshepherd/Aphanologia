SELECT o."observationID", o."taxonID", t."scientificName", t."scientificnameAuthorship"
FROM observations o
JOIN taxonomy t ON o."taxonID" = t."taxonID"
LEFT JOIN observation_taxonomy_override ov ON o."observationID" = ov.observation_id
WHERE t."taxonomicStatus" = 'misapplied'
  AND ov.observation_id IS NULL;
