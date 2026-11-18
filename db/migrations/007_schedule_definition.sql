CREATE TABLE rpt.schedules (
    report_id uuid PRIMARY KEY REFERENCES rpt.reports,
    version integer NOT NULL,
    period jsonb NOT NULL,
    enabled boolean NOT NULL,
    revision integer NOT NULL CHECK (revision > 0),
    FOREIGN KEY (report_id, version) REFERENCES rpt.report_versions
);

ALTER TABLE rpt.runs ADD COLUMN schedule_revision integer;
ALTER TABLE rpt.runs ADD CHECK (schedule_revision IS NULL OR (schedule_revision > 0 AND trigger_kind = 'automatic'));
