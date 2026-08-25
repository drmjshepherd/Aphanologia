-- Migration 12: Verification actions table.
--
-- WHY THIS IS NEEDED:
-- observations already has verification_status/verified_by/
-- verified_date/verification_notes, but these are a single snapshot -
-- each new review action overwrites the last, so there's no record of
-- HOW a record reached its current state, who was involved along the
-- way, or why an earlier decision was changed. Given the emphasis on
-- being able to show your reasoning for taxonomic and verification
-- decisions transparently (to the recording community, to Chris
-- Raper/NBN, to anyone questioning a call later), this needs to be a
-- proper append-only log: one row per review action, never
-- overwritten or deleted.
--
-- This also directly supports the planned contributor notification
-- bell (a contributor should be told when one of their records is
-- reviewed) via the viewed_by_contributor flag - not built yet, but
-- the data this needs already exists here rather than being bolted
-- on awkwardly later.

CREATE TABLE IF NOT EXISTS observation_verification_actions (
    action_id SERIAL PRIMARY KEY,
    "observationID" text NOT NULL REFERENCES observations("observationID"),
    action_type text NOT NULL CHECK (action_type IN ('accepted', 'rejected', 'reassigned', 'queried')),
    reassigned_taxon_id text REFERENCES taxonomy("taxonID"),
    notes text,
    performed_by_user_id integer NOT NULL REFERENCES users(user_id),
    performed_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    viewed_by_contributor boolean NOT NULL DEFAULT false,

    -- A "reassigned" action without saying what it was reassigned TO
    -- would be a silent, unusable record - enforce that it always
    -- carries a target taxon.
    CONSTRAINT reassignment_needs_target CHECK (
        (action_type = 'reassigned' AND reassigned_taxon_id IS NOT NULL)
        OR (action_type != 'reassigned')
    )
);

-- Fast lookup of an observation's full review history
CREATE INDEX IF NOT EXISTS idx_verification_actions_observation
    ON observation_verification_actions ("observationID");

-- Fast lookup of "does this contributor have anything unseen?" - the
-- query the notification bell will eventually run on every page load,
-- so worth indexing now even though the bell itself isn't built yet
CREATE INDEX IF NOT EXISTS idx_verification_actions_unviewed
    ON observation_verification_actions (viewed_by_contributor)
    WHERE viewed_by_contributor = false;

-- Verify:
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'observation_verification_actions'
ORDER BY ordinal_position;
