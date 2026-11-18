| ID | Phase | Task | Status | Evidence |
|---|---|---|---|---|
| T-001 | G0 | Create public repository layout and copy protocol. | DONE | [Protocol](README.md), [project entry](../../README.md), [API skeleton](../../api/openapi.json) |
| T-002 | G0 | Transcribe 16 pages and record release redactions. | DONE | [Source index and transcription notes](../../README.md#briefing-pack) |
| T-003 | G0 | Mirror documented source shapes with verified synthetic setup. | DONE | [Sources](../../db/sources.sql), [fixture check](../../db/seed/check-local.sh) |
| T-004 | G0 | Develop architecture, draft DDL and review trackers. | DONE | [Plan](plans/PLAN.md), [draft DDL](plans/rpt-draft.sql), [questions](QUESTIONS.md), [assumptions](ASSUMPTIONS.md), [decisions](DECISIONS.md) |
| T-005 | G0 | Submit S-001 with annotated review tag and wait for R-001. | DONE | [R-001](reviews/R-001.md), `review-001` |
| T-006 | G1 | Apply reviewed source fixture changes, own schema migrations and one-command local stack. | REVIEW | [Source catalog](../../db/sources.sql), [migration](../../db/migrations/001_report_slice.sql), [local runner](../../scripts/dev). Exact ordinals and two index inventories pending Q-015. |
| T-007 | G1 | Implement fail-closed auth, owner scopes, provider interfaces and the API. | DONE | [Auth](../../src/aegis_report/auth.py), [gateway](../../src/aegis_report/gateway.py), [OpenAPI](../../api/openapi.json), [ownership test](../../tests/test_postgres.py) |
| T-008 | G1 | Verify source role, coverage, bank keys and the benchmarking and earnings adapters. | DONE | [Sources](../../src/aegis_report/sources.py), [catalog and adapter tests](../../tests/test_postgres.py) |
| T-009 | G2 | Enable the five remaining logical source adapters with bounded retrieval and readiness probes. | TODO | |
| T-010 | G2 | Validate source anchors, metadata markers and retrieval quality on evaluated inputs. | TODO | |
| T-011 | G3 | Expand stages, source scope, preview and comparison functionality. | TODO | |
| T-012 | G3 | Add personal template lifecycle and extend HTML/JSON exports to PDF. | TODO | |
| T-013 | G4 | Build chat turn lifecycle, typed tools, resumable SSE, fallback turn result and provider tests. | TODO | |
| T-014 | G5 | Build a thin developer console and write the Functions Assist UI/SSE contracts. | TODO | |
| T-015 | G6 | Implement quarterly scheduling and corrections, readiness, retries, fencing and opt-in provisional publication. | TODO | |
| T-016 | G7 | Complete security/privacy review, load/cost testing, OpenAPI contract, and operations handoff. | TODO | |
| T-017 | G1 | Complete the template, patch, preview diff, version and next-quarter worker slice. | DONE | [HTTP demo](../../scripts/demo.py), [PostgreSQL test](../../tests/test_postgres.py) |
| T-018 | G1 | Generate OpenAPI, check it in CI and verify a changed load restarts the quiet interval. | DONE | [CI](../../.github/workflows/check.yml), [worker](../../src/aegis_report/worker.py), [tests](../../tests/test_postgres.py) |
| T-019 | G1 | Submit S-002 and review tag, stop at G1 pending R-002. | REVIEW | [S-002](status/S-002.md), `review-002` |
