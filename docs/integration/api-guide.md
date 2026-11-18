# Aegis API integration guide

Use /v1 and the checked-in OpenAPI contract. The request and response examples are generated from the same API in the disposable synthetic stack. [OpenAPI](../../api/openapi.json), [worked examples](api-examples.md), [Functions Assist UI specification](functions-assist-ui.md)

## Authentication

Send `Authorization: Bearer <token>` to the report API over HTTPS. The API verifies the token upstream with service=AEGIS and derives an opaque owner from the verified employee subject. Use the same authorization for JSON, downloads, and SSE. Upstream identity failure can return short detail. Hosted saved-report generation additionally requires the injected approved active-owner resolver. The localhost console offers only allowlisted fixture identities. [Operations](operations.md)

## Workflow

| Action | Request | Follow-up |
|---|---|---|
| Start | GET /v1/templates and /v1/catalog/banks, then POST /v1/drafts with template and bank. | Draft ID, editable spec and revision. |
| Edit | PATCH /v1/drafts/{id}/operations with a revision and typed operations. | Updated draft revision. The original add/replace endpoint remains available. |
| Chat | POST /v1/conversations, then POST /v1/conversations/{id}/turns with text and request_key. | 202 turn. Read /events or the turn GET resource. POST /accept with the returned revision. |
| Preview | POST /v1/drafts/{id}/previews with revision and period. Optionally pass section_id, stop_after or baseline_run_id. | 202 run ID. Poll the run, then fetch output.json and citations. |
| Save | POST /v1/drafts/{id}/save with the latest revision. | 201 report ID, saved version and next draft revision. |
| Generate | POST /v1/reports/{id}/runs with saved version, period and request_key. | Poll GET /v1/runs/{id}. On success fetch output.json, output.html or, for a saved run, output.pdf. |
| Schedule | PUT /v1/reports/{id}/schedule with pinned version, period, enabled flag and last revision as expected_revision. | Read the updated revision. POST /schedule/enqueue, then read /schedule/runs. |
| Evidence | GET /v1/runs/{id}/evidence/{opaque_id}/detail. | Source, locator and a short excerpt within this run. |

## Versioning, retries and pagination

Spec_version 1 versions the authored spec inside the HTTP /v1 contract. A report version is immutable. Draft revision is an optimistic lock on its editable spec. Catalog rename is independent. If the saved report head changes, a historical draft can fail to save even if its draft revision matches. Reopen the latest version and review the intended changes.

Generation keys are owner-scoped and tied to the exact request. Chat keys are conversation-scoped and tied to the exact message. Reuse the same key and body to retry an interrupted submit. Use a new key for a new logical request. Repeat acceptance of the same proposal revision and enqueue of the same schedule revision are idempotent. Preview creation can return another run ID on retry. After an uncertain edit or save, inspect the resource revision before submitting again.

Report lists, version lists and schedule history use limit and offset. Advance by the returned count until the page is short. The contract specifies each list's defaults and maximum. Lists can change while paging. Template and bank catalogs return arrays.

## Errors and capacity

| HTTP | Meaning | Client response |
|---|---|---|
| 401 or 403 | Credentials missing, expired or denied. | Follow the host authentication flow. |
| 404 | The resource is unavailable in the authenticated scope. | Return to the owned list or choose another resource. |
| 409 | Stale revision, reused key, conflicting proposal or run output still pending. | Use the reason code to reload, wait, or replace the request key. |
| 422 | Invalid fields or unsupported scope. | Apply loc and msg to fields. The endpoint may also return a machine reason string. |
| 503 | Dependency unavailable. | Retry reads with backoff and use the documented guards when retrying writes. |

Errors return a detail string or a detail array containing loc, msg and type. Use GET /v1/reasons to map stable reason codes. A successful GET can return a failed run or turn with error_code. Treat terminal state as the outcome of the underlying job. [Wording and states](functions-assist-ui.md#state-and-recovery)

G5 enforces per-operation scope and work budgets. General edge rate policy is a deployment concern. A report has one to six sections. A section can select four sources, twelve fiscal periods and up to twelve banks. The section's source-period product is capped at 24 before bank expansion. A report expands to at most 288 bank-source-period scopes. Chat allows one active turn per conversation, 2,000 input characters, seven tool calls, a bounded context, at most 5,600 model output tokens, and a time budget. A retrieval tool returns up to three evidence records. A turn can propose once and queue one preview. Automatic report runs retry expired leases up to three attempts. The default automatic quiet interval is 1,800 seconds.
