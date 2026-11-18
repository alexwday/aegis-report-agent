# Aegis Report Agent

A standalone quarterly report builder. The G2 slice supports template-based drafts, multi-year KPI trends, multi-source earnings themes, cited HTML and JSON, and previews with row, cell and claim diffs.

## Try the G2 slice

Install `uv` and PostgreSQL server tools with pgvector 0.8.x. Run as an ordinary local user. `pg_config --bindir` must point to the PostgreSQL installation with pgvector.

```sh
./scripts/dev --demo
```

The command starts an isolated socket-only Postgres cluster, seeds fabricated rows, applies the migrations, and starts FastAPI and a worker with the stub model. The demo uses the application default quiet period of 1,800 seconds. It previews against current data immediately, saves a version, and uses an injected clock to run that version via the internal automatic entry point for the next fiscal quarter. This exercises the automatic worker path ahead of G6 schedule discovery and publication. The fixture cluster is removed on exit.

Run `./scripts/dev` to keep the fixture stack available until Ctrl-C. The API listens on loopback port 8000 by default, with FastAPI docs at `/docs`. Set `AEGIS_DEV_PORT` to use another port.

```sh
./db/seed/check-local.sh
./scripts/test -q --disable-warnings
uv run --no-sync python scripts/openapi.py --check
```

## Runtime configuration

`ENVIRONMENT=local` explicitly enables the fixed `LOCAL_AUTH_USER_ID` and permits the deterministic model stub. The fixture scripts set both. Outside local mode, set `AUTH_PROVIDER=upstream`, `AUTH_VALIDATION_URL`, `INTERNAL_LLM_URL`, and `CHAT_MODEL`. The upstream HTTPS endpoints and credentials come from deployment configuration. The model gateway accepts a per-call credential provider. The default wrapper reads `INTERNAL_LLM_API_KEY` if supplied. `EMBEDDING_MODEL` defaults to `text-embedding-3-large`.

Use separate `SOURCE_DATABASE_URL` (SELECT-only) and `RPT_DATABASE_URL` (runtime access to `rpt`). Apply migrations with a separate `RPT_MIGRATION_DATABASE_URL` and `uv run python -m aegis_report.migrate`. Set a stable `OWNER_KEY_SECRET` with at least 32 bytes to derive private ownership keys. A hosted worker requires an injected owner-status checker before generating saved reports.

`QUIET_SECONDS` (default 1800) gates automatic generation. Manual runs and previews immediately return current evidence with per-scope readiness and `data_stability`. `WORKER_POLL_SECONDS` (default 1) controls polling. `PREVIEW_RETENTION_DAYS` controls preview expiry. `CURRENCY_MAP` accepts instrument symbols or country suffixes mapped to currency codes. The default is `{"CA":"CAD","US":"USD"}`, displayed as unconfirmed. `EARNINGS_COSINE_DISTANCE`, `SLIDES_COSINE_DISTANCE` and `RTS_COSINE_DISTANCE` default to 0.35 and cap optional vector retrieval per source.

## Briefing pack and reviews

The [page index](docs/sources/01_index.md) links the 16 original source pages. The [catalog addendum](docs/sources/PACK_v1.1_corrections.md) links the exact R-002 definitions now reflected in the source fixture. Original images and unredacted text stay local. The public briefing and R-001 transcript mark public-hygiene removals.

The [generated API contract](api/openapi.json), [design](DESIGN.md) and [architecture plan](docs/collab/plans/PLAN.md) describe the current boundary. Use the [collaboration protocol](docs/collab/README.md), [tracker](docs/collab/TRACKER.md), [question log](docs/collab/QUESTIONS.md), [assumptions](docs/collab/ASSUMPTIONS.md) and [decisions](docs/collab/DECISIONS.md). Gate G2 awaits R-003. [S-003](docs/collab/status/S-003.md)
