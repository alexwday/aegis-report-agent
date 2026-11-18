# Functions Assist UI specification

The generated API contract defines request and response types. The frontend owns navigation and presentation. The backend owns revisions, source readiness, provenance and acceptance. The loopback console exercises the same flows with fixture data and stub identities. [API contract](../../api/openapi.json), [integration guide](api-guide.md)

## Screens and flows

All paths in this table are relative to the /v1 namespace.

| Screen | Content and actions | State and route |
|---|---|---|
| Reports | Show active and archived lists, title, and head version. Let owners open, rename, clone, archive and restore. | List with archived, limit and offset. Inspect versions through /reports/{id}/versions. Rename updates the catalog title. Saved artifacts retain their version titles. |
| Templates | Group shared system templates and personal templates. Offer a bank picker for system templates. Start a new draft or snapshot a saved version into a personal template. | GET and POST /templates, POST /drafts. An optional bank override replaces the template's per-section bank scope. |
| Draft editor | Show revision and ordered sections. Edit banks, sources, time, instruction, format and mode. Add, replace, remove and reorder sections. Open a historical draft from its saved version. | GET /drafts/{id}, PATCH /drafts/{id}/operations with revision, and GET /drafts/{id}/stages. Refresh on 409 and ask the user to review the intended edit before retrying. |
| Chat | Bind to one draft and fiscal period. Show request, progress, final message, proposal and proposed revision. Pause or resume the connection, or cancel the turn. Show a separate explicit accept action. | Create a conversation and turn. Read events or the turn result. Send the proposal revision to /accept. Reload the draft after acceptance. A new fiscal period starts a new conversation. |
| Preview and diff | Pick a fiscal period, optional section and eligible baseline. Display stages, resolved fiscal periods and per-bank, claim, note, comparison and peer changes. | POST /drafts/{id}/previews, poll /runs/{id}, then open output.json. The baseline is a successful saved run of the draft's base version and period. Gather-only requires a staged section and omits the baseline. |
| Evidence and citations | Show cited rows and claims. Open a focusable drawer with the locator and short excerpt. Show available evidence, no matching evidence, and unavailable scopes by source, bank and period. | Group readiness entries by section_id. Use message for current per-scope wording. Look up opaque citation IDs within the run. |
| Peer comparisons | Display fiscal scope, units, currency provenance, high, low and median. Show “Higher is better” or “Lower is better” for ranks. For highest_to_lowest, display ordered_values without rank badges. List missing symbols. | Use sections[].peers[] and peer diff entries. An older artifact may lack direction. Use “Historical order” for those artifacts. |
| Schedule and history | Show enabled or paused state, pinned version, next period and revision. Offer explicit enqueue and recent runs with state and error wording. | GET and PUT /schedule with expected_revision for edits. Read /schedule/runs, then open a run. Calendar dispatch belongs to G6. |
| Exports | Offer HTML and JSON after a run succeeds. Offer PDF for a finished saved report. | Download output.html, output.json, or output.pdf through the authorized run. Use a sandbox when displaying HTML within the host. |

Fiscal periods are vendor labels, for example FY2090 Q2 with JSON {"year":2090,"quarter":2}.

## State and recovery

| State | What the user sees and can do |
|---|---|
| Empty | Name the next action, such as “Start from a template” or “Run a preview”. Give archived lists their own empty state. |
| Loading | Preserve the current context. Disable the action being submitted and announce when it finishes. |
| Partial data | Keep available rows and citations visible. Label unavailable scopes and stability by bank and period. Source catalog hints are informational. |
| Available with no match | Display no matching evidence separately from source absence. The ready observation has evidence_state no_match. |
| Error | Show mapped wording and an action if recovery is available. Render the upstream service's allowed detail as plain text. |
| Conflict | Reload the current draft or schedule. Display the new revision and preserve unsent user input where safe. Ask the user to confirm the revised action. |
| Validation or limit | Apply field errors to the controls using their location. Let users narrow banks, dates or sources. A turn that exceeds a limit can be followed by a shorter turn. |
| Disconnected | Preserve the last processed event ID. Check the existing turn or run by ID. Reuse the same key and payload for an idempotent retry. |
| Unauthorized or 404 | Use the host's sign-in flow for 401. For 404 show unavailable within the current session. |
| Waiting, succeeded or failed run | Distinguish waiting for stable data from an available output. Read terminal error_code independently of HTTP status. |

## SSE and polling

Use a streaming fetch or same-origin host proxy for bearer-authenticated SSE. Send Accept: text/event-stream and Last-Event-ID with the last applied sequence number. IDs increase within a turn. The next response replays events after that ID. A blank line terminates a frame. A heartbeat starts with a colon and leaves the cursor unchanged. Reconnect on a transport interruption or after the approximately 30-second response window, or read the JSON fallback. A cursor ahead of the turn returns 409. [HTML event stream standard](https://html.spec.whatwg.org/multipage/server-sent-events.html), [captured frames](api-examples.md)

| Event | Data | UI behavior |
|---|---|---|
| queued, started | Empty object | Show queue or active progress. |
| tool | name | Add the tool step to the event log. |
| preview_queued | preview_id | Link to the preview run. |
| patch_proposed | revision, operations | Render a change review. Enable accept after success if the draft revision still matches. |
| message | text | Show the assistant's complete reply as text. |
| succeeded, cancelled | Empty object | End active progress and refresh available actions. |
| failed | error_code | Show the reason and allow a new turn. |
| patch_applied | revision | Appears in replay after explicit acceptance. The acceptance response already contains this revision. |

The turn GET fallback supplies the same state, final message, proposal, applied revision, preview ID, error code and latest sequence. Pause closes the client stream. Cancel updates the server turn. A preview already queued retains its run lifecycle. Use SSE for chat progress and GET polling for report runs and schedule history. Start run polling at about one second, slow down while waiting or in the background, and back off after 503. Stop when terminal, on navigation away, or when identity changes.

## Identity, errors and accessibility

The host supplies the bearer token over HTTPS. The API verifies it upstream and derives ownership from the verified employee subject. Pass the same identity for streaming, polling, exports, and citations. Keep the token out of URLs and persistent browser storage. The console's identity picker applies only to the loopback fixture.

Fetch GET /v1/reasons for user-facing sentences keyed by stable machine codes. The same catalog supplies chat tool messages and the preview scope wording. For a new code, show a safe generic message and record the code separately. A structured 422 contains loc, msg and type. Render text fields and excerpts as text nodes. [Reason catalog](../../src/aegis_report/reasons.py)

Use labeled controls, descriptive headings, visible focus and text labels for status. Make subsection reorder possible with the keyboard. On opening the citation drawer, focus its heading and restore focus to the citation trigger when the drawer closes. Announce user actions and the final reply through a polite live region. Reserve alerts for errors requiring attention. Test narrow viewports, browser zoom and keyboard-only use. [WCAG 2.2](https://www.w3.org/TR/WCAG22/), [status messages guidance](https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html)
