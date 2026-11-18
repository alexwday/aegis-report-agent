-- Load once into a freshly initialized fixture DB. Symbols, values, and files are fabricated.
CREATE TEMP TABLE seed_bank (id integer, symbol text, short text, name text);
INSERT INTO seed_bank VALUES
    (901, 'SYN1-CA', 'SYN1', 'Fixture Bank One'),
    (902, 'SYN2-CA', 'SYN2', 'Fixture Bank Two'),
    (903, 'SYN3-US', 'SYN3', 'Fixture Bank Three');

-- Deterministic, orthogonal unit vectors for exact-match and low-relevance test cases.
CREATE TEMP TABLE seed_vector AS
SELECT id, ARRAY(SELECT CASE WHEN coordinate = id THEN 1.0 ELSE 0.0 END
                 FROM generate_series(1, 3072) AS coord(coordinate)
                 ORDER BY coordinate)::vector(3072) AS embedding
FROM generate_series(1, 2) AS kind(id);

INSERT INTO public.aegis_data_availability
    (id, bank_id, bank_name, bank_symbol, bank_aliases, bank_tags, fiscal_year, quarter,
     database_names, last_updated, last_updated_by)
SELECT 10 * bank.id + period.number, bank.id, bank.name, bank.symbol,
       CASE WHEN period.number <> 3 THEN ARRAY[bank.short, bank.name] END,
       CASE WHEN period.number <> 3 THEN ARRAY['synthetic'] END, 2090, 'Q' || period.number,
       CASE
           WHEN bank.id = 903 THEN ARRAY['event_transcripts', 'supplementary']
           WHEN period.number = 3 THEN ARRAY['transcripts', 'rts', 'pillar3', 'investor_presentation', 'supplementary_financials']
           WHEN period.number = 2 THEN ARRAY['supplementary', 'investor_relations_benchmarking']
           ELSE ARRAY['rts']
       END,
       timestamp '2090-10-01 00:00:00', 'fixture-loader'
FROM seed_bank bank CROSS JOIN generate_series(1, 3) AS period(number);

INSERT INTO public.kpi_metadata
    (id, kpi_name, description, synonyms, platforms, unit, higher_is_better, key_drivers, analyst_usage)
VALUES
    (801, 'Net Income', 'Synthetic profit series', ARRAY['Fixture profit'], ARRAY['Enterprise'], 'millions', true, 'Synthetic activity', 'Trend'),
    (802, 'Efficiency Ratio', 'Synthetic expense ratio', ARRAY['Fixture efficiency'], ARRAY['Enterprise', 'Capital Markets'], '%', false, 'Synthetic costs', 'Ranking');

INSERT INTO public.benchmarking_report
    (bank, bank_symbol, "Parameter", "Platform", "ID", "yr_Qtr", fiscal_year,
     quarter, "Actual", "QoQ", "YoY", source, "Units", "BPS", updated_at, filepath)
SELECT bank.short, bank.symbol, metric.kpi_name, 'Enterprise', 'fixture-' || metric.id,
       '2090_Q' || period.number, 2090, 'Q' || period.number,
       CASE
           WHEN bank.id = 902 AND metric.id = 801 AND period.number = 3 THEN NULL
           WHEN metric.id = 801 THEN 410 + 3 * (bank.id - 900) + 11 * period.number
           ELSE 47 + (bank.id - 900) - 0.4 * period.number
       END,
       CASE WHEN period.number = 3 THEN CASE metric.id WHEN 802 THEN -40 ELSE 2.54 END END,
       NULL, 'Calculated', NULL, CASE WHEN metric.id = 802 THEN 'Yes' END, timestamp '2090-10-01 00:00:00',
       'synthetic/benchmarking.csv'
FROM seed_bank bank CROSS JOIN public.kpi_metadata metric
CROSS JOIN generate_series(1, 3) AS period(number);

INSERT INTO public.benchmarking_report
    (bank, "Parameter", "Platform", "yr_Qtr", fiscal_year, quarter, "Actual", source, filepath)
VALUES ('Fixture peers', 'Net Income', 'Enterprise', '2090_Q3', 2090, 'Q3', 811, 'Calculated', 'synthetic/benchmarking.csv');

INSERT INTO public.benchmarking_report
    (bank, bank_symbol, "Parameter", "Platform", fiscal_year, quarter, "Actual", "QoQ", "Units", filepath)
VALUES
    ('SYN3', 'SYN3-US', 'Efficiency Ratio', 'Capital Markets', 2090, 'Q3', 47.77, -34, '%', 'synthetic/benchmarking.csv'),
    ('SYN1', 'SYN1-CA', 'Net Income', 'Enterprise', 2088, 'Q3', 400, NULL, 'fixture invalid unit', 'synthetic/benchmarking.csv');

-- Same-quarter comparison fixtures. The 2088 Q3 value is explicit above.
INSERT INTO public.benchmarking_report
    (bank, bank_symbol, "Parameter", "Platform", fiscal_year, quarter, "Actual", updated_at, filepath)
SELECT 'SYN1', 'SYN1-CA', 'Net Income', 'Enterprise', year_number, quarter_label,
       380 + (year_number - 2087) * 15 + CASE WHEN quarter_label = 'Q3' THEN 5 ELSE 0 END,
       timestamp '2090-10-01 00:00:00', 'synthetic/benchmarking.csv'
FROM generate_series(2087, 2089) AS history(year_number)
CROSS JOIN (VALUES ('Q2'), ('Q3')) AS quarters(quarter_label)
WHERE (year_number, quarter_label) <> (2088, 'Q3');

-- Real identifiers are excluded; the synthetic relative paths exercise the documented naming pattern.


INSERT INTO public.aegis_transcripts
    (file_path, filename, date_last_modified, title, transcript_type, event_id, version_id,
     institution_type, institution_id, ticker, company_name, fiscal_year, fiscal_quarter,
     section_name, speaker_block_id, qa_group_id, chunk_id, chunk_tokens, chunk_paragraph_ids,
     chunk_content, block_summary, classification_ids, classification_names, chunk_embedding, created_at, updated_at)
SELECT 'synthetic/calls/' || version.number || '.xml',
       bank.symbol || '_Q3_2090_' || version.kind || '_991_' || version.number || '.xml',
       timestamptz '2090-08-10 00:00:00+00', 'Fixture Q3 2090 Earnings Call',
       version.kind, '991', version.number,
       'Canadian_Banks', bank.id::text, bank.symbol, bank.name, 2090, 'Q3',
       chunk.section, chunk.block, chunk.qa, chunk.position, 24, ARRAY['p-' || chunk.position],
       chunk.body, 'Fictional discussion for adapter tests.', ARRAY['fixture-margin'],
       ARRAY[chunk.topic], vectors.embedding,
       timestamptz '2090-08-10 00:00:00+00', timestamptz '2090-08-10 00:00:00+00'
FROM seed_bank bank
CROSS JOIN (VALUES ('Raw', '30'), ('Corrected', '2'), ('Corrected', '11')) AS version(kind, number)
CROSS JOIN (VALUES
    ('MANAGEMENT DISCUSSION SECTION', 1, NULL::integer, 1, '[Synthetic Speaker, CFO, Fixture Bank] Margins widened in the fixture.', 'Net Interest Income & Margins'),
    ('Q&A', 2, 1, 1, '[Synthetic Analyst, Analyst, Fixture Research] What drove the change?', 'Funding costs'),
    ('Q&A', 3, 1, 1, '[Synthetic Speaker, CFO, Fixture Bank] Fictional funding costs fell.', 'Funding costs')
) AS chunk(section, block, qa, position, body, topic)
JOIN seed_vector vectors ON vectors.id = 1
WHERE bank.id = 901;

INSERT INTO public.aegis_event_transcripts
    (filename, title, transcript_type, event_id, version_id, institution_type, institution_id,
     ticker, company_name, fiscal_year, fiscal_quarter, section_name, speaker_block_id,
     qa_group_id, chunk_id, chunk_content, chunk_embedding)
SELECT 'synthetic-event.xml', 'Fixture Strategy Forum', 'Corrected', 'fixture-event-1', '1',
       'US banks', bank.id::text, bank.symbol, bank.name, 2090, 'Q2', 'Q&A', 1, 1, 1,
       '[Synthetic Speaker, CFO, Fixture Bank] The fictional expansion is in planning.',
       vectors.embedding
FROM seed_bank bank JOIN seed_vector vectors ON vectors.id = 2
WHERE bank.id = 903;

INSERT INTO public.pillar3_embedding (created_at, sheet_name, bank, quarter, year, filename, raw_text, embedding)
SELECT timestamptz '2090-08-10 00:00:00+00', CASE bank.id WHEN 901 THEN 'OV1' ELSE 'Page 13' END,
       bank.symbol, 'Q3', '2090', bank.short || '-fixture-pillar3.xlsx',
       E'| Metric | Fixture millions |\n|---|---:|\n| Risk-weighted assets | 18240 |', vectors.embedding::halfvec(3072)
FROM seed_bank bank JOIN seed_vector vectors ON vectors.id = 1
WHERE bank.id IN (901, 902);

INSERT INTO public.rts_embedding
    (created_at, chunk_id, page_no, bank, quarter, year, filename, summary_title,
     raw_text, propositions, tables, source_section, embedding)
SELECT timestamptz '2090-08-10 00:00:00+00', 1, 9, bank.symbol, 'Q3', 2090,
       bank.short || '-fixture-rts.pdf.md', 'Synthetic credit quality',
       'The fixture provision was 47 million.', '{"The fixture provision was 47 million."}',
       '<table><tr><td>Fixture provision</td><td>47</td></tr></table>',
       'Fixture results > Credit quality', vectors.embedding::halfvec(3072)
FROM seed_bank bank JOIN seed_vector vectors ON vectors.id = 1
WHERE bank.id IN (901, 902);

-- Each unified pair shares one documented shape. The local variants exercise alias and join fallbacks.
DO $seed_unified$
DECLARE
    source record;
BEGIN
    FOR source IN
        SELECT * FROM (VALUES
            ('investor-slides', 'SYN1-CA', 'Q3', 'pdf', 3, 'Fixture capital position', 1),
            ('financial-supp', 'SYN1', 'Q2', 'xlsx', 24, 'Fixture income statement', 2),
            ('earnings-transcripts', 'SYN1-CA', 'Q2', 'xml', 1, 'Fixture earnings discussion', 2),
            ('event-transcripts', 'SYN1-CA', 'Q2', 'xml', 2, 'Fixture unverified event variant', 1),
            ('pillar3', 'SYN1-CA', 'Q2', 'xlsx', 5, 'Fixture ratios', 1),
            ('rts', 'SYN1-CA', 'Q2', 'pdf', 8, NULL, 1)
        ) AS fixtures(kind, bank, quarter, file_type, page, label, parts)
    LOOP
        EXECUTE format($data$
            INSERT INTO public.%I
                (source_type, bank, fiscal_year, quarter, filename, file_id, file_type,
                 file_path, file_hash, page_number, name, chunk_id, summary, chunk_content,
                 keywords, metrics, created_at)
            SELECT $1, $2, '2090', $3,
                   CASE WHEN $1 = 'earnings-transcripts' THEN 'SYN1-CA_Q2_2090_Corrected_990_1.xml'
                        ELSE $1 || '-fixture.' || $4 END,
                   $1 || '_2090_' || $3 || '_' || $2, $4,
                   'synthetic/' || $1 || '-fixture.' || $4, md5($1 || '-fixture'), CASE WHEN $1 = 'earnings-transcripts' THEN 3 - part ELSE $5 END, $6,
                   CASE WHEN $1 = 'financial-supp' THEN 'sheet_' ELSE 'page_' END || $5 || '.' || part,
                   'Fabricated evidence, part ' || part,
                   CASE WHEN $1 = 'financial-supp'
                        THEN E'| Row | A | B |\n|---|---|---:|\n| ' || (part + 1) ||
                             ' | Synthetic income line | ' || (120 + 13 * part) || ' |'
                        WHEN $1 = 'earnings-transcripts' AND part = 1 THEN 'Synthetic net interest margins were steady.'
                        WHEN $1 = 'earnings-transcripts' THEN 'Synthetic funding costs rose during the quarter.'
                        WHEN $1 = 'investor-slides' THEN 'Synthetic funding costs fell in the sample presentation.'
                        ELSE 'Synthetic disclosure for fixture testing.'
                   END,
                   CASE WHEN $1 = 'earnings-transcripts' AND part = 1 THEN '["Net Interest Income & Margins"]'::jsonb
                        WHEN $1 = 'earnings-transcripts' THEN '["Funding costs"]'::jsonb
                        ELSE '["fixture", "capital"]'::jsonb END,
                   '["Net Interest Income", "CET1 Ratio"]'::jsonb,
                   timestamptz '2090-08-10 00:00:00+00'
            FROM generate_series(1, $7) AS parts(part)
        $data$, 'aegis-' || source.kind || '-data')
        USING source.kind, source.bank, source.quarter, source.file_type, source.page, source.label, source.parts;

        EXECUTE format($embeddings$
            INSERT INTO public.%I
                (embedding_id, embedding_type, embedding_scope, source_type, fiscal_year, quarter,
                 bank, filename, file_id, file_type, file_path, file_hash, chunk_id, content_unit_id,
                 content_unit_ids, section_id, embedding_text, text_hash, embedding, embedding_model,
                 embedding_dimensions, created_at)
            SELECT d.file_id || ':' || d.chunk_id, 'content', 'content_unit', d.source_type,
                   d.fiscal_year, d.quarter, d.bank, d.filename, d.file_id, d.file_type, d.file_path, d.file_hash,
                   NULL, d.chunk_id, '[]'::jsonb, 'fixture-section', d.chunk_content, md5(d.chunk_content),
                   vectors.embedding, 'text-embedding-3-large', 3072, d.created_at
            FROM public.%I d CROSS JOIN seed_vector vectors
            WHERE vectors.id = 1
        $embeddings$, 'aegis-' || source.kind || '-embeddings', 'aegis-' || source.kind || '-data');
    END LOOP;
END
$seed_unified$;

INSERT INTO public."aegis-investor-slides-embeddings"
    (embedding_id, embedding_type, embedding_scope, source_type, fiscal_year, quarter,
     bank, filename, file_id, file_type, file_path, file_hash, content_unit_ids, section_id,
     embedding_text, text_hash, embedding, embedding_model, embedding_dimensions, created_at)
SELECT d.file_id || ':summary', 'section_summary', 'section', d.source_type, d.fiscal_year,
       d.quarter, d.bank, d.filename, d.file_id, d.file_type, d.file_path, d.file_hash,
       jsonb_build_array(d.chunk_id), 'fixture-section', d.summary, md5(d.summary),
       vectors.embedding, 'text-embedding-3-large', 3072, d.created_at
FROM public."aegis-investor-slides-data" d CROSS JOIN seed_vector vectors
WHERE vectors.id = 2;
