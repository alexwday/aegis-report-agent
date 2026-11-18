# IDENTITY AND ACCESS (EXISTING CONTRACT)

PAGE 7 / 16 24.0px

## HOW THE EXISTING AEGIS API IDENTIFIES A CALLER

- FastAPI service. Protected routes depend on validate_token: it takes the `Authorization: Bearer <token>` header and calls an external auth service (GET, query service=AEGIS, short timeout, run in a worker thread). HTTP 200 = valid. Auth-service 503 or timeout = respond 503.
- The validated response body is stored on the request as token_data. The caller identity is token_data.data.employee_id (a string). No employee_id = 401.
- Helper get_current_user_id(request) returns that employee_id. Rule in the code: the ONLY identity usable for authorization is the one from the validated token; never a user id sent in the body or query.
- require_caller_matches(claimed, caller): if a client still sends user_id/userId in the body, it must equal the token identity or the API returns 403.
- Local development: if env ENVIRONMENT is explicitly local, token validation is skipped and identity is a fixed value (env LOCAL_AUTH_USER_ID, default local-dev-user). If ENVIRONMENT is unset, auth stays ON (fail closed).

NOTE: EMAIL: Aegis does not read an email from request headers. Identity is employee_id from the token. Email only appears as a client-supplied optional field (user_email) when subscribing to reports, stored in the subscriptions and access tables.

NOTE: The chat stream endpoint takes userId from the request BODY to key sessions and chat history (legacy behaviour). Do NOT copy this. Your system must take the user from the token only.

## CONTRACT FOR YOUR SYSTEM

- Define one dependency, get_current_user(), returning {user_id: str, email: str or None}. All ownership and permission checks use user_id.
- Production implementation: validate the bearer token against an auth service whose URL comes from an env var, read employee_id from the response. Dev implementation: fixed local user selected by env var. Hide both behind an interface so the real one can be wired in later.
- Email: treat as an optional profile field. Where a real email is needed (delivery of reports) it must come from a separate, explicit source or the user's own input.
- Do not log tokens. Do not store raw employee ids in analytics logs (existing Aegis hashes user and manager info for QA reporting).

## EXISTING ACCESS-CONTROL AND SESSION MODEL

- Report access: table of user x report_type with admin flag; helpers check_has_access(user, report_type) and check_is_admin(...). Admins can add or remove users for that report type.
- Sessions: user_session table; a session id is created on first message and reused until a configurable idle timeout. Conversations, messages, chat_history and log tables key off user id plus session id.
- Streaming: POST /aegis/stream returns Server-Sent Events, JSON per data: line, event type in agent / widget / etc.

=== END OF PAGE 7 OF 16 ===
