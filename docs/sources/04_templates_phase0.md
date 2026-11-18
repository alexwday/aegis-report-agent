# TEMPLATES AND YOUR FIRST ASSIGNMENT (PHASE 0)

PAGE 4 / 16 24.0px

## STATUS DOCUMENT TEMPLATE: DOCS/COLLAB/STATUS/S-NNN.MD

Use exactly these headings, in this order, so the reviewer can navigate quickly. Keep it under about 400 lines; link to files instead of pasting code.

| # | Heading | Content |
|---|---|---|
| 0 | Header | S-NNN, title, phase and gate, date, tag review-NNN, commit range |
| 1 | Summary | At most 10 lines: what was achieved, what is not, overall confidence |
| 2 | Completed | Task ids (T-) done, with file links |
| 3 | Evidence | Commands run and VERBATIM output: tests, linters, migrations, how to reproduce |
| 4 | Changes since last review | Each CHG-id from the previous R-NNN: DONE (evidence) or DISPUTED (reason) |
| 5 | Decisions | New D-ids with options and reasons |
| 6 | Assumptions | New or changed A-ids, especially anything about the source tables |
| 7 | Questions | Q-ids: owner, blocking or not, options, your recommendation |
| 8 | Risks and issues | RISK-ids with mitigation |
| 9 | Not done or deferred | Honest list, with reasons |
| 10 | Next | Proposed next phase tasks and what you need answered first |

## WHAT THE REVIEWER WILL RETURN: R-NNN (SO YOU KNOW WHAT TO EXPECT)

A set of portrait pages with: VERDICT (APPROVED, APPROVED WITH CHANGES, or REWORK); answers to each Q-id; accepted or overruled D-ids; assumptions verified against the real schema (CONFIRMED or WRONG with the correct facts); required changes CHG-ids each with acceptance criteria; and the instruction for the next phase.

## PHASE 0 ASSIGNMENT: START IMMEDIATELY

Goal: a reviewed PLAN plus repo skeleton. No feature code. Take your time and reason carefully about the best design; the vision on page 2 is intent, and you may reshape it. Deliver everything below in ONE push, then stop at gate G0.

1. Create the public GitHub repo with the layout on page 3. Add the protocol to docs/collab/README.md.
2. Transcribe EVERY page of this pack into `docs/sources/NN_<slug>.md`, verbatim. Mark doubtful OCR with [?]. These are the shared source of truth.
3. Write `db/sources.sql`: CREATE TABLE statements for all source tables on pages 10-16 and the availability table (page 5), with exact column names, types and quoted identifiers. Add a synthetic seed generator that fills them with fabricated, plausible rows (embeddings may be random unit vectors) so everything can run locally.
4. Write `docs/collab/plans/PLAN.md` covering the sections listed below.
5. Create TRACKER.md, QUESTIONS.md, ASSUMPTIONS.md, DECISIONS.md, filled in. Ask every question you need answered; it is better to over-ask now.
6. Write S-001.md, commit `S-001: phase 0 plan`, tag `review-001`, push with tags, report to the human, STOP.

## PLAN.MD: SUGGESTED CONTENTS (ORGANISE FREELY; THE PLAN IS YOURS)

a. Architecture: components, data flow, process boundaries (diagram in mermaid or ASCII).

b. Own-schema data model: ERD and draft DDL (users, reports, versioned sections and pipelines, templates, previews, runs, outputs with provenance, schedules, audit, plus any shared-extraction tables you choose).

c. Your core model: how a report, its sections and their pipelines (sources, time logic, stages, intermediate steps, formatting) are represented, versioned, previewed, compared and saved. Whether to include shared extractions, and if so identity, re-ingest behaviour, triggers, dedupe, governance.

d. Section and report engine: how a section is generated from extractions plus ad hoc retrieval; prompt assembly; formatting; citations; one-section preview; whole-report assembly; export.

e. Template model and the first set of prebuilt templates you propose.

f. Agent design: the tool list (names, inputs, outputs), conversation state, streaming event types, guardrails.

g. API: resource list and endpoints; auth; error model. UI plan: screens, flows, wireframes in ASCII, and what the local test UI will do.

h. Scheduling and auto-regeneration; readiness rules for partial data.

i. Security and privacy; observability; testing strategy (including stub LLM); local dev setup.

j. Phased roadmap with T-ids and rough sizes; risks; open questions.

## WHAT THE REVIEWER WILL CHECK AT G0

- Every assumption in ASSUMPTIONS.md compared with the real schema and data.
- Source-access design: adapter layer, legacy vs unified tables, bank-key and period normalisation, availability staleness (pages 5, 6).
- Identity handled only through the auth interface; ownership checks everywhere (page 7).
- Core design: how sections, stages and time logic are represented and re-run each quarter; provenance; re-ingest behaviour; cost and abuse limits; preview isolation (and, if you adopt shared extractions, their governance).
- Plan realism: testable phases, nothing hand-waved, questions asked rather than guessed.

=== END OF PAGE 4 OF 16 ===
