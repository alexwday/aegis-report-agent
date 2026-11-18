# Aegis Report Agent

A standalone quarterly report builder with chat-based draft editing, peer comparisons, cited document evidence, and HTML, JSON, and PDF exports. G5 includes a local developer console and an integration handoff for Functions Assist.

## Try the G5 slice

Install `uv` and PostgreSQL server tools with pgvector 0.8.x. Run as an ordinary local user. `pg_config --bindir` must point to the PostgreSQL installation with pgvector.

```sh
./scripts/dev --demo
```

The command starts an isolated socket-only Postgres cluster, seeds fabricated rows, applies the migrations, and starts FastAPI and a worker with the stub model. At the default 1,800-second quiet period, it demonstrates gather-only preview, a personal template, and cited PDF export from a three-section report. An injected clock exercises the internal automatic next-quarter path. The chat demo proposes and previews a two-bank section, resumes the event stream, accepts the patch, shows the diff and saves. The fixture cluster is removed on exit.

To keep the synthetic PDF, run `AEGIS_DEMO_PDF=/path/to/new-report.pdf ./scripts/dev --demo` with a new output path.

Run `./scripts/dev` to keep the fixture stack available until Ctrl-C. Open [the developer console](http://127.0.0.1:8000/console) for reports, templates, draft edits, chat, previews, citations, schedules and exports. It uses the loopback API and bundled local assets. FastAPI documentation is at `/docs`. Set `AEGIS_DEV_PORT` to use another port.

```sh
./db/seed/check-local.sh
./scripts/test -q --disable-warnings
uv run --no-sync python scripts/openapi.py --check
```

## API and evaluation

The report API supports owner-scoped list, rename, archive, restore, clone, version history and historical draft creation. The shared system templates are Quarterly earnings, Credit and provisions watch, and Margins and capital brief. Owners can snapshot a saved version to a personal template and instantiate it into a new draft.

A section preview includes the output of its compiled stages. Set the section's `mode` to `staged`, then send `section_id` and `stop_after: "gather"` with the preview if you want to inspect source evidence before drafting. Finished saved runs expose HTML, JSON and PDF. Citation details carry an owner-scoped, bounded excerpt.

Use `bank` for a single symbol, `banks` for up to 12 explicit symbols, or `peer_group: "big-6-canadian-banks"` for the tagged core Canadian peers. Multi-bank benchmark sections show high, low and median. Rank 1 follows the metric’s configured direction. Unknown direction produces an ordered list of values. Missing banks and mixed units, currencies or change bases appear in the preview.

Create a conversation with `POST /v1/conversations` using a draft ID and fiscal period. Post a turn with a request key to the conversation's `/turns` resource. Read the turn resource as JSON or connect to its `/events` stream with `Last-Event-ID` to resume. Submit `/accept` with the proposal revision to apply it to the draft. Use `/cancel` to end a queued or running turn. Save through the existing draft endpoint. [API contract](api/openapi.json)

Schedule definitions support enable, pause, pinned version and an explicit next period. The enqueue endpoint runs that definition through the automatic quiet-period path. The owner can inspect recent scheduled runs at `/schedule/runs`. Calendar-driven submission remains a G6 task.

Run `uv run --no-sync python scripts/eval_chat.py` for the synthetic chat cases. The theme, document and peer harnesses use read-only source access. `eval_documents.py --claims` adds shortlisted units and final cited claims to the ranking output. Opt-in `--gateway real` supports a local credentials hook. The source harnesses use configured embeddings in that mode. [Evaluation guide](docs/integration/evaluation.md), [S-006 acceptance commands](docs/collab/status/S-006.md)

## Runtime configuration

`ENVIRONMENT=local` explicitly enables the fixed `LOCAL_AUTH_USER_ID` and permits the deterministic model stub. The fixture scripts set both. Outside local mode, set `AUTH_PROVIDER=upstream`, `AUTH_VALIDATION_URL`, `INTERNAL_LLM_URL`, and `CHAT_MODEL`. The upstream HTTPS endpoints and credentials come from deployment configuration. The model gateway accepts a per-call credential provider. The default wrapper reads `INTERNAL_LLM_API_KEY` if supplied. `EMBEDDING_MODEL` defaults to `text-embedding-3-large`.

Use separate `SOURCE_DATABASE_URL` (SELECT-only) and `RPT_DATABASE_URL` (runtime access to `rpt`). Apply migrations with a separate `RPT_MIGRATION_DATABASE_URL` and `uv run python -m aegis_report.migrate`. Set a stable `OWNER_KEY_SECRET` with at least 32 bytes to derive private ownership keys. A hosted worker requires an injected owner-status checker before generating saved reports.

`QUIET_SECONDS` (default 1800) gates automatic generation. Manual runs and previews immediately return current evidence with per-scope readiness and `data_stability`. `WORKER_POLL_SECONDS` (default 1) controls polling. `PREVIEW_RETENTION_DAYS` controls preview expiry. `CURRENCY_MAP` accepts instrument symbols or country suffixes mapped to currency codes. The default is `{"CA":"CAD","US":"USD"}`, displayed as unconfirmed. `EARNINGS_COSINE_DISTANCE`, `SLIDES_COSINE_DISTANCE` and `RTS_COSINE_DISTANCE` default to 0.35 and cap optional vector retrieval per source.

## Integration handoff

[Functions Assist UI specification](docs/integration/functions-assist-ui.md), [API integration guide](docs/integration/api-guide.md), [captured requests and responses](docs/integration/api-examples.md), [operations](docs/integration/operations.md)

## Briefing pack and reviews

The [page index](docs/sources/01_index.md) links the 16 original source pages. The [catalog addendum](docs/sources/PACK_v1.1_corrections.md) links the exact R-002 definitions now reflected in the source fixture. Original images and unredacted text stay local. The public briefing and review transcripts mark public-hygiene removals.

The [generated API contract](api/openapi.json), [design](DESIGN.md) and [architecture plan](docs/collab/plans/PLAN.md) describe the current boundary. Use the [collaboration protocol](docs/collab/README.md), [tracker](docs/collab/TRACKER.md), [question log](docs/collab/QUESTIONS.md), [assumptions](docs/collab/ASSUMPTIONS.md) and [decisions](docs/collab/DECISIONS.md). Gate G5 awaits R-006. [S-006](docs/collab/status/S-006.md)
