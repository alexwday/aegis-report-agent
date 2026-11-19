# API and Functions Assist handoff

## API-to-screen map

Paths are relative to `/v1`. All report, draft, conversation, output, schedule and evidence requests run under the current authenticated owner. The local reference uses the loopback fixture identity. The host integration supplies its approved session and ownership wiring. [Schema and error responses](../../api/openapi.json)

| Screen or action | Request sequence | Rendering contract |
|---|---|---|
| Reports home | `GET /catalog/banks`, `/templates`, `/reports?archived=false`; schedules for active reports | Resolve bank chips via the catalog. For a scheduled report show the latest waiting target and missing banks instead of a generic saved status. |
| Templates | `GET /templates`; `POST /drafts` with `template`, `bank`, `title` | Use `description` and `section_titles` to preview the template. Personal templates accept the original bank scope. |
| Start with chat | `POST /drafts`, `POST /conversations`, `POST /conversations/{id}/turns` | Start with the selected bank and editable working draft. Use a unique request key per submission. |
| Conversation progress | `GET /conversations/{id}/turns/{turn}/events`, then `GET /conversations/{id}/turns/{turn}` | Map tool events to readable text. Carry the last SSE event ID into reconnect. Use the terminal JSON for the final message, proposal and preview reference. Abort or cancel via `POST …/cancel` when the user asks. |
| Review proposal | `POST …/accept` with revision or `POST …/reject` | Accept with the draft revision. A stale revision is a conflict. Reject is durable and idempotent. An edited proposal passes explicit replacement operations to the same acceptance endpoint so the section and proposal state commit together. |
| Edit report or section | `GET /drafts/{id}`, `PATCH /drafts/{id}/title`, `PATCH /drafts/{id}/operations` | Pass a typed add, replace, remove or reorder operation and the observed revision. Duplicate by adding a copy with a distinct internal key. Server still validates scope, uniqueness and ordering. |
| Preview and gather | `POST /drafts/{id}/previews`, `GET /runs/{id}` and `/output.json` | Gather uses `section_id` plus `stop_after: gather`. Show queued and running progress. Use `readiness` per source, bank, fiscal period and section. |
| Compare saved and draft | `POST /reports/{id}/runs`, wait for the base version and period, then `POST /drafts/{id}/previews` with `baseline_run_id` | The API pairs matching output items in `diff_details.entries` and preserves before and after positions. The client also compares the draft settings to `GET /reports/{id}/versions/{version}`. |
| Citation drawer | `GET /runs/{id}/evidence/{citation}/detail` | Use the authorized excerpt, source, bank and fiscal period. Combine with scoped `data_stability` from the selected run. Use a conservative unknown label if an older run has no matching scope. |
| Save and history | `POST /drafts/{id}/save`, `GET /reports/{id}/versions`, `GET /reports/{id}/versions/{version}`, `POST /reports/{id}/versions/{version}/drafts` | `note` is optional, durable and at most 500 characters. Compare neighbouring version settings before reopening a historical draft. |
| Report actions | `GET/PATCH /reports/{id}`, `POST …/clone`, `POST …/archive` or `…/restore`, `POST /templates` | Ask for confirmation before archive. Clone or snapshot the selected saved version. |
| Schedule settings | `GET/PUT /reports/{id}/schedule`, `GET /reports/{id}/versions` | Treat missing configuration as an unset schedule. Write the current `expected_revision` and the version, fiscal target, wait policy and timezone. |
| Schedule timeline | `GET /reports/{id}/schedule/periods` and `…/runs`; `POST …/enqueue` | `first_checked_at` gives observed wait time. `next_check_at`, `current_kind`, `current_run_id`, `missing` and `last_correction` drive the timeline. Show superseded artifacts in history. |
| Download | `GET /runs/{id}/output.html`, `.pdf` or `.json` | Saved exports generate the pinned version for the selected fiscal period. Scheduled downloads use the current published run or the explicit historical selection. Prefix provisional downloads. |
| Help, source check and support | `GET /reasons`, `POST /sources/{source}/probe`; Developer tools expose `/drafts/{id}/stages`, lower-level requests and diagnostics | Check physical source status without initiating a report. Only support flows expose raw JSON and source identifiers. |

## Plain-language wording

| Condition | UI copy or wording rule |
|---|---|
| No saved reports | “No saved reports yet” with a short save hint |
| Loading or reconnecting | “Preparing report…” or “Connection interrupted. Reconnect to pick up where you left off.” |
| Missing data | “Waiting for required data” at section level. “Source not available yet” beside an absent source. |
| Existing source gives no evidence | “No matching evidence” and “This source was available and returned no matching evidence.” |
| Conflicting edit | “The draft changed. Refresh it before applying another edit.” Offer Reload draft and, for a saved report, Open latest saved version. |
| Expired session | “Your session has expired. Reload the workspace to reconnect.” |
| Section limit | “A report can have up to six sections.” |
| Temporary failure | “The reporting database is temporarily unavailable.” Unknown errors have a short retry message. |
| Currency mapping pending | “Currency unconfirmed” on the figure and peer view where applicable |
| Peer direction | “Lower is better” or “Higher is better”, plus “Rank 1 = best” where ranking is supported |
| Provisional | “Provisional report · Some sources are still pending.” Include “provisional” in the download menu, filename and artifact. |
| Waiting after a quarter ends | Show which banks and sources are missing, the elapsed observed wait and the next check. The verified Canadian calendar floor is quarter end for the core Big Six. Earnings release can occur later. Other banks use physical source readiness without a date-based floor. |

Map recognized reason codes through the canonical `/reasons` catalog. Normalize UI request failures to a plain message and keep machine codes in support tools. Surface source content as text and honor its owner-scoped availability. [Canonical wording](../../src/aegis_report/reasons.py)

## What Functions Assist should carry forward

| Product | Local demonstration |
|---|---|
| Reports, templates, schedule status and help, plus fact and claim citations | Fixture identities, seed banks, fiscal dates and deterministic suggested chat example |
| Conversation beside document canvas, contextual settings, evidence and history | Browser-native layout and replaceable Aegis palette as implementation references |
| Review, revision protection, version restore, schedule and provisional labels | The short local polling and quiet period for the demo |
| Ownership, credential routing, focus and announcement behavior, error states | Loopback server, local source probe menu and raw Developer tools console |
| Telemetry integration for latency, failure and attempts | Notification delivery remains a no-op hook. Exposing a working notification setting requires a delivery channel and ownership rules. |

Use real product single sign-on, deployment and browser compatibility validation in the embedding. Token names and styling can map into the host design system after Q-027. The local reference module boundaries separate transport and events (`api.js`), shared controls (`components.js`), the report canvas and editor (`workspace.js`), and navigation, templates and scheduling (`app.js`). [Frontend source](../../ui/reference)
