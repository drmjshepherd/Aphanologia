CREATE OR REPLACE VIEW view_media_with_resolved_taxon AS
SELECT
    om.*,
    CASE
        WHEN om.link_level = 'taxon' THEN om.taxon_id
        WHEN om.link_level = 'observation' THEN veo_obs.resolved_taxon_id
        WHEN om.link_level = 'demographic' THEN veo_demo.resolved_taxon_id
        WHEN om.link_level = 'specimen' THEN veo_spec.resolved_taxon_id
        ELSE NULL
    END AS effective_taxon_id
FROM observation_media om
LEFT JOIN view_effective_observations veo_obs
    ON om.observation_id = veo_obs."observationID"
LEFT JOIN observation_demographics od_demo
    ON om.demographic_id = od_demo."demographicID"
LEFT JOIN view_effective_observations veo_demo
    ON od_demo."observationID" = veo_demo."observationID"
LEFT JOIN specimens sp_spec
    ON om.specimen_id = sp_spec."specimenID"
LEFT JOIN observation_demographics od_spec
    ON sp_spec."demographicID" = od_spec."demographicID"
LEFT JOIN view_effective_observations veo_spec
    ON od_spec."observationID" = veo_spec."observationID";
