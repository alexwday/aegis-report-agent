# Local and hosted operations

## Local fixture

Run `./scripts/dev` to load a disposable PostgreSQL cluster and start the API and worker. Open `/` at the loopback URL printed by the command. Developer tools remain at `/console`. Use Ctrl-C to tear down the fixture. AEGIS_DEV_PORT overrides port 8000. Run ./scripts/dev --demo for the HTTP walkthrough. The console uses local assets and the local API.

## Deployment

Use separate migration, report runtime and read-only source credentials. Apply migrations before deploying processes that need the new tables. The migration registry verifies checksums.

```sh
uv run python -m aegis_report.migrate
uv run uvicorn aegis_report.api:app
uv run python -m aegis_report.worker
```

Run the migration command with RPT_MIGRATION_DATABASE_URL. Run the services with the report runtime and read-only source DSNs. In hosted mode set AUTH_PROVIDER=upstream and AUTH_VALIDATION_URL. Use the approved HTTPS INTERNAL_LLM_URL, CHAT_MODEL and compatible EMBEDDING_MODEL. The gateway accepts an injected per-call credential provider or INTERNAL_LLM_API_KEY through configuration. Keep OWNER_KEY_SECRET stable across API and worker. An authorized active-owner checker is required before hosted report generation. Readiness and retention settings apply through the existing environment variables. [Runtime configuration](../../README.md#runtime-configuration)

## Observe

Track queue age, poll lag, queue depth, expired leases, turn budgets, source probe failures, time to stable inputs by source, supersession totals, model latency and costs, and terminal run codes. Log aggregate counts and durations. Keep prompts, request headers, tokens and raw source text out of logs. Check /health for the API process and run a synthetic job through terminal state to exercise the worker. Run uv run --no-sync python scripts/schedule_metrics.py with an authorized report metrics DSN for aggregate poll lag, queue depth, mean marker stabilization time by source, supersessions and failures by code. Load tests and deployment hardening belong to G8.


## Automatic scheduling

The worker starts a separate schedule polling loop. SCHEDULE_POLL_SECONDS defaults to 60. The policy starts at the saved version and requested fiscal quarter. Each complete publication advances next_period once. Tentative outputs retain the current target until it is complete. The core Canadian fiscal calendar uses the configured IANA timezone and the end of the vendor quarter. The floor is a quarter-end date for the verified Big Six calendar, with physical evidence still required after it. Earnings release may occur later. Other and mixed scopes use physical readiness without a date-based floor. The quiet interval starts when the target source marker is first observed and needs a second unchanged read.

Complete required inputs are the default. Set provisional_after_hours to opt in after a wait from the later of the first check and the calendar floor, or from the first check on physical-only schedules. A provisional run needs at least one stable scope. Its JSON, HTML and PDF identify it as provisional. A stable complete generation supersedes it. Correction_days defaults to 14 days from the first complete publication. A replacement inside this window keeps the original deadline. A known update observed within the window can finish its quiet interval during a small bounded grace period. Same-count benchmark corrections are detected from scoped values. Document and transcript corrections depend on the available source markers.

Pause and archive fence queued and in-flight publication. The active-owner checker runs before probing, during the start of generation, and again before publication. The approved production implementation remains a sign-off item. Recoverable generation failures back off with jitter and stop at the existing attempt cap. The notification interface uses a no-op implementation.

## Read-only schedule checks

Run scripts/eval_schedule.py with an approved SOURCE_DATABASE_URL and one of the documented report or template forms. It uses the worker's source probe path without schedule writes. A first probe can report physical readiness. The publication quiet gate needs a later observation. [Evaluator commands](../collab/status/S-007.md)
