# Aegis Report Agent

A standalone quarterly report builder. Gate G1 demonstrates an owner creating a draft from a template, previewing a change against a saved version, and generating cited HTML and JSON from the next fiscal quarter.

## Try the G1 slice

Install `uv` and PostgreSQL server tools with pgvector 0.8.x. Run as an ordinary local user. `pg_config --bindir` must point to the PostgreSQL installation with pgvector.

```sh
./scripts/dev --demo
```

The command starts an isolated socket-only Postgres cluster, seeds fabricated rows, applies the `rpt` migration, and starts the FastAPI API and a worker with the stub model. It runs the scripted demo over HTTP and removes the cluster on exit. Run `./scripts/dev` to keep the fixture stack available until Ctrl-C. The default API listens on loopback port 8000 and exposes FastAPI docs at `/docs`. Set `AEGIS_DEV_PORT` to use another port. The fixture defaults to a one-second quiet period to make the demo quick.

```sh
./db/seed/check-local.sh
./scripts/test -q --disable-warnings
uv run --no-sync python scripts/openapi.py --check
```

## Runtime configuration

`ENVIRONMENT=local` explicitly enables the fixed `LOCAL_AUTH_USER_ID` and permits the deterministic model stub. The fixture scripts set both. Outside local mode, set `AUTH_PROVIDER=upstream`, `AUTH_VALIDATION_URL`, `INTERNAL_LLM_URL`, and `CHAT_MODEL`. The upstream HTTPS endpoints and credentials come from deployment configuration. The model gateway accepts a per-call credential provider. The default wrapper reads `INTERNAL_LLM_API_KEY` if supplied. `EMBEDDING_MODEL` defaults to `text-embedding-3-large`.

Use separate `SOURCE_DATABASE_URL` (SELECT-only) and `RPT_DATABASE_URL` (runtime access to `rpt`). Apply migrations with a separate `RPT_MIGRATION_DATABASE_URL` and `uv run python -m aegis_report.migrate`. Set a stable `OWNER_KEY_SECRET` with at least 32 bytes to derive private ownership keys. Worker timing uses `QUIET_SECONDS` (default 1800) and `WORKER_POLL_SECONDS` (default 1). `PREVIEW_RETENTION_DAYS` sets preview access expiry. `CURRENCY_MAP` accepts an object from canonical instrument symbols or country suffixes to currency codes. The default is `{"CA":"CAD","US":"USD"}`, displayed as unconfirmed. The production worker requires an injected owner-status checker before it will generate saved reports. The local fixture supplies a deterministic checker.

The [generated API contract](api/openapi.json), [architecture plan](docs/collab/plans/PLAN.md), and [design](DESIGN.md) describe the boundary between this slice and later gates.

## Briefing pack and reviews

The [page index](docs/sources/01_index.md) links the 16 source pages. The [v1.1 corrections](docs/sources/PACK_v1.1_corrections.md) supplement the original transcription. The photos and unredacted transcripts stay local. Public briefing pages 10, 11, 13, and 16 and R-001 page 4 visibly mark public-hygiene redactions.

Use the [collaboration protocol](docs/collab/README.md), [tracker](docs/collab/TRACKER.md), [question log](docs/collab/QUESTIONS.md), [assumptions](docs/collab/ASSUMPTIONS.md), and [decisions](docs/collab/DECISIONS.md). Gate G1 awaits R-002. [S-002](docs/collab/status/S-002.md) records the evidence and open questions.
