# SOURCE: transcripts -> aegis_transcripts (earnings calls)

PAGE 13 / 16 24.0px

## WHAT IT IS

Earnings-call transcripts from Snowflake/vendor XML. One row per CHUNK (a few paragraphs of one speaker block). 1,106 rows, 38 files, 34 institutions. Legacy schema (not the unified pair). PK `id` int identity.

## COLUMNS (27)

File and event: `file_path` txt (internal share path: do not publish), `filename` txt (pattern `[redacted for public repository: vendor filename]` = ticker_Q_FY_type_eventid_versionid), `date_last_modified` tstz, `title` txt ('Q3 2026 Earnings Call'), `transcript_type` txt (`Corrected` 961 / `Raw` 145), `event_id` txt, `version_id` txt.

Company: `institution_type` txt (Canadian_Banks, European_Banks, US_Boutiques, US_Wealth_Asset_Managers, US_Regionals, Australian_Banks, Trusts, Canadian_Insurers), `institution_id` txt, `ticker` txt NOT NULL (canonical symbol), `company_name` txt. Period: `fiscal_year` int, `fiscal_quarter` txt.

Structure: `section_name` txt = `MANAGEMENT DISCUSSION SECTION` (362 rows; has speaker_block_id, NO qa_group_id) or `Q&A` (744 rows; both ids set). `speaker_block_id` int, `qa_group_id` int (one analyst question + its answers), `chunk_id` int (order inside the block), `chunk_tokens` int, `chunk_paragraph_ids` txt[].

Content: `chunk_content` txt (starts with a speaker tag like [Name, Title, Company]), `block_summary` txt (LLM summary of the block), `classification_ids` txt[] and `classification_names` txt[] (topic taxonomy, e.g. Net Interest Income & Margins, Credit Quality & Provisions, Capital & Liquidity, Expenses & Efficiency, Revenue & Growth; 15+ topics), `chunk_embedding` v3072 (never NULL), `created_at`, `updated_at` tstz.

## COVERAGE WARNING

**NOTE:** Today this table holds FY2026 Q3 for 31 institutions (Q4: 2, FY2027 Q2: 1). Core six Canadian banks = Q3 2026 only (160 rows). Their Q1 and Q2 2026 calls live ONLY in the unified twin `aegis-earnings-transcripts-data/-embeddings` (368 / 6,226 rows, unified schema of page 11: `name`, `summary`, `chunk_content` = Q&A exchange or MD block, `keywords`, `metrics`). A full call history needs BOTH. Prefer `Corrected` over `Raw`; dedupe by `event_id`.

## INDEXES AND READING ORDER

btree: `ticker`, `(ticker,fiscal_year,fiscal_quarter)`, `(fiscal_year,fiscal_quarter)`, `company_name`, `event_id`.

Read a call in order: MD by `(speaker_block_id, chunk_id)`; Q&A by `(qa_group_id, speaker_block_id, chunk_id)`.

Aegis' output shows no source link, only the call title.

### A) management discussion in reading order

```sql
SELECT speaker_block_id, chunk_id, left(chunk_content,100) AS text
FROM aegis_transcripts
WHERE ticker='RY-CA' AND fiscal_year=2026 AND fiscal_quarter='Q3'
  AND transcript_type='Corrected' AND section_name='MANAGEMENT DISCUSSION SECTION'
ORDER BY speaker_block_id, chunk_id LIMIT 10
```

### B) Q&A on one topic

```sql
SELECT qa_group_id, speaker_block_id, left(chunk_content,100) AS text
FROM aegis_transcripts
WHERE ticker='RY-CA' AND fiscal_year=2026 AND fiscal_quarter='Q3' AND section_name='Q&A'
  AND 'Net Interest Income & Margins' = ANY(classification_names)
ORDER BY qa_group_id, speaker_block_id, chunk_id LIMIT 10
```

### C) vector search (:qvec = query embedding)

```sql
SELECT ticker, qa_group_id, chunk_embedding <=> :qvec AS dist
FROM aegis_transcripts
WHERE ticker='RY-CA' AND fiscal_year=2026 AND fiscal_quarter='Q3'
ORDER BY dist LIMIT 5
```

## TOPIC TAXONOMY IN CLASSIFICATION_NAMES (VALUE AND CHUNK COUNT)

```text
Strategic Initiatives & Transformation (702)
Revenue & Growth (614)
Capital & Liquidity (543)
Macro & Market Environment (541)
Net Interest Income & Margins (518)
Profitability & Returns (509)
Expenses & Efficiency (498)
Wealth & Asset Management (436)
Commercial & Corporate Banking (395)
Geographic & International (384)
Capital Markets & Investment Banking (379)
Credit Quality & Provisions (336)
Consumer & Retail Banking (291)
Technology & Digital Innovation (280)
Customer & Client Experience (278)
Trading & Markets (224)
Workforce & Talent (205)
Regulatory & Compliance (167)
Payments & Transaction Services (152)
Risk Management & Cybersecurity (101)
Non-Relevant (64)
ESG & Sustainability (38)
Digital Assets & Emerging Payments (17)
```

=== END OF PAGE 13 OF 16 ===
