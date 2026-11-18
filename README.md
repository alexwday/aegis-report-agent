# Aegis Report Agent

Phase 0 proposes a standalone report builder for analysts to design, preview, save and regenerate quarterly reports. The [architecture plan](docs/collab/plans/PLAN.md) and [review status](docs/collab/status/S-001.md) describe the proposed service and its current review gate.

## Run the local fixture check

Install PostgreSQL with server tools and pgvector with `vector` and `halfvec` support. Ensure `pg_config` points to that installation, then run as an ordinary local user:

```sh
./db/seed/check-local.sh
```

The command starts a disposable, socket-only Postgres cluster, applies the 19 documented fixture shapes, generates fabricated rows, applies the own-schema design draft, and checks the fixture. It removes the cluster when it finishes. PostgreSQL 15.12 and pgvector 0.8.1 were exercised for the gate. The app and demo begin after review.

## Briefing pack

The [page index](docs/sources/01_index.md) describes the order and scope. All 16 public Markdown pages are in [docs/sources](docs/sources/), each named by order. The photos and the local text copies stay outside Git. The transcription reproduces the page body, with Markdown formatting and screen line wraps reflowed. Browser chrome is outside the briefing. Public copies mark the redactions for disclosure values/headings or document identifiers on pages 10, 11, 13 and 16. Page 16's ring over A was clarified by the human relay and is recorded in the [question log](docs/collab/QUESTIONS.md).

## Review workflow

See the [protocol](docs/collab/README.md), [tracker](docs/collab/TRACKER.md), [assumptions](docs/collab/ASSUMPTIONS.md), and [decisions](docs/collab/DECISIONS.md). Gate G0 awaits R-001.
