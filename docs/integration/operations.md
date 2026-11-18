# Local and hosted operations

## Local fixture

Run ./scripts/dev to load a disposable PostgreSQL cluster and start the API and worker. Open /console at the loopback URL printed by the command. Use Ctrl-C to tear down the fixture. AEGIS_DEV_PORT overrides port 8000. Run ./scripts/dev --demo for the HTTP walkthrough. The console uses local assets and the local API.

## Deployment

Use separate migration, report runtime and read-only source credentials. Apply migrations before deploying processes that need the new tables. The migration registry verifies checksums.

```sh
uv run python -m aegis_report.migrate
uv run uvicorn aegis_report.api:app
uv run python -m aegis_report.worker
```

Run the migration command with RPT_MIGRATION_DATABASE_URL. Run the services with the report runtime and read-only source DSNs. In hosted mode set AUTH_PROVIDER=upstream and AUTH_VALIDATION_URL. Use the approved HTTPS INTERNAL_LLM_URL, CHAT_MODEL and compatible EMBEDDING_MODEL. The gateway accepts an injected per-call credential provider or INTERNAL_LLM_API_KEY through configuration. Keep OWNER_KEY_SECRET stable across API and worker. An authorized active-owner checker is required before hosted report generation. Readiness and retention settings apply through the existing environment variables. [Runtime configuration](../../README.md#runtime-configuration)

## Observe

Track queue age, expired leases, turn budgets, source probe failures, stability delays, model latency and costs, and terminal run codes. Log aggregate counts and durations. Keep prompts, request headers, tokens and raw source text out of logs. Check /health for the API process and run a synthetic job through terminal state to exercise the worker. Calendar dispatch and correction handling belong to G6. Load tests and deployment hardening belong to G7.
