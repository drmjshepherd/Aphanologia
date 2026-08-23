UPDATE observation_media
SET caption = regexp_replace(
    file_url,
    '^.*[\\/]([^\\/]+)\.[^.]+$',
    '\1'
)
WHERE caption IS NOT NULL;
