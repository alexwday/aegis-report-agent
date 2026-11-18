# READ ME FIRST: INDEX AND ORDERS

PAGE 1 / 16 24.0px

## WHO YOU ARE AND WHAT THIS IS

You are the BUILDER. This pack (version 1.0, 2026-11-18, 16 pages, each photographed then OCR'd) shares our vision and priorities (ideas, not a spec) and describes the existing Postgres tables you build on. The REVIEWER (an AI with the real database) and a HUMAN RELAY work with you through a public GitHub repo that you create. Treat the pack as ground truth. If a page is unclear or looks mis-read by OCR, ask a numbered question instead of guessing.

## WHAT TO DO FIRST, IN ORDER

1. Read pages 2, 3 and 4 fully: our vision and context, your working protocol, and your first assignment. You are the architect: think deeply, then decide how to build it.
2. Read pages 5 to 16 (data conventions, coverage, identity, existing systems, the seven sources).
3. Execute the Phase 0 assignment on page 4: repo skeleton, verbatim transcription of this pack, sources.sql, PLAN.md, trackers, S-001.
4. Push with tag `review-001`, tell the human, and STOP until you receive R-001.

## PAGES

| # | Page |
|---|---|
| 2 | VISION AND CONTEXT (IDEAS AND PRIORITIES, NOT A SPECIFICATION) |
| 3 | COLLABORATION PROTOCOL: HOW WE WORK TOGETHER |
| 4 | TEMPLATES AND YOUR FIRST ASSIGNMENT (PHASE 0) |
| 5 | CONVENTIONS: BANKS, PERIODS, AVAILABILITY |
| 6 | COVERAGE MATRIX AND BANK UNIVERSE |
| 7 | IDENTITY AND ACCESS (EXISTING CONTRACT) |
| 8 | THE EXISTING AEGIS CHATBOT AGENT (CONTEXT ONLY) |
| 9 | THE AIRFLOW ETL AND REPORT REPO |
| 10 | SOURCE: investor_relations_benchmarking |
| 11 | SOURCE: investor_presentation |
| 12 | SOURCE: supplementary_financials |
| 13 | SOURCE: transcripts |
| 14 | SOURCE: event_transcripts |
| 15 | SOURCE: pillar3 |
| 16 | SOURCE: rts |

## GROUND RULES (APPLY ALWAYS)

- The source tables are READ-ONLY to you. Your system writes only to its own schema (suggest `rpt`).
- Assume you cannot reach the real database. Build `sources.sql` from these pages plus synthetic seed data so everything runs locally. List every assumption in ASSUMPTIONS.md.
- Your repo is PUBLIC. Never commit secrets, real hostnames, employee ids, emails, internal share paths or real disclosure text. Fabricated samples only.
- Counts and coverage were measured on the dev database on 2026-11-17 and will drift. Design for change; never hard-code them.
- Example SQL on pages 10 to 16 was executed against the real database and returned rows. Dates in examples are literals; replace them.

## TYPE ABBREVIATIONS USED ON THE TABLE PAGES

`txt`=text `vch`=varchar `int`=integer `num`=numeric `ts`=timestamp `tstz`=timestamptz `txt[]`=text array `jsonb`

`v3072`=pgvector vector(3072) `hv3072`=pgvector halfvec(3072). pgvector 0.8.0. Cosine distance operator `<=>`.

=== END OF PAGE 1 OF 16 ===
