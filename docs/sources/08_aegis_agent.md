# THE EXISTING AEGIS CHATBOT AGENT (CONTEXT ONLY)

PAGE 8 / 16 24.0px

## WHAT IT DOES

A chatbot that answers analyst questions about bank disclosures. One LLM runs a tool-calling loop (OpenAI-compatible function calling, via an internal gateway; model tiers: medium for retrieval turns, high for synthesis). Request fields: question, sessionId, filters (which data sources), responseMode = standard or comprehensive.

## THE FOUR TOOLS THE LLM HAS

| Tool | Purpose |
|---|---|
| ask_clarification | Ask the user for missing bank, period or intent |
| check_data_availability | Query aegis_data_availability to say what bank/period/source combos exist |
| run_research | Fan out in parallel: one subagent call per (bank, period) x source |
| present_response | Declare the final widget type and title (text, table, chart) |

## RETRIEVAL STYLE PER SOURCE

| Source | How it retrieves |
|---|---|
| benchmarking | No vector search. LLM picks metrics from kpi_metadata; ONE parameterised SQL pull; deterministic markdown table |
| investor_presentation, supplementary_financials | Hybrid: vector (content, summary, keywords, metrics, HyDE) + BM25 + JSONB containment, weighted fusion, LLM rerank, gap-fill of sibling sheet chunks, then up to 2 LLM research iterations |
| transcripts, event_transcripts | LLM picks method per bank/period: full section, topic-classified chunks, or vector similarity; deterministic formatting; LLM synthesis |
| pillar3 | Vector top-3 per bank/period, tool-calling RAG loop |
| rts | LLM keyword extraction, embed, vector top-10 per bank/period, tool-calling RAG loop |

## OTHER BEHAVIOURS WORTH KNOWING

- Bank names are canonicalised to symbols (RBC, Royal Bank, RY -> RY-CA) from a monitored-institutions YAML list before any query.
- Every answer carries citations (file, page) where the source supports it; the UI shows a PDF viewer for slides, supp and rts files stored in S3.
- Charts are rendered as inline widgets that the frontend draws from structured events, not images.
- Prompts live in YAML files; errors are mapped to safe codes so internals never leak; a PII-detection middleware screens chat routes.
- Streaming over SSE; chat history persisted per session.

## KNOWN WEAKNESSES SEEN (DO NOT REPEAT)

- No similarity threshold: pillar3 and rts always return top-k even when irrelevant.
- Up to three independent 'is this bank/period available' checks that can disagree.
- Bank-key inconsistency across tables (see page 5).
- Several unused parameters and dead code paths in the subagent call contract.

=== END OF PAGE 8 OF 16 ===
