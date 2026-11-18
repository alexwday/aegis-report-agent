ALTER TABLE rpt.reports ADD COLUMN title text;
UPDATE rpt.reports r SET title = v.spec->>'title'
FROM rpt.report_versions v WHERE v.report_id = r.id AND v.version = r.head;
ALTER TABLE rpt.reports ALTER COLUMN title SET NOT NULL;
CREATE INDEX report_owner_catalog ON rpt.reports (owner_key, archived_at, created_at DESC);

ALTER TABLE rpt.drafts ADD COLUMN head_at_start integer;
UPDATE rpt.drafts SET head_at_start = base_version WHERE report_id IS NOT NULL;
ALTER TABLE rpt.drafts ADD CHECK ((report_id IS NULL) = (head_at_start IS NULL));
