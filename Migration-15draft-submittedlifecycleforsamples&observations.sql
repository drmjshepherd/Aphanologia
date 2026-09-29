-- ============================================================
-- Migration 15: draft / submitted lifecycle for samples and observations
--
-- Purpose: adds a "record_status" column (draft | submitted) to samples
-- and observations, so contributors can build records privately as
-- drafts and then submit them. This is separate from the existing
-- observations.verification_status, which keeps recording the
-- superuser REVIEW outcome (unverified / pending / verified / queried /
-- rejected, plus the new 'unverifiable').
--
-- Every existing row becomes 'submitted' (the column default), so all
-- 25,000-odd legacy records and the 17 pending ones stay exactly as
-- they are. Only rows created by the new submit code start as 'draft'.
--
-- Also adds qc_flags on samples (warnings from the automated sample
-- checks) and submitted_at timestamps.
-- ============================================================

BEGIN;

ALTER TABLE samples
    ADD COLUMN IF NOT EXISTS record_status text NOT NULL DEFAULT 'submitted',
    ADD COLUMN IF NOT EXISTS submitted_at timestamp with time zone,
    ADD COLUMN IF NOT EXISTS qc_flags jsonb;

ALTER TABLE observations
    ADD COLUMN IF NOT EXISTS record_status text NOT NULL DEFAULT 'submitted',
    ADD COLUMN IF NOT EXISTS submitted_at timestamp with time zone;

ALTER TABLE samples
    ADD CONSTRAINT samples_record_status_chk CHECK (record_status IN ('draft', 'submitted'));
ALTER TABLE observations
    ADD CONSTRAINT observations_record_status_chk CHECK (record_status IN ('draft', 'submitted'));

-- Existing rows count as submitted at the time they were entered
UPDATE samples SET submitted_at = entered_at WHERE submitted_at IS NULL;
UPDATE observations SET submitted_at = entered_at WHERE submitted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_samples_owner_status ON samples (submitted_by_user_id, record_status);
CREATE INDEX IF NOT EXISTS idx_observations_owner_status ON observations (submitted_by_user_id, record_status);
CREATE INDEX IF NOT EXISTS idx_observations_event ON observations ("eventID");

COMMIT;

-- Sanity check afterwards - expect everything 'submitted':
-- SELECT record_status, COUNT(*) FROM samples GROUP BY 1;
-- SELECT record_status, verification_status, COUNT(*) FROM observations GROUP BY 1, 2;
