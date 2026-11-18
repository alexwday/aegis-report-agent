| ID | Phase | Task | Status | Evidence |
|---|---|---|---|---|
| T-001 | G0 | Create public repository layout and copy protocol. | DONE | [Protocol](README.md), [project entry](../../README.md), [API skeleton](../../api/openapi.json) |
| T-002 | G0 | Transcribe 16 pages and record release redactions. | DONE | [Source index and transcription notes](../../README.md#briefing-pack) |
| T-003 | G0 | Mirror documented source shapes with verified synthetic setup. | DONE | [Sources](../../db/sources.sql), [fixture check](../../db/seed/check-local.sh) |
| T-004 | G0 | Develop architecture, draft DDL and review trackers. | DONE | [Plan](plans/PLAN.md), [draft DDL](plans/rpt-draft.sql), [questions](QUESTIONS.md), [assumptions](ASSUMPTIONS.md), [decisions](DECISIONS.md) |
| T-005 | G0 | Submit S-001 with annotated review tag and wait for R-001. | DONE | [R-001](reviews/R-001.md), `review-001` |
| T-006 | G1 | Apply reviewed source fixture changes, own schema migrations and one-command local stack. | DONE | [Source catalog](../../db/sources.sql), [migration](../../db/migrations/001_report_slice.sql), [local runner](../../scripts/dev). R-002 exact catalog closed in G2. |
| T-007 | G1 | Implement fail-closed auth, owner scopes, provider interfaces and the API. | DONE | [Auth](../../src/aegis_report/auth.py), [gateway](../../src/aegis_report/gateway.py), [OpenAPI](../../api/openapi.json), [ownership test](../../tests/test_postgres.py) |
| T-008 | G1 | Verify source role, coverage, bank keys and the benchmarking and earnings adapters. | DONE | [Sources](../../src/aegis_report/sources.py), [catalog and adapter tests](../../tests/test_postgres.py) |
| T-009 | G2 | Enable slides and RTS and retain typed statuses for unimplemented sources. | DONE | [Document adapters](../../src/aegis_report/documents.py), [PostgreSQL tests](../../tests/test_postgres.py) |
| T-010 | G2 | Verify page anchors, metadata probes and distance limits against fixtures. | DONE | [PostgreSQL tests](../../tests/test_postgres.py) |
| T-011 | G3 | Expose typed stage output and gather-only previews. | DONE | [Stage compiler](../../src/aegis_report/models.py), [engine](../../src/aegis_report/engine.py) |
| T-012 | G3 | Add personal templates and offline PDF export. | DONE | [PDF](../../src/aegis_report/pdf_export.py), [system templates](../../src/aegis_report/templates.py) |
| T-013 | G4 | Build chat turn lifecycle, typed tools, resumable SSE, fallback turn result and provider tests. | TODO | |
| T-014 | G5 | Build a thin developer console and write the Functions Assist UI/SSE contracts. | TODO | |
| T-015 | G6 | Implement quarterly scheduling and corrections, readiness, retries, fencing and opt-in provisional publication. | TODO | |
| T-016 | G7 | Complete security/privacy review, load/cost testing, OpenAPI contract, and operations handoff. | TODO | |
| T-017 | G1 | Complete the template, patch, preview diff, version and next-quarter worker slice. | DONE | [HTTP demo](../../scripts/demo.py), [PostgreSQL test](../../tests/test_postgres.py) |
| T-018 | G1 | Generate OpenAPI, check it in CI and verify a changed load restarts the quiet interval. | DONE | [CI](../../.github/workflows/check.yml), [worker](../../src/aegis_report/worker.py), [tests](../../tests/test_postgres.py) |
| T-019 | G1 | Submit S-002 and wait at G1 for R-002. | DONE | [S-002](status/S-002.md), [R-002](reviews/R-002.md), `review-002` |
| T-020 | G2 | Apply exact catalog v3, vendor identity and benchmark unit fallback. | DONE | [Catalog check](../../db/seed/check-catalog-v3.sql), [adapter](../../src/aegis_report/sources.py) |
| T-021 | G2 | Split immediate and automatic runs, expose scope stability, and release claim transactions before model calls. | DONE | [Worker](../../src/aegis_report/worker.py), [migration](../../db/migrations/002_run_readiness.sql) |
| T-022 | G2 | Compile fiscal presets to ordered, capped offsets and show resolved periods. | DONE | [Section spec](../../src/aegis_report/models.py), [unit tests](../../tests/test_unit.py) |
| T-023 | G2 | Combine sources and validate cited earnings themes with quote fallback. | DONE | [Themes validator](../../src/aegis_report/claims.py), [PostgreSQL tests](../../tests/test_postgres.py) |
| T-024 | G2 | Add structured row, cell, claim and period diffs, and extend the demo. | DONE | [Diff](../../src/aegis_report/diff.py), [demo](../../scripts/demo.py) |
| T-025 | G2 | Submit S-003 and wait at G2 for R-003. | DONE | [R-003](reviews/R-003.md), `review-003` |
| T-026 | G3 | Improve theme and document relevance and deliver read-only evaluator commands. | DONE | [Themes](../../scripts/eval_themes.py), [documents](../../scripts/eval_documents.py), [tests](../../tests/test_postgres.py) |
| T-027 | G3 | Cap reclaim attempts, disambiguate ticker prefixes, and prefer vendor standard-period changes. | DONE | [Worker](../../src/aegis_report/worker.py), [engine](../../src/aegis_report/engine.py) |
| T-028 | G3 | Implement owner-scoped report lifecycle and new drafts from historical versions. | DONE | [Repository](../../src/aegis_report/repository.py), [tests](../../tests/test_postgres.py) |
| T-029 | G3 | Add citation-detail excerpts and pinned schedule definition/enqueue. | DONE | [API contract](../../api/openapi.json), [schedule migration](../../db/migrations/007_schedule_definition.sql) |
| T-030 | G3 | Demonstrate three sections, staged preview, personal template and linked PDF. | DONE | [Demo](../../scripts/demo.py), [status](status/S-004.md) |
| T-031 | G3 | Submit S-004 and wait at G3 for R-004. | DONE | [S-004](status/S-004.md), `review-004` |
