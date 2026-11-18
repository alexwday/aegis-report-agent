# Briefing pack v1.1 corrections

[R-001 page 3](../collab/reviews/R-001.md#r-001-catalog-facts-q-002-q-003-and-pack-corrections-v11) governs these corrections to the original transcription.

- Page 10 — `yr_Qtr` is nullable, `fiscal_year` and `quarter` are required, and `updated_at` is a timestamp without time zone. Benchmarking has no key or index. The 17 benchmarking labels comprise 14 banks and 3 aggregates.
- Page 6 — RBC-US is included in the 14 benchmarking banks. Three aggregate labels have NULL symbols.
- Page 5 — Availability is unique on `(bank_id, fiscal_year, quarter)`. Alias and tag arrays can be NULL in individual periods.
- Page 11 — Unified data tables use primary key `(file_id, chunk_id)`. Unified embedding tables use primary key `embedding_id`.
