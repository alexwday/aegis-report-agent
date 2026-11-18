-- G0 design draft. The G1 migration will follow the review.
CREATE SCHEMA rpt;

CREATE TABLE rpt.users (
    id uuid PRIMARY KEY,
    auth_subject_key bytea NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE rpt.reports (
    id uuid PRIMARY KEY,
    owner_id uuid NOT NULL REFERENCES rpt.users,
    created_at timestamptz NOT NULL DEFAULT now(),
    archived_at timestamptz
);

CREATE TABLE rpt.report_versions (
    report_id uuid NOT NULL REFERENCES rpt.reports,
    version integer NOT NULL CHECK (version > 0),
    created_by uuid NOT NULL REFERENCES rpt.users,
    title text NOT NULL,
    spec_version integer NOT NULL,
    settings jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (report_id, version)
);

CREATE TABLE rpt.section_versions (
    report_id uuid NOT NULL,
    report_version integer NOT NULL,
    section_id uuid NOT NULL,
    position integer NOT NULL CHECK (position >= 0),
    title text NOT NULL,
    pipeline jsonb NOT NULL,
    PRIMARY KEY (report_id, report_version, section_id),
    UNIQUE (report_id, report_version, position),
    FOREIGN KEY (report_id, report_version) REFERENCES rpt.report_versions
);

CREATE TABLE rpt.templates (
    id uuid PRIMARY KEY,
    owner_id uuid REFERENCES rpt.users,
    created_at timestamptz NOT NULL DEFAULT now(),
    archived_at timestamptz
);

CREATE TABLE rpt.template_versions (
    template_id uuid NOT NULL REFERENCES rpt.templates,
    version integer NOT NULL CHECK (version > 0),
    spec_version integer NOT NULL,
    name text NOT NULL,
    spec jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (template_id, version)
);

CREATE TABLE rpt.conversations (
    id uuid PRIMARY KEY,
    owner_id uuid NOT NULL REFERENCES rpt.users,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL
);

CREATE TABLE rpt.drafts (
    id uuid PRIMARY KEY,
    owner_id uuid NOT NULL REFERENCES rpt.users,
    report_id uuid REFERENCES rpt.reports,
    base_version integer,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    spec_version integer NOT NULL,
    spec jsonb NOT NULL,
    expires_at timestamptz NOT NULL,
    CHECK ((report_id IS NULL) = (base_version IS NULL)),
    FOREIGN KEY (report_id, base_version) REFERENCES rpt.report_versions
);

CREATE TABLE rpt.turns (
    id uuid PRIMARY KEY,
    conversation_id uuid NOT NULL REFERENCES rpt.conversations,
    draft_id uuid REFERENCES rpt.drafts ON DELETE SET NULL,
    request_key text NOT NULL,
    status text NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled')),
    input jsonb NOT NULL,
    attempt integer NOT NULL DEFAULT 0,
    lease_until timestamptz,
    lease_epoch bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (conversation_id, request_key)
);

CREATE TABLE rpt.turn_events (
    turn_id uuid NOT NULL REFERENCES rpt.turns ON DELETE CASCADE,
    seq bigint NOT NULL CHECK (seq > 0),
    type text NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (turn_id, seq)
);

CREATE TABLE rpt.schedules (
    id uuid PRIMARY KEY,
    report_id uuid NOT NULL REFERENCES rpt.reports,
    version integer NOT NULL,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    enabled boolean NOT NULL DEFAULT false,
    calendar_policy jsonb NOT NULL,
    readiness_policy jsonb NOT NULL,
    next_check_at timestamptz NOT NULL,
    FOREIGN KEY (report_id, version) REFERENCES rpt.report_versions,
    UNIQUE (id, report_id)
);

CREATE UNIQUE INDEX one_active_schedule_per_report ON rpt.schedules (report_id) WHERE enabled;

CREATE TABLE rpt.runs (
    id uuid PRIMARY KEY,
    requested_by uuid NOT NULL REFERENCES rpt.users,
    mode text NOT NULL CHECK (mode IN ('preview', 'manual', 'scheduled')),
    status text NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled', 'superseded')),
    report_id uuid REFERENCES rpt.reports,
    report_version integer,
    schedule_id uuid,
    spec_snapshot jsonb NOT NULL,
    resolved_scope jsonb NOT NULL,
    source_manifest jsonb NOT NULL,
    source_fingerprint text NOT NULL,
    engine_version text NOT NULL,
    generation_key text UNIQUE,
    attempt integer NOT NULL DEFAULT 0,
    lease_until timestamptz,
    lease_epoch bigint NOT NULL DEFAULT 0,
    available_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (report_id, report_version) REFERENCES rpt.report_versions,
    FOREIGN KEY (schedule_id, report_id) REFERENCES rpt.schedules (id, report_id),
    CHECK ((report_id IS NULL) = (report_version IS NULL)),
    CHECK ((mode = 'scheduled') = (schedule_id IS NOT NULL)),
    CHECK (mode <> 'scheduled' OR (report_id IS NOT NULL AND generation_key IS NOT NULL)),
    CHECK ((mode = 'preview') = (expires_at IS NOT NULL))
);

CREATE INDEX runnable_runs ON rpt.runs (available_at) WHERE status = 'queued';

CREATE TABLE rpt.schedule_periods (
    schedule_id uuid NOT NULL REFERENCES rpt.schedules,
    fiscal_year integer NOT NULL,
    fiscal_quarter integer NOT NULL CHECK (fiscal_quarter BETWEEN 1 AND 4),
    readiness jsonb NOT NULL,
    latest_fingerprint text,
    probe_lease_until timestamptz,
    probe_epoch bigint NOT NULL DEFAULT 0,
    current_run_id uuid REFERENCES rpt.runs,
    PRIMARY KEY (schedule_id, fiscal_year, fiscal_quarter)
);

CREATE TABLE rpt.previews (
    run_id uuid PRIMARY KEY REFERENCES rpt.runs ON DELETE CASCADE,
    draft_id uuid REFERENCES rpt.drafts ON DELETE SET NULL,
    draft_revision bigint NOT NULL,
    scope jsonb NOT NULL,
    baseline_run_id uuid REFERENCES rpt.runs ON DELETE SET NULL
);

CREATE TABLE rpt.run_outputs (
    run_id uuid NOT NULL REFERENCES rpt.runs ON DELETE CASCADE,
    output_key text NOT NULL,
    media_type text NOT NULL,
    blocks jsonb,
    body bytea,
    PRIMARY KEY (run_id, output_key),
    CHECK ((blocks IS NULL) <> (body IS NULL))
);

CREATE TABLE rpt.evidence (
    run_id uuid NOT NULL REFERENCES rpt.runs ON DELETE CASCADE,
    evidence_id text NOT NULL,
    source text NOT NULL,
    bank_scope text NOT NULL,
    fiscal_year integer NOT NULL,
    fiscal_quarter integer NOT NULL CHECK (fiscal_quarter BETWEEN 1 AND 4),
    doc_ref text NOT NULL,
    content_hash text NOT NULL,
    anchor jsonb NOT NULL,
    validation_snapshot jsonb,
    PRIMARY KEY (run_id, evidence_id)
);

CREATE TABLE rpt.output_citations (
    run_id uuid NOT NULL,
    output_key text NOT NULL,
    block_key text NOT NULL,
    evidence_id text NOT NULL,
    PRIMARY KEY (run_id, output_key, block_key, evidence_id),
    FOREIGN KEY (run_id, output_key) REFERENCES rpt.run_outputs ON DELETE CASCADE,
    FOREIGN KEY (run_id, evidence_id) REFERENCES rpt.evidence ON DELETE CASCADE
);

CREATE TABLE rpt.idempotent_requests (
    actor_id uuid NOT NULL REFERENCES rpt.users,
    operation text NOT NULL,
    request_key text NOT NULL,
    payload_digest text NOT NULL,
    response jsonb NOT NULL,
    expires_at timestamptz NOT NULL,
    PRIMARY KEY (actor_id, operation, request_key)
);

CREATE TABLE rpt.audit (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor_id uuid REFERENCES rpt.users,
    action text NOT NULL,
    resource_id uuid,
    result_code text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
