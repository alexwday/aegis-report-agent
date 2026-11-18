# SOURCE: supplementary_financials -> "aegis-financial-supp-data" + "-embeddings"

PAGE 12 / 16 24.0px

## WHAT IT IS

Quarterly financial supplement spreadsheets (xlsx) for six Canadian banks. Same unified schema as page 11 (same 21 + 22 columns, same embedding types except no `document_summary`). Rows: data 995, embeddings 3,919; 24 files (6 banks x FY2025 Q4 to FY2026 Q3); `source_type`/`file_id` prefix = financial-supp.

## DIFFERENCES FROM INVESTOR SLIDES

- A chunk is a SPREADSHEET SHEET (or part of one), not a slide. `page_number` int = sheet index. `name` txt = sheet name (183 distinct; e.g. Page_21 or plain numbers). `chunk_id` looks like `sheet_24.1`: the `.N` suffix means big sheets are split into parts.
- `chunk_content` is a markdown table of the sheet with spreadsheet column letters (A, B, C...) and a leading Row number column. Values are as printed in the supplement (usually millions; units sit in header rows).
- `metrics` jsonb lists row labels on the sheet, sometimes with a suffix like `Net income | Segment: U.S. Banking`; it can be an empty list `[]`. `keywords` jsonb lists topic tags.
- To read a whole sheet you must fetch ALL parts that share the sheet number (Aegis does a 'gap fill' of missing sibling chunks `sheet_N.M`).

**NOTE:** Bank key is inconsistent in this table pair: 12 distinct `bank` values for 6 banks. Older files use `RY`, `BMO`, `BNS`, `CM`, `NA`, `TD`; newer files use `RY-CA`, `BMO-CA`, `CM-CA`, `NA-CA`, `BNS-CA`, `TD-CA` (same quarter can differ by file). Always match both forms, and normalise on read.

## RELATIONSHIPS AND COVERAGE

- Benchmarking rows with `source`='SuppPack' are structured numbers derived from these supplements (likely: verify). Use benchmarking for clean numbers, supp for line-item detail and footnotes.
- In `aegis_data_availability` the source appears as `supplementary` (385 rows) and `supplementary_financials` (12 rows). Treat both as this source.
- Only the six core Canadian banks; FY2025 Q4 to FY2026 Q3 loaded. Unified embeddings use model `text-embedding-3-large` (a few rows tagged `-eastus-dz`).

### A) sheets for a bank and period (both bank forms)

```sql
SELECT page_number, name, chunk_id, left(summary,80) AS summary
FROM "aegis-financial-supp-data"
WHERE bank IN ('RY','RY-CA') AND fiscal_year='2026' AND quarter='Q1'
ORDER BY page_number, chunk_id LIMIT 15
```

### B) find sheets by a line item

```sql
SELECT bank, quarter, name, chunk_id FROM "aegis-financial-supp-data"
WHERE bank IN ('TD','TD-CA') AND fiscal_year='2026'
  AND metrics::text ILIKE '%Net interest income%'
ORDER BY quarter, page_number
```

### C) read the table text of one chunk

```sql
SELECT left(chunk_content, 400) AS chunk_content
FROM "aegis-financial-supp-data"
WHERE bank IN ('RY','RY-CA') AND fiscal_year='2026' AND quarter='Q1' AND chunk_id='sheet_24.1'
```

=== END OF PAGE 12 OF 16 ===
