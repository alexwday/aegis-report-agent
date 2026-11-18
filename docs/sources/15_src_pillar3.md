# SOURCE: pillar3 -> pillar3_embedding

PAGE 15 / 16 24.0px

## WHAT IT IS

Basel Pillar 3 regulatory disclosure workbooks (xlsx), one workbook per bank per quarter. Each ROW is one SHEET rendered as a markdown table. 10,282 rows from 159 files; 6 Canadian banks; FY2020 Q1 to FY2026 Q3 (~440 sheets per quarter). Legacy schema, single table, embedding inline.

## COLUMNS (10)

| Column | Type | Meaning |
|---|---|---|
| id | int PK identity | row id |
| created_at | tstz | load time |
| sheet_name | vch NOT NULL | template code (OV1, KM1, KM2, TLAC1...) for standard templates; otherwise Page 13 or a bare number like 29 |
| bank | vch NOT NULL | canonical symbol, e.g. BMO-CA |
| quarter | vch NOT NULL | 'Q1'..'Q4' |
| year | vch NOT NULL | fiscal year AS TEXT: '2026' (compare with strings) |
| filename | vch NOT NULL | e.g. BMO-CA Q4 2020 Pillar 3.xlsx |
| raw_text | txt | markdown 'Sheet: Page 13' + table; header cells often read 'Unnamed: 0' (pandas artefact); very wide |
| source_section | vch | almost always NULL (9,834) or empty string (448): unused |
| embedding | hv3072 NOT NULL | halfvec, cosine `<=>` |

## GUIDANCE

- Coverage: 159 of 162 possible bank-quarters (6 banks x FY2020 Q1 to FY2026 Q3). Check `database_names` for `pillar3` before querying.
- Template-coded names (`OV1` RWA overview, `KM2`, `TLAC1`) exist for only SOME banks (3 of 6 in FY2026 Q3); most sheets are named by page number, which differs per bank. So `sheet_name` is NOT a reliable cross-bank key: locate sheets by vector search or by reading `raw_text`.
- Numbers inside `raw_text` are strings in a markdown grid: a downstream LLM or parser must extract them. No structured numeric table exists for pillar3.
- No similarity cut-off exists in Aegis: it returns top-3 per bank-period whatever the score. A new system should apply a distance threshold.
- Citation = `filename` + `sheet_name`. A unified twin `aegis-pillar3-data/-embeddings` (922 / 18,807 rows, FY2026 Q1-Q2, with `name` e.g. Cover, Index and LLM `summary`) exists but is not read by Aegis.

### A) one sheet by template code

```sql
SELECT filename, sheet_name, left(raw_text,120) AS text
FROM pillar3_embedding
WHERE bank='RY-CA' AND year='2026' AND quarter='Q3' AND sheet_name='OV1'
```

### B) which banks use template-coded sheets

```sql
SELECT bank, sheet_name FROM pillar3_embedding
WHERE year='2026' AND quarter='Q3' AND sheet_name IN ('OV1','KM2','TLAC1')
ORDER BY bank, sheet_name
```

### C) vector search (:qvec = query embedding)

```sql
SELECT bank, sheet_name, embedding <=> :qvec AS dist
FROM pillar3_embedding
WHERE year='2026' AND quarter='Q3' AND bank='TD-CA'
ORDER BY dist LIMIT 3
```

=== END OF PAGE 15 OF 16 ===
