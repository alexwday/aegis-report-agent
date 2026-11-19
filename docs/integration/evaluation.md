# Source and model evaluations

The document, theme, and peer evaluators connect only to the source DSN. Set SOURCE_DATABASE_URL to the approved read-only connection. The default chat, theme, and document mode uses the deterministic stub and lexical search. Excerpts and credential headers stay on the reviewer's machine unless using the opted-in gateway for drafting.

## Provide gateway credentials

Use --gateway real with the approved HTTPS INTERNAL_LLM_URL and CHAT_MODEL. EMBEDDING_MODEL defaults to text-embedding-3-large. Set INTERNAL_LLM_MODEL_HEADER to the approved custom header name when required. Each chat or embedding call sets that header to the model in its request body. INTERNAL_LLM_CA_BUNDLE can point to the approved CA bundle while retaining TLS verification. The evaluators accept --credentials-hook module:function or the AEGIS_EVAL_CREDENTIALS_HOOK environment variable. The explicit flag takes precedence. A hook is a trusted local Python callable that takes no arguments and returns a mapping of HTTP header names to string values. It is loaded once and called for every request, so it can refresh expiring credentials. Run the evaluators with the approved private module already on the Python import path. A missing or invalid configured hook fails with a generic error. When the operator omits the hook, the existing INTERNAL_LLM_API_KEY fallback is available.

For example, with private_eval_identity importable in the operator's environment, run:

```sh
export AEGIS_EVAL_CREDENTIALS_HOOK=private_eval_identity:request_headers
uv run --no-sync python scripts/eval_chat.py --gateway real
uv run --no-sync python scripts/eval_themes.py --bank RBC --year 2026 --quarter 3 --topic "Net Interest Income & Margins" \
  --gateway real --credentials-hook private_eval_identity:request_headers
uv run --no-sync python scripts/eval_documents.py --bank RBC --year 2026 --quarter 3 --topic "Net Interest Income & Margins" \
  --source rts --claims --gateway real
```

Keep the private provider and its configuration outside the public workspace. Chat evaluation uses fabricated drafts and tool results. With --gateway real, theme and document evaluations request embeddings and refine their rankings with the returned vectors. Claim drafting sends approved short candidate units to the configured gateway. Record accuracy, elapsed time, and sanitized observations for the reviewer. [Exact G6 acceptance cases](../collab/status/S-007.md)


Run chat evaluation with --repeat 3 for a per-case and aggregate pass rate. Gateway errors count as failed samples and testing continues. Real mode defaults to a 90% minimum aggregate rate. CHAT_CALL_SECONDS defaults to 20 and CHAT_TURN_SECONDS to 60. Planning retries once on timeout or a server error within the remaining budget.
