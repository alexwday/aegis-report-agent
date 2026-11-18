CREATE TABLE rpt.personal_templates (
    id uuid PRIMARY KEY,
    owner_key bytea NOT NULL,
    title text NOT NULL,
    spec jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX template_owner_catalog ON rpt.personal_templates (owner_key, created_at DESC);
