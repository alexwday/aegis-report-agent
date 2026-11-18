CREATE TABLE rpt.conversations (
    id uuid PRIMARY KEY,
    owner_key bytea NOT NULL,
    draft_id uuid NOT NULL REFERENCES rpt.drafts,
    period jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE rpt.chat_turns (
    id uuid PRIMARY KEY,
    conversation_id uuid NOT NULL REFERENCES rpt.conversations,
    request_key varchar(128) NOT NULL,
    user_message varchar(2000) NOT NULL,
    state text NOT NULL DEFAULT 'queued' CHECK (state IN ('queued','running','succeeded','failed','cancelled')),
    message text,
    proposal jsonb,
    preview_id uuid REFERENCES rpt.runs ON DELETE SET NULL,
    applied_revision integer,
    error_code text,
    last_sequence integer NOT NULL DEFAULT 0,
    lease_until timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (conversation_id, request_key),
    CHECK ((state = 'running') = (lease_until IS NOT NULL))
);

CREATE UNIQUE INDEX one_active_chat_turn ON rpt.chat_turns (conversation_id)
    WHERE state IN ('queued', 'running');
CREATE INDEX runnable_chat_turns ON rpt.chat_turns (created_at) WHERE state = 'queued';
CREATE INDEX expiring_chat_turns ON rpt.chat_turns (lease_until) WHERE state = 'running';

CREATE TABLE rpt.chat_events (
    turn_id uuid NOT NULL REFERENCES rpt.chat_turns ON DELETE CASCADE,
    sequence integer NOT NULL,
    kind text NOT NULL,
    data jsonb NOT NULL,
    PRIMARY KEY (turn_id, sequence)
);
