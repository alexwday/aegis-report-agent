# SOURCE: investor_presentation -> "aegis-investor-slides-data" + "-embeddings" (the UNIFIED schema)

PAGE 11 / 16 24.0px

## WHAT IT IS

Quarterly investor slide decks (PDF) for six Canadian banks, one chunk per slide. 1,266 chunks from 24 files (6 banks x FY2025 Q4 to FY2026 Q3). Table names contain hyphens: always double-quote them. This page defines the unified `-data` + `-embeddings` pattern that financial-supp (page 12) and the newer twins reuse.

## "AEGIS-INVESTOR-SLIDES-DATA": 1,266 ROWS, 21 COLUMNS

Document: `source_type` txt, `bank` txt (canonical symbol), `fiscal_year` txt, `quarter` txt, `filename` txt, `file_id` txt (e.g. investor-slides_2026_Q3_BNS-CA; join key), `file_type` txt, `file_path` txt (S3-relative key, e.g. [redacted for public repository: object key]), `file_hash` txt.

Chunk: `page_number` int, `name` txt (section label), `chunk_id` txt (e.g. page_34.1), `summary` txt (LLM, 1-3 sentences), `chunk_content` txt (markdown of the slide incl. tables), `keywords` jsonb (array of strings), `metrics` jsonb (array of strings), `created_at` tstz.

`keyword_embedding`, `metric_embedding`, `summary_embedding`, `chunk_embedding` v3072: ALWAYS NULL by design; vectors live in the embeddings table.

## "AEGIS-INVESTOR-SLIDES-EMBEDDINGS": 4,830 ROWS, 22 COLUMNS

`embedding_id` txt PK, `embedding_type` txt: `content` 1,266, `section_summary` 1,266, `keyword` 1,256, `metric` 1,018, `document_summary` 24. `embedding_scope` txt: content_unit / section / document. Denormalised copies: `source_type`, `fiscal_year`, `quarter`, `bank`, `filename`, `file_id`, `file_type`, `file_path`, `file_hash`.

Links: `chunk_id` txt, `content_unit_id` txt (join fallback: `COALESCE(chunk_id, content_unit_id)` = data.chunk_id), `content_unit_ids` jsonb (a section_summary row lists ALL chunk ids in that section), `section_id` txt. Text and vector: `embedding_text` txt, `text_hash` txt, `embedding` v3072, `embedding_model` txt, `embedding_dimensions` int (3072), `created_at` tstz NOT NULL.

## HOW TO USE IT

- Always filter by `bank`, `fiscal_year`, `quarter` (txt: '2026'). Join data to embeddings on `file_id` and the chunk id.
- Facets: search `content` for slide text, `keyword`/`metric` for tag matches, `section_summary` for topic then expand through `content_unit_ids`.
- Citation = `file_path` + `page_number`. Vectors are plain `<=>` cosine distance, lower = closer.

### A) list slides for a bank and period

```sql
SELECT page_number, name, left(summary,90) AS summary
FROM "aegis-investor-slides-data"
WHERE bank='BNS-CA' AND fiscal_year='2026' AND quarter='Q3'
ORDER BY page_number
```

### B) tag match on metrics

```sql
SELECT page_number, name FROM "aegis-investor-slides-data"
WHERE bank='RY-CA' AND fiscal_year='2026' AND metrics::text ILIKE '%CET1%'
```

### C) vector search (:qvec = query embedding)

```sql
SELECT d.page_number, d.name, e.embedding <=> :qvec AS dist
FROM "aegis-investor-slides-embeddings" e
JOIN "aegis-investor-slides-data" d
  ON d.file_id=e.file_id AND d.chunk_id=COALESCE(e.chunk_id,e.content_unit_id)
WHERE e.embedding_type='content' AND e.bank='RY-CA'
  AND e.fiscal_year='2026' AND e.quarter='Q3'
ORDER BY dist LIMIT 5
```

## MOST COMMON NAME (SECTION LABEL) VALUES ON SLIDES

[Redacted for public repository: disclosure headings.]

=== END OF PAGE 11 OF 16 ===
