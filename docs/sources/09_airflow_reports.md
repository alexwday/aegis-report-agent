# THE AIRFLOW ETL AND REPORT REPO

PAGE 9 / 16 23.3px

## ROLE

A separate Airflow DAG repo (Kubernetes) loads all source tables and also generates the scheduled reports from the same data. Secrets come from a vault at run time. Each report has a runtime budget and sends a 'running long' alert.

## PROCESS SERIES AND RUN ORDER

| Series | Meaning |
|---|---|
| O1-O5 | Ingest from NAS files into Postgres + S3: O1 benchmarking, O2 pillar3, O3 RTS, O4 investor presentation, O5 financial supplement |
| O6-O7 | Ingest from Snowflake: O6 transcripts, O7 calendar events |
| R1-R13 | Reports; each needs its O-series inputs complete for the SAME bank and fiscal period |
| O8 | Mail delivery of finished reports (runs last) |

Triggers: a NAS file watcher and an auto-trigger service start ingestion when new current-period files land; an orchestration DAG sequences them; the availability table is refreshed as the last step of each DAG; per-bank status emails follow.

## THE 13 REPORTS

R1 call summary, R2 key themes, R3 capital-markets readthrough, R4 bank earnings report, R5 CM US benchmarking, R6 WM benchmarking, R7 WM RTS commentary, R8 pillar3 optimization, R9 RTS blackline (YoY, QoQ), R10 cards and loyalty, R11 peer comparison, R12 APG RTS benchmarking, R13 peer analysis.

## HOW A REPORT IS BUILT TODAY

- Each report is a hand-written Python module (own pipeline, own doc/html/pdf output) plus rows in config tables (one versioned config table per report family, e.g. etl_category_config; a preview run reads a specific task_id instead of the max version).
- Prompts are YAML bundles: stage, version, system_prompt, user_prompt, and strict function-tool schemas (structured output). LLM calls go through the same internal gateway.
- Outputs go to S3; a row is written to aegis_reports (957 rows now); subscribers are in aegis_report_subscriptions; sends in aegis_report_deliveries.
- Config-edit flow (existing): user edits config rows -> a task row in aegis_config_edit_tasks -> a PREVIEW DAG run with that task_id -> preview PDF streamed back -> user applies, which promotes the rows to a new production version.

## INGESTION PATTERN FOR DOCUMENT SOURCES

- Parse the file (PDF, xlsx, transcript XML) into chunks; LLM adds summary, keywords, metrics per chunk; embed with text-embedding-3-large; load.
- Investor slides and supplement pipelines compute chunks and embeddings in separate local repos and Airflow only bulk-loads their CSV (full truncate and reload). Transcripts, RTS, pillar3 run fully inside Airflow.
- Load semantics differ by table (truncate-reload vs append). Re-loads can change row counts, so never cache chunk ids across loads.

## TAKEAWAY

Today a report = code + config rows. The new system should make a report DATA: a stored spec that a generic engine interprets.

## REPORT OUTPUTS TODAY: TABLE AEGIS_REPORTS (957 ROWS)

Columns: id int PK, report_name vch, report_description txt, report_type vch, bank_id int, bank_name vch, bank_symbol vch, fiscal_year int, quarter vch, local_filepath txt, s3_document_name txt, s3_pdf_name txt, markdown_content txt, generation_date ts, date_last_modified ts, generated_by vch (e.g. an ETL name), execution_id uuid, metadata jsonb. One row per generated file per bank and period; some reports are all-bank (bank columns NULL).

| report_type (rows) | report_type (rows) |
|---|---|
| rts_blackline_qoq (192), rts_blackline_yoy (162) | bank_earnings_report (162) |
| call_summary (136), key_themes (136) | pillar3_optimization (66) |
| cards_and_loyalty (27) + cards_and_loyalty_data (27) | call_summary_editor (20), cm_readthrough_editor (2) = preview runs |
| cm_us_benchmarking, cm_readthrough, wm_benchmarking, wm_rts_commentary (4 each) | peer_analysis (3), peer_comparison (3), peer_comparison_market_capture (3), apg_rts_benchmarking (2) |

## HOW REPORT CONFIG LOOKS TODAY: TABLE ETL_CATEGORY_CONFIG (837 ROWS)

Columns: id, report_type (call_summary, rts_blackline, cm_readthrough...), config_set (e.g. canadian_banks, us_banks, topics, sentiment, blackline_topics, qa, outlook), version int, is_active bool, created_by, created_at, display_order, transcript_sections (MD or QA), report_section (section heading in the output, e.g. Results Summary), category_name (e.g. Wealth and Asset Management, Volume Growth & NII), category_description (a topics checklist written as bullet lines), example_1..3 (example text), task_id (preview task, else NULL).

So today a section's content is defined as a list of CATEGORIES with description and examples, versioned, with a preview path via task_id. A shared extractions list is one possible evolution of this idea; learn from it but do not copy it.

## OTHER TABLES AROUND REPORTS

- aegis_config_edit_tasks: id, report_type, status, created_by, created_at, etl_started_at, etl_completed_at, applied_at, applied_by, apply_on_complete, etl_scope jsonb (banks, period), report_paths jsonb (preview PDFs), error_message, comparison_type. This is the existing preview-then-apply flow.
- aegis_config_edit_user_mgmt: which user may edit which report_type, and who is admin.
- aegis_report_subscriptions: id, user_id, user_email, report_type, bank_id, bank_name, is_subscribed, created_at, updated_at. aegis_report_deliveries: mail sends.
- Per-report config tables exist for newer reports (aegis_cards_loyalty_metrics_config, aegis_peer_comparison_metrics_config, aegis_apg_rts_benchmarking_categories_config, etl_peer_analysis_*). template_question_configs belongs to an unrelated product: ignore.
- Output formats today: docx, html, pdf, xlsx, plus markdown stored in markdown_content. Files are uploaded to S3 and referenced by name.

=== END OF PAGE 9 OF 16 ===
