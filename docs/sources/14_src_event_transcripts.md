# SOURCE: event_transcripts -> aegis_event_transcripts (conferences, investor days)

PAGE 14 / 16 24.0px

## WHAT IT IS

Transcripts of NON-earnings events (investor days, industry conferences). Column-for-column IDENTICAL to `aegis_transcripts` (page 13: same 27 columns, types, meanings, indexes and reading order). Separate table so earnings and event content never mix. 88 rows only.

## DIFFERENCES

- `title` = EVENT name, and is the grouping key (earnings calls use 'Qn YYYY Earnings Call').
- Today: 3 files, all FY2025 Q2: JPM-US, MS-US and WFC-US at Morgan Stanley U.S. Financials conferences. `transcript_type` = Corrected only. institution_type = US banks.
- Calendar of upcoming events is a separate table `aegis_calendar_events` (loaded from Snowflake by process O7); it describes events, not their text.
- Aegis tags this source `event_transcripts` in availability (3 bank-period rows only).

**NOTE:** Coverage is tiny and probably incomplete. A unified twin `aegis-event-transcripts-data` (844 rows) and `-embeddings` (9,649 rows) exists with FY2026 Q1-Q2 content for the six Canadian banks (RY, BMO, CM, NA, BNS, TD), but Aegis does not read it and its content type is not verified. Inspect before relying on it.

## WHY IT MATTERS FOR A REPORT BUILDER

- Event content is the place for forward-looking and strategy commentary outside the earnings cycle.
- Because coverage is thin and uneven, a report section that uses it must handle 'no data for this bank and period' without failing.
- Always check `aegis_data_availability.database_names` for `event_transcripts` before querying.

### A) what exists

```sql
SELECT title, ticker, fiscal_year, fiscal_quarter, section_name, count(*) AS chunks
FROM aegis_event_transcripts
GROUP BY 1,2,3,4,5 ORDER BY 2,5
```

### B) read one event's Q&A in order

```sql
SELECT qa_group_id, speaker_block_id, chunk_id, left(chunk_content,100) AS text
FROM aegis_event_transcripts
WHERE ticker='JPM-US' AND section_name='Q&A'
ORDER BY qa_group_id, speaker_block_id, chunk_id LIMIT 8
```

### C) vector search (:qvec = query embedding)

```sql
SELECT ticker, title, chunk_embedding <=> :qvec AS dist
FROM aegis_event_transcripts
WHERE fiscal_year=2025 AND fiscal_quarter='Q2'
ORDER BY dist LIMIT 5
```

=== END OF PAGE 14 OF 16 ===
