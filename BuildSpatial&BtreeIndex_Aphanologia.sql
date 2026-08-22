-- 1. Build GiST Spatial Indexes for PostGIS
CREATE INDEX IF NOT EXISTS idx_samples_geom_bng ON samples USING gist (geom_bng);
CREATE INDEX IF NOT EXISTS idx_samples_geom_wgs84 ON samples USING gist (geom_wgs84);

-- 2. Build B-tree Indexes on Foreign Keys for fast JOIN performance
CREATE INDEX IF NOT EXISTS idx_obs_eventid ON observations ("eventID");
CREATE INDEX IF NOT EXISTS idx_obs_taxonid ON observations ("taxonID");
CREATE INDEX IF NOT EXISTS idx_demo_obsid ON observation_demographics ("observationID");
CREATE INDEX IF NOT EXISTS idx_spec_demoid ON specimens ("demographicID");
