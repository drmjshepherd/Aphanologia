-- Migration 10: Add sequences for web-submitted demographic and
-- specimen records.
--
-- WHY THIS IS NEEDED:
-- The schema viewer confirmed neither "demographicID" (in
-- observation_demographics) nor "specimenID" (in specimens) has a
-- column_default - meaning nothing currently auto-generates an ID for
-- a new row in either table. eventID and observationID already have
-- this solved via web_eventid_seq / web_observationid_seq, each
-- producing a WEB-prefixed value that can never collide with the
-- ~25,000 imported historic records. This migration creates the same
-- kind of sequence for these two newer tables, following the exact
-- same pattern.
--
-- This does NOT touch any existing data - it only adds two new,
-- previously-nonexistent sequences.

CREATE SEQUENCE IF NOT EXISTS web_demographicid_seq START WITH 1;
CREATE SEQUENCE IF NOT EXISTS web_specimenid_seq START WITH 1;

-- Verify both now exist:
SELECT sequence_name, start_value
FROM information_schema.sequences
WHERE sequence_name IN ('web_demographicid_seq', 'web_specimenid_seq');
