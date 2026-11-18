# CONVENTIONS: BANKS, PERIODS, AVAILABILITY

PAGE 5 / 16 24.0px

## BANK IDENTITY: CANONICAL SYMBOL

Canonical form is `TICKER-CC`, e.g. `RY-CA`. Core six Canadian banks and their `bank_id`: `RY-CA`=1, `BMO-CA`=2, `CM-CA`=3, `NA-CA`=4, `BNS-CA`=5, `TD-CA`=6. Also tracked: `LB-CA`=7, `JPM-US`=8, `BAC-US`=9, `WFC-US`=10, `C-US`=11, `MS-US`=12 and more (85 banks total in availability).

| Table | Bank column(s) and format |
|---|---|
| benchmarking_report | `bank` = short label (RBC, CIBC, NBC, Citi...) AND `bank_symbol` = canonical. Aggregates `Big 6`, `Peer (ex-RY)`, `Peer (ex-RY-US)` have NULL symbol |
| investor slides, pillar3, rts, event twin | `bank` = canonical symbol |
| financial-supp (+embeddings) | MIXED: `RY` and `RY-CA` both occur (older loads used short code). Match both |
| aegis_transcripts, aegis_event_transcripts | `ticker` = canonical symbol; `institution_id` = text number (matches bank_id for the core six: verify) |

## FISCAL PERIODS

Pair `fiscal_year` + `quarter` ('Q1'..'Q4'). Canadian bank fiscal year starts Nov 1: Q1 = Nov-Jan, Q2 = Feb-Apr, Q3 = May-Jul, Q4 = Aug-Oct. The fiscal_year label is the calendar year in which the year ENDS (Q1 2026 = Nov 2025 to Jan 2026). Non-Canadian banks use the vendor/company fiscal label (verify before aligning peers).

Type and name differences: `year` is `vch` ('2025') in pillar3_embedding, `int` in rts_embedding. Slides and supp tables store `fiscal_year` as `txt`. Transcripts call the quarter column `fiscal_quarter`. Benchmarking also has combined `yr_Qtr` = '2026_Q3'.

## AEGIS_DATA_AVAILABILITY: WHAT IS LOADED

One row per bank x fiscal_year x quarter (1,082 rows, 85 banks, FY2019 to FY2027). Columns: `id` int PK, `bank_id` int, `bank_name` vch, `bank_symbol` vch, `bank_aliases` txt[] (e.g. RBC, Royal Bank), `bank_tags` txt[], `fiscal_year` int, `quarter` vch, `database_names` txt[], `last_updated` ts, `last_updated_by` vch.

`database_names` lists loaded sources: `pillar3`, `rts`, `transcripts`, `event_transcripts`, `investor_presentation`, `investor_relations_benchmarking`, `supplementary`, `supplementary_financials` (both spellings exist: 385 vs 12 rows), `reports`. Latest complete quarter now = FY2026 Q3 (49 rows), Q4 partial (6 rows).

## TWO TABLE GENERATIONS (IMPORTANT)

- LEGACY, read by Aegis today: `benchmarking_report`, `aegis_transcripts`, `aegis_event_transcripts`, `pillar3_embedding`, `rts_embedding`.
- UNIFIED pair pattern `"aegis-X-data"` + `"aegis-X-embeddings"` (see page 11): used today for investor-slides and financial-supp. Twins also exist but are NOT read by Aegis yet: earnings-transcripts, event-transcripts, pillar3, rts. They hold FY2026 Q1-Q2 only so far. This is the direction of travel: put source access behind an adapter layer.

## EMBEDDINGS AND CITATIONS

Embedding model `text-embedding-3-large`, 3072 dims. Legacy pillar3/rts use `hv3072`; others `v3072`. No ANN (HNSW/IVFFlat) index was seen on rts_embedding, aegis_transcripts or slides-embeddings: queries filter by btree columns first. Citation anchors: slides/supp = `file_path` + `page_number`; rts = `filename` + `page_no`; pillar3 = `filename` + `sheet_name`; transcripts = `title/filename` only (no page).

## SOURCE SELECTION GUIDE: WHICH SOURCE ANSWERS WHICH KIND OF QUESTION

| Need | Best source | Why / caution |
|---|---|---|
| Reported KPIs, ratios, growth rates, segment numbers, peer comparison | benchmarking_report | Clean numbers with QoQ, YoY and multi-year change precomputed. 166 metrics (page 10). Quarterly only. Not every bank has every metric. |
| Line items and footnotes behind the numbers | financial-supp | Spreadsheet sheets in markdown; six Canadian banks |
| Management narrative, tone, outlook, analyst questions | transcripts | Q&A topics are pre-classified. Check which table holds the period (page 13) |
| Strategy, targets, medium-term goals, segment slides | investor slides | One chunk per slide; keywords and metrics tags help search |
| Regulatory capital, RWA, leverage, TLAC, liquidity detail | pillar3 | Raw sheet markdown; extraction of numbers needs parsing |
| Official MD&A narrative, credit quality, segment results, financial statements | rts | Largest source; use `source_section` breadcrumbs to navigate |
| Conference and investor-day commentary | event_transcripts | Very thin coverage today |

Extraction pattern per kind: NUMBERS prefer benchmarking (exact, structured) then supp or rts tables. NARRATIVE and SENTIMENT prefer transcripts then rts. Always record which source an extracted value came from.

=== END OF PAGE 5 OF 16 ===
