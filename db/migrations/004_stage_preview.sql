ALTER TABLE rpt.runs ADD COLUMN stop_after text CHECK (stop_after = 'gather');
ALTER TABLE rpt.runs ADD CHECK (stop_after IS NULL OR (mode = 'preview' AND preview_section_id IS NOT NULL));
