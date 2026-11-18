ALTER TABLE rpt.runs
    ADD COLUMN trigger_kind text NOT NULL DEFAULT 'manual'
        CHECK (trigger_kind IN ('manual', 'automatic')),
    ADD COLUMN lease_token uuid,
    ADD COLUMN lease_until timestamptz,
    DROP CONSTRAINT runs_state_check,
    ADD CHECK (state IN ('queued', 'waiting', 'running', 'succeeded', 'failed')),
    ADD CHECK ((state = 'running') = (lease_token IS NOT NULL AND lease_until IS NOT NULL)),
    ADD CHECK (mode <> 'preview' OR trigger_kind = 'manual');

CREATE INDEX recoverable_report_runs ON rpt.runs (lease_until) WHERE state = 'running';

CREATE TABLE rpt.source_observations (
    scope_key text PRIMARY KEY,
    observed_at timestamptz NOT NULL,
    observation jsonb NOT NULL
);
