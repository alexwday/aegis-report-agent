# COLLABORATION PROTOCOL: HOW WE WORK TOGETHER

PAGE 3 / 16 23.8px

## ROLES

| Role | Who | Does |
|---|---|---|
| BUILDER | You | Designs and writes all code and docs. Works only inside the public GitHub repo. Stops at gates. |
| REVIEWER | An AI that can read your repo and a live copy of the real database | Pulls your repo, reads your status doc, checks your assumptions against the REAL schema, reviews code, answers your questions, issues written responses (R-ids) as pages like these. |
| HUMAN RELAY | The person using both of you | Photographs the reviewer's response pages to you, tells the reviewer when you have pushed, and is the final authority on product questions. |

## THE LOOP (REPEAT PER PHASE)

1. WORK. Do the current phase. Small commits. Push to `main` on the public repo.
2. REPORT. At the end of the phase write ONE status document `docs/collab/status/S-NNN.md` (format on page 4). Update TRACKER.md, QUESTIONS.md, ASSUMPTIONS.md, DECISIONS.md. Commit with message `S-NNN: <title>`.
3. TAG AND PUSH. Create an annotated tag `review-NNN` on that commit. `git push origin main --tags`. Then tell the human exactly: 'S-NNN pushed, tag review-NNN'.
4. STOP. Do not start the next phase. Wait for the reviewer's response page R-NNN.
5. RECEIVE. The human shows you R-NNN as photographed pages. Transcribe VERBATIM into `docs/collab/reviews/R-NNN.md` (mark any uncertain OCR read with [?]). Commit `R-NNN received`. Push.
6. ACT. Do what R-NNN says. Every CHG-id in it must appear in your next status doc as DONE (with evidence) or DISPUTED (with reasons). Every answer to a Q-id is binding unless you dispute it in writing.

**NOTE:** The reviewer reads ONLY what is in the repo. If it is not committed and pushed, it does not exist for review. Never rely on chat messages for decisions: write them in DECISIONS.md.

## IDENTIFIERS (NEVER REUSE A NUMBER; 3 DIGITS)

| Id | Meaning | Written by |
|---|---|---|
| S-NNN | Status document (one per gate) | Builder |
| R-NNN | Reviewer response, matches S-NNN (R-001 answers S-001) | Reviewer |
| Q-NNN | Question. Has owner: REVIEWER or HUMAN. Marked BLOCKING or not | Builder |
| D-NNN | Decision with options considered and reason | Builder (reviewer may overrule) |
| A-NNN | Assumption about source tables or environment, with how to verify | Builder |
| CHG-NNN | Required change from the reviewer, with acceptance criteria | Reviewer |
| T-NNN | Task in TRACKER.md | Builder |
| RISK-NNN | Risk or issue with mitigation | Either |

## REPOSITORY LAYOUT (CREATE THIS IN THE FIRST PUSH)

`README.md` how to run. `DESIGN.md` living architecture. `docs/collab/` = `README.md` (this protocol, copied), `TRACKER.md`, `QUESTIONS.md`, `ASSUMPTIONS.md`, `DECISIONS.md`, `status/`, `reviews/`, `plans/`. `docs/sources/` = verbatim transcription of every page of this pack, one `.md` per page. `db/` = `sources.sql` (source table DDL from the pages), `seed/` (synthetic data generator), `migrations/` (your own schema). `src/`, `tests/`, `ui/`, `api/openapi.json`.

## TRACKER RULES

- TRACKER.md is a single table: `ID | Phase | Task | Status | Evidence`. Status is one of TODO, DOING, REVIEW, DONE, BLOCKED. Evidence = file path or test name or commit hash.
- QUESTIONS.md: one table with `Q-id | Owner | Blocking | Question | Why it matters | Options | Your recommendation | Status | Answer (R-id)`. Never delete rows; mark ANSWERED.
- ASSUMPTIONS.md: `A-id | Table or system | Assumption | Impact if wrong | How to verify | Status` (UNVERIFIED, CONFIRMED, WRONG).
- DECISIONS.md: `D-id | Date | Decision | Options considered | Reason | Status` (PROPOSED, ACCEPTED, OVERRULED).

## PHASE GATES (PROPOSED; YOU MAY REFINE THEM IN THE PHASE 0 PLAN)

| Gate | Phase | Exit evidence |
|---|---|---|
| G0 | Plan | Plan docs, repo skeleton, sources.sql, S-001. No feature code. |
| G1 | Foundations | Own schema and migrations, source adapter, auth interface, seed data, API skeleton, tests passing |
| G2 | Extractions | Shared extractions model, runner, triggers, preview, tests |
| G3 | Sections and reports | Section engine, templates, section and report preview, save, export |
| G4 | Chat agent | Agent tools, streaming events, conversation persistence |
| G5 | Local UI | Test UI covering all flows, UI spec for the frontend team |
| G6 | Scheduling | Auto-regeneration on new data, status, retries |
| G7 | Hardening | Security review fixes, OpenAPI, docs, load and cost tests |

## BEHAVIOUR RULES

- Ask rather than invent. A wrong guess about a source table is expensive; a question is cheap.
- If any page in this pack is unclear or looks mis-OCR'd, raise a Q-id instead of guessing.
- Keep scope to the current phase. Do not pre-build later phases.
- Public repo hygiene: no secrets, real hostnames, internal paths, real user data or real disclosure text. Fabricated samples only.
- Status docs must contain REAL command output (test counts, errors), not summaries of what you intended.

=== END OF PAGE 3 OF 16 ===
