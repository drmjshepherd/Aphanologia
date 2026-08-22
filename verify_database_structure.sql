SELECT 
    'samples' AS table_name, 
    COUNT(*) AS total_rows, 
    COUNT(geom_bng) AS bng_geoms_built, 
    COUNT(geom_wgs84) AS wgs_geoms_built 
FROM samples
UNION ALL
SELECT 'observations', COUNT(*), NULL, NULL FROM observations
UNION ALL
SELECT 'observation_demographics', COUNT(*), NULL, NULL FROM observation_demographics
UNION ALL
SELECT 'taxonomy', COUNT(*), NULL, NULL FROM taxonomy
UNION ALL
SELECT 'literature', COUNT(*), NULL, NULL FROM literature;
