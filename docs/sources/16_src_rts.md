# SOURCE: rts -> rts_embedding (Reports to Shareholders)

PAGE 16 / 16 24.0px

## WHAT IT IS

Each bank's quarterly Report to Shareholders (MD&A plus financial statements, PDF converted to markdown). The largest table: 41,216 rows from 162 files; 6 banks; FY2020 to FY2026 Q3. Q4 holds about half the rows (annual-report content). Legacy single table, embedding inline.

## COLUMNS (14)

| Column | Type | Meaning |
|---|---|---|
| id | int PK identity | row id |
| created_at | tstz | load time |
| chunk_id | int NOT NULL | chunk number inside the file |
| page_no | int | PDF page: use for citation |
| bank | vch NOT NULL | canonical symbol |
| quarter | vch NOT NULL | 'Q1'..'Q4' |
| year | int NOT NULL | fiscal year as INTEGER (pillar3 uses text) |
| filename | vch NOT NULL | e.g. TD-CA Q2 2025.pdf.md |
| summary_title | txt | LLM one-sentence summary of the chunk |
| raw_text | txt | markdown text of the chunk; may include HTML tables |
| propositions | txt | atomic factual claims, stored as a brace-wrapped list in TEXT (not a real array); unused by Aegis but valuable for extraction |
| tables | txt | HTML `<table>` blocks from the chunk, with merged-cell attributes |
| source_section | txt | heading breadcrumb, e.g. [redacted for public repository: disclosure heading] |
| embedding | hv3072 NOT NULL | halfvec, cosine `<=>` |

## GUIDANCE

- btree indexes on `bank`, `year`, `quarter` and their combinations, plus `chunk_id`; no vector index. Always filter bank + year + quarter first.
- `source_section` breadcrumbs are the cheapest way to find a topic (credit quality, capital management, results by segment) before any vector search; match with ILIKE.
- Headings are not standardised across banks; wording differs. Section names for one bank change little year to year.
- Aegis returns top-10 per bank-period with no distance threshold; add one. A unified twin `aegis-rts-data/-embeddings` (925 / 19,590 rows, FY2026 Q1-Q2, `name` NULL) exists but is not read by Aegis.
- Citation = `filename` + `page_no`.

### A) find chunks by section heading

```sql
SELECT page_no, source_section, left(summary_title,80) AS summary
FROM rts_embedding
WHERE bank='TD-CA' AND year=2026 AND quarter='Q3' AND source_section ILIKE '%credit%'
ORDER BY page_no, chunk_id LIMIT 8
```

### B) read atomic claims of a chunk

```sql
SELECT page_no, left(propositions,250) AS claims
FROM rts_embedding
WHERE bank='RY-CA' AND year=2026 AND quarter='Q3' AND propositions IS NOT NULL
ORDER BY page_no LIMIT 2
```

### C) vector search (:qvec = query embedding)

```sql
SELECT page_no, source_section, embedding <=> :qvec AS dist
FROM rts_embedding
WHERE bank='RY-CA' AND year=2026 AND quarter='Q3'
ORDER BY dist LIMIT 5
```

## TOP-LEVEL HEADINGS IN SOURCE_SECTION (VALUE AND CHUNK COUNT)

[Redacted for public repository: disclosure headings.]

Headings are the first part of the breadcrumb before ' > '. Wording differs by bank and year.

=== END OF PAGE 16 OF 16 ===
