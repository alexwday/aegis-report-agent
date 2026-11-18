-- For a disposable fixture cluster only. A deployed environment provisions credentials separately.
CREATE ROLE source_reader LOGIN;
CREATE ROLE rpt_runtime LOGIN;

ALTER ROLE source_reader SET default_transaction_read_only = on;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO source_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO source_reader;

REVOKE ALL ON SCHEMA rpt FROM PUBLIC;
GRANT USAGE ON SCHEMA rpt TO rpt_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA rpt TO rpt_runtime;
REVOKE ALL ON rpt.schema_migrations FROM rpt_runtime;
