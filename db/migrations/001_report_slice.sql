CREATE SCHEMA IF NOT EXISTS rpt;

CREATE TABLE rpt.reports (
    id uuid PRIMARY KEY,
    owner_key bytea NOT NULL,
    head integer NOT NULL CHECK (head > 0),
    archived_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE rpt.report_versions (
    report_id uuid NOT NULL REFERENCES rpt.reports,
    version integer NOT NULL CHECK (version > 0),
    spec jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (report_id, version)
);

CREATE TABLE rpt.drafts (
    id uuid PRIMARY KEY,
    owner_key bytea NOT NULL,
    report_id uuid,
    base_version integer,
    revision integer NOT NULL CHECK (revision > 0),
    spec jsonb NOT NULL,
    CHECK ((report_id IS NULL) = (base_version IS NULL)),
    FOREIGN KEY (report_id, base_version) REFERENCES rpt.report_versions
);

CREATE TABLE rpt.runs (
    id uuid PRIMARY KEY,
    owner_key bytea NOT NULL,
    mode text NOT NULL CHECK (mode IN ('generate', 'preview')),
    report_id uuid,
    version integer,
    draft_revision integer,
    preview_section_id text,
    baseline_id uuid REFERENCES rpt.runs,
    period jsonb NOT NULL,
    spec jsonb NOT NULL,
    idempotency_key varchar(128),
    readiness jsonb NOT NULL DEFAULT '{}'::jsonb,
    state text NOT NULL DEFAULT 'queued' CHECK (state IN ('queued', 'waiting', 'succeeded', 'failed')),
    next_probe_at timestamptz NOT NULL DEFAULT now(),
    result jsonb,
    error_code text,
    expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((mode = 'generate') = (report_id IS NOT NULL AND version IS NOT NULL)),
    CHECK ((mode = 'preview') = (expires_at IS NOT NULL AND draft_revision IS NOT NULL)),
    FOREIGN KEY (report_id, version) REFERENCES rpt.report_versions,
    UNIQUE (owner_key, idempotency_key)
);

CREATE INDEX runnable_reports ON rpt.runs (next_probe_at) WHERE state IN ('queued', 'waiting');
