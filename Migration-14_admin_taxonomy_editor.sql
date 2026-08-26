-- Migration-14: admin_taxonomy_editor
-- Adds the infrastructure needed for the new superuser taxonomy
-- editor: a permanent audit log for admin edits (mirroring the
-- pattern already used by observation_verification_actions), and a
-- WEB-prefixed sequence for taxonIDs created through the editor, so
-- new taxa can never collide with legacy numeric taxonIDs (e.g. 244)
-- imported from the original spreadsheet data.

BEGIN;

-- ==========================================================
-- 1. Sequence for new taxonIDs created via the web editor
-- ==========================================================
-- Follows the same "WEB-<n>" convention already used for
-- web_eventid_seq, web_litid_seq, web_observationid_seq and
-- web_demographicid_seq/web_specimenid_seq.
CREATE SEQUENCE IF NOT EXISTS web_taxonid_seq START WITH 1;

-- ==========================================================
-- 2. Generic admin activity log
-- ==========================================================
-- Append-only, like observation_verification_actions - a row is
-- never updated or deleted once written. Deliberately generic
-- (table_name + record_id, rather than a taxonomy-specific table)
-- so the same log can be reused later when superuser editing is
-- extended to other tables, without a further migration.
CREATE TABLE IF NOT EXISTS admin_activity_log (
    log_id                  integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    performed_by_user_id    integer NOT NULL REFERENCES users(user_id),
    action_type             text NOT NULL,   -- e.g. 'taxonomy_edit', 'taxonomy_create'
    table_name              text NOT NULL,   -- e.g. 'taxonomy'
    record_id               text NOT NULL,   -- e.g. the taxonID affected
    field_changes           jsonb,           -- {"fieldName": {"old": ..., "new": ...}, ...}
    notes                   text,            -- optional free-text reason, entered by the superuser
    performed_at            timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Fast "show me everything that's ever happened to this record"
-- lookups - this is what powers the edit-history panel on the
-- taxonomy editor page.
CREATE INDEX IF NOT EXISTS idx_admin_activity_log_record
    ON admin_activity_log (table_name, record_id);

CREATE INDEX IF NOT EXISTS idx_admin_activity_log_user
    ON admin_activity_log (performed_by_user_id);

CREATE INDEX IF NOT EXISTS idx_admin_activity_log_performed_at
    ON admin_activity_log (performed_at DESC);

COMMIT;

-- Rollback (manual, if ever needed):
-- DROP TABLE IF EXISTS admin_activity_log;
-- DROP SEQUENCE IF EXISTS web_taxonid_seq;
