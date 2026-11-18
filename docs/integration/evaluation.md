# Source and model evaluations

The document, theme, and peer evaluators connect only to the source DSN. Set SOURCE_DATABASE_URL to the approved read-only connection. The default chat, theme, and document mode uses the deterministic stub and lexical search. Excerpts and credential headers stay on the reviewer's machine unless using the opted-in gateway for drafting.

## Provide gateway credentials

Use --gateway real with the approved HTTPS INTERNAL_LLM_URL and CHAT_MODEL. EMBEDDING_MODEL defaults to text-embedding-3-large. The evaluators accept --credentials-hook module:function or the AEGIS_EVAL_CREDENTIALS_HOOK environment variable. The explicit flag takes precedence. A hook is a trusted local Python callable that takes no arguments and returns a mapping of HTTP header names to string values. It is loaded once and called for every request, so it can refresh expiring credentials. Run the evaluators with the approved private module already on the Python import path. A missing or invalid configured hook fails with a generic error. When the operator omits the hook, the existing INTERNAL_LLM_API_KEY fallback is available.

For example, with private_eval_identity importable in the operator's environment, run:

```sh
export AEGIS_EVAL_CREDENTIALS_HOOK=private_eval_identity:request_headers
uv run --no-sync python scripts/eval_chat.py --gateway real
uv run --no-sync python scripts/eval_themes.py --bank RBC --year 2026 --quarter 3 --topic "Net Interest Income & Margins" \
  --gateway real --credentials-hook private_eval_identity:request_headers
uv run --no-sync python scripts/eval_documents.py --bank RBC --year 2026 --quarter 3 --topic "Net Interest Income & Margins" \
  --source rts --claims --gateway real
```

Keep the private provider and its configuration outside the public workspace. Chat evaluation uses fabricated drafts and tool results. With --gateway real, theme and document evaluations request embeddings and refine their rankings with the returned vectors. Claim drafting sends approved short candidate units to the configured gateway. Record accuracy, elapsed time, and sanitized observations for the reviewer. [Exact G5 acceptance cases](../collab/status/S-006.md)
