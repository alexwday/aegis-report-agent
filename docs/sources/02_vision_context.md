# VISION AND CONTEXT (IDEAS AND PRIORITIES, NOT A SPECIFICATION)

PAGE 2 / 16 24.0px

## HOW TO READ THIS PAGE

This is what we have been imagining. It is brainstorming and intent, NOT a specification. You are expected to think deeply about the best way to build this and to make the build decisions yourself. Where your design differs from our ideas, prefer yours and record why in DECISIONS.md. The only fixed items are in the 'Constraints' section at the end.

## CONTEXT

- Users: finance professionals in RBC's CFO Group (Group Finance). They study Canadian banks and peers using each quarter's disclosures: the seven sources in this pack, both current and historical.
- Today: the existing Aegis chatbot (page 8) answers questions about the disclosures. Scheduled reports (page 9) are hand-built by developers, one Python module per report. Finance users cannot design their own reports.
- This project: a STANDALONE chatbot, used through the Functions Assist web UI, that lets those users design their own reports, save them, and have them re-run automatically every quarter as new source data lands in the existing source tables.

## THE IDEA IN PLAIN WORDS

A user describes in plain English the report they want. Together with the chatbot they build it SECTION BY SECTION. Each section can be previewed, adjusted by chatting, and compared with what it looked like before. The user can start from scratch, from a template, or by editing an existing report. When happy they save it, and the system regenerates it next quarter (and every quarter after) on the newest data, with no developer involved.

## WHAT MATTERS MOST TO US

- Section-by-section design that is EASY to adjust, with a preview that clearly shows WHAT CHANGED compared with the previous version.
- Any of the seven data sources can be used by any section, singly or combined.
- Control over HOW A SECTION USES TIME: only the current quarter; the current quarter against previous quarters; a trailing window; a sequence that walks year by year or quarter by quarter; comparisons to prior periods.
- Control over HOW A SECTION IS PRODUCED: one step, or STAGES. For example: first gather the raw content from the sources, then format it. Optionally intermediate steps (extract figures, compute, summarise, draft, check) that the user can see and shape in plain English. Think of each section as a small, user-shaped pipeline.
- SAVING so that all of the above (sources, time logic, stages, prompts, formatting) is stored and can be re-run quarter over quarter automatically, including sensible behaviour when only some banks or sources have updated.
- PREVIEW at every useful level (a section, possibly its individual steps, the whole report) without altering anything saved until the user chooses to save.
- TEMPLATES for layout and style, prebuilt and user-created
- Ownership by the logged-in user (page 7). How reports and templates are shared is for you to propose.

## IDEAS WE ARE UNSURE ABOUT: TAKE, ADAPT OR DISCARD

- SHARED EXTRACTIONS. One global list of things pulled out of every new disclosure (a metric, or a summarised piece of context; the source; which banks; other details), which users can add to through the agent, so different reports share findings and the values stay current as new disclosures arrive. This is only a concept for sharing findings between reports. It might become a cache, a library of reusable pipeline steps, a lightweight shared catalogue, or be dropped entirely.
- AD HOC RETRIEVAL straight from the source tables for anything not covered by shared or saved pieces.
- A LIBRARY of reusable section building blocks that users can pick up and adjust.
- If you see a better organising idea than any of these, propose it.

## HOW IT WILL BE DELIVERED

A usable DEMO UI is being designed here now, working against your API. After the backend API is finished, the frontend team builds the real interface directly inside Functions Assist, from your API contract (OpenAPI) and your UI specification (screens, states, streaming event contract). So the backend must be API-first, with chat streaming, and well documented.

## CONSTRAINTS (THE FIXED ITEMS)

- STANDALONE. No Aegis or Airflow code is available to you or to be reused. You READ the source tables (pages 10 to 16) and write ONLY to your own schema (suggest rpt).
- PROVENANCE. Figures and claims must be traceable to a source document, page or sheet. Never invent numbers.
- SAFE BY DEFAULT. Parameterised SQL, a read-only role for source access, treat disclosure text and user prompts as untrusted, no PII or tokens in logs, limits on LLM cost.
- CONFIGURABLE. LLM endpoint, models, keys and database URLs through environment variables; a stub LLM for tests. Assume an OpenAI-compatible chat and embeddings API.
- IDENTITY through an auth interface (page 7). Public repo hygiene (page 1). The collaboration protocol (page 3).
- STACK. Our production environment is Python 3.13, FastAPI and Postgres with pgvector, and it must run locally with one command. Prefer that; if you choose otherwise, justify it as a question. The UI stack is your proposal.

## EVERYTHING ELSE IS YOURS TO DECIDE

Architecture and data model; how a section pipeline is represented; how staged and time-sequenced logic is expressed and executed; how previews and change comparison work; how scheduling and auto-regeneration detect new data; whether and how shared extractions exist; the agent's tools; the API; the UI; the sharing model; export formats; testing; phasing. Raise a numbered question (Q-id) whenever you need a decision from us.

=== END OF PAGE 2 OF 16 ===
