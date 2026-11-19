ALTER TABLE rpt.schedules
    ADD COLUMN dispatch_period jsonb,
    ADD COLUMN timezone text NOT NULL DEFAULT 'America/Toronto',
    ADD COLUMN quiet_seconds double precision CHECK (quiet_seconds BETWEEN 0 AND 86400),
    ADD COLUMN correction_days integer NOT NULL DEFAULT 14 CHECK (correction_days BETWEEN 0 AND 90),
    ADD COLUMN provisional_after_hours double precision CHECK (provisional_after_hours BETWEEN 0 AND 2160),
    ADD COLUMN next_poll_at timestamptz NOT NULL DEFAULT now();

CREATE INDEX schedules_due ON rpt.schedules (next_poll_at, report_id) WHERE enabled;

ALTER TABLE rpt.runs
    ADD COLUMN schedule_generation integer CHECK (schedule_generation > 0),
    ADD COLUMN evidence_key text,
    ADD COLUMN evidence_snapshot jsonb,
    ADD COLUMN publication_kind text CHECK (publication_kind IN ('complete', 'provisional')),
    ADD COLUMN publication_state text CHECK (publication_state IN ('published', 'provisional', 'superseded')),
    ADD CHECK (
        (schedule_generation IS NULL AND evidence_key IS NULL AND evidence_snapshot IS NULL AND publication_kind IS NULL)
        OR (schedule_generation IS NOT NULL AND evidence_key IS NOT NULL AND evidence_snapshot IS NOT NULL
            AND publication_kind IS NOT NULL AND schedule_revision IS NOT NULL)
    );

CREATE UNIQUE INDEX schedule_unique_evidence ON rpt.runs (report_id, version, period, evidence_key)
    WHERE schedule_generation IS NOT NULL;
CREATE UNIQUE INDEX schedule_unique_current ON rpt.runs (report_id, period)
    WHERE publication_state IN ('published', 'provisional');

CREATE TABLE rpt.schedule_periods (
    report_id uuid NOT NULL REFERENCES rpt.schedules (report_id),
    period jsonb NOT NULL,
    version integer NOT NULL,
    policy_revision integer NOT NULL,
    generation integer NOT NULL DEFAULT 0 CHECK (generation >= 0),
    status text NOT NULL DEFAULT 'waiting_for_data'
        CHECK (status IN ('waiting_for_data', 'ready_to_run', 'published', 'provisional', 'failed')),
    reason text,
    first_checked_at timestamptz NOT NULL,
    checked_at timestamptz NOT NULL,
    next_check_at timestamptz,
    readiness jsonb NOT NULL DEFAULT '{}'::jsonb,
    latest_run_id uuid REFERENCES rpt.runs,
    current_run_id uuid REFERENCES rpt.runs,
    current_version integer,
    current_kind text CHECK (current_kind IN ('complete', 'provisional')),
    current_evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
    published_at timestamptz,
    correction_until timestamptz,
    last_correction jsonb NOT NULL DEFAULT '[]'::jsonb,
    PRIMARY KEY (report_id, period),
    FOREIGN KEY (report_id, version) REFERENCES rpt.report_versions,
    FOREIGN KEY (report_id, current_version) REFERENCES rpt.report_versions,
    CHECK ((current_run_id IS NULL) = (current_kind IS NULL)),
    CHECK ((current_run_id IS NULL) = (current_version IS NULL))
);

CREATE INDEX schedule_period_corrections ON rpt.schedule_periods (report_id, correction_until)
    WHERE current_run_id IS NOT NULL;
