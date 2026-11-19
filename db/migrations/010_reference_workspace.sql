ALTER TABLE rpt.report_versions ADD COLUMN note text CHECK (char_length(note) <= 500);
ALTER TABLE rpt.chat_turns ADD COLUMN rejected boolean NOT NULL DEFAULT false;
