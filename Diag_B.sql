SELECT
    "taxonomicStatus",
    ("scientificnameAuthorship" ILIKE '%sensu%') AS has_sensu,
    COUNT(*) AS n_rows
FROM taxonomy
WHERE "taxonomicStatus" = 'misapplied'
GROUP BY "taxonomicStatus", has_sensu;
