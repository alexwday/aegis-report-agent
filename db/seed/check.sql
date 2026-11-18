DO $smoke$
DECLARE
    source record;
    column_count integer;
    has_rows boolean;
BEGIN
    FOR source IN
        SELECT * FROM (VALUES
            ('aegis_data_availability', 11), ('benchmarking_report', 21), ('kpi_metadata', 9),
            ('aegis_transcripts', 27), ('aegis_event_transcripts', 27), ('pillar3_embedding', 10), ('rts_embedding', 14)
        ) AS legacy(table_name, expected_columns)
        UNION ALL
        SELECT 'aegis-' || variant || '-' || suffix, expected_columns
        FROM unnest(ARRAY['investor-slides', 'financial-supp', 'earnings-transcripts', 'event-transcripts', 'pillar3', 'rts']) AS variants(variant)
        CROSS JOIN (VALUES ('data', 21), ('embeddings', 22)) AS pair(suffix, expected_columns)
    LOOP
        SELECT count(*) INTO column_count FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = source.table_name;
        EXECUTE format('SELECT EXISTS (SELECT FROM public.%I)', source.table_name) INTO has_rows;
        IF column_count <> source.expected_columns OR NOT has_rows THEN
            RAISE EXCEPTION 'Unexpected shape or empty fixture: %', source.table_name;
        END IF;
    END LOOP;

    IF (SELECT count(*) FROM "aegis-financial-supp-data" d
        JOIN "aegis-financial-supp-embeddings" e USING (file_id)
        WHERE d.chunk_id = coalesce(e.chunk_id, e.content_unit_id)
          AND d.bank IN ('SYN1', 'SYN1-CA') AND d.fiscal_year = '2090' AND d.quarter = 'Q2'
          AND vector_dims(e.embedding) = 3072) <> 2 THEN
        RAISE EXCEPTION 'Supplement aliases, sibling chunks, or vector join failed';
    END IF;

    IF NOT EXISTS (
        SELECT FROM benchmarking_report b
        WHERE b.bank_symbol = 'SYN1-CA' AND b."yr_Qtr" = '2090_Q3'
          AND b."Parameter" = 'Net Income' AND b."Actual" IS NOT NULL
    ) OR NOT EXISTS (
        SELECT FROM benchmarking_report b WHERE b.bank_symbol = 'SYN2-CA'
          AND b."yr_Qtr" = '2090_Q3' AND b."Parameter" = 'Net Income' AND b."Actual" IS NULL
    ) THEN
        RAISE EXCEPTION 'Fixture missing benchmark row';
    END IF;

    IF NOT EXISTS (
        SELECT FROM aegis_transcripts t
        JOIN aegis_transcripts other USING (event_id)
        WHERE t.transcript_type = 'Corrected' AND other.transcript_type = 'Raw'
    ) THEN
        RAISE EXCEPTION 'Fixture missing overlapping transcript versions';
    END IF;

    IF NOT EXISTS (
        SELECT FROM pillar3_embedding p JOIN rts_embedding r USING (bank)
        WHERE p.year = '2090' AND r.year = 2090 AND p.embedding <=> r.embedding = 0
    ) THEN
        RAISE EXCEPTION 'Half-vector cosine search failed';
    END IF;
END
$smoke$;

SELECT 'PostgreSQL ' || current_setting('server_version') || ', pgvector ' || extversion
FROM pg_extension WHERE extname = 'vector';
SELECT '19 populated source fixture tables with expected column counts';
SELECT 'Unified joins, quoted KPIs, transcript version overlap, and halfvec cosine passed';

DO $catalog$
DECLARE
    relation text;
BEGIN
    IF EXISTS (SELECT FROM pg_index WHERE indrelid = 'public.benchmarking_report'::regclass) THEN
        RAISE EXCEPTION 'Benchmarking must have no index or key';
    END IF;

    IF (SELECT count(*) FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'benchmarking_report'
          AND ((column_name = 'yr_Qtr' AND is_nullable = 'YES' AND character_maximum_length = 500)
            OR (column_name = 'quarter' AND is_nullable = 'NO' AND character_maximum_length = 10)
            OR (column_name = 'fiscal_year' AND is_nullable = 'NO')
            OR (column_name = 'updated_at' AND data_type = 'timestamp without time zone' AND column_default = 'now()'))) <> 4 THEN
        RAISE EXCEPTION 'Benchmarking type, nullability, or default mismatch';
    END IF;

    IF EXISTS (
        SELECT FROM pg_class idx JOIN pg_am am ON am.oid = idx.relam
        JOIN pg_namespace ns ON ns.oid = idx.relnamespace
        WHERE ns.nspname = 'public' AND am.amname IN ('ivfflat', 'hnsw')
    ) THEN
        RAISE EXCEPTION 'Unexpected ANN index in fixture';
    END IF;

    FOR relation IN SELECT tablename FROM pg_tables
        WHERE schemaname = 'public' AND tablename LIKE 'aegis-%-data'
    LOOP
        IF NOT EXISTS (
            SELECT FROM pg_constraint
            WHERE conrelid = format('public.%I', relation)::regclass
              AND contype = 'p' AND pg_get_constraintdef(oid) = 'PRIMARY KEY (file_id, chunk_id)'
        ) OR (SELECT array_agg(column_name::text ORDER BY ordinal_position)
              FROM information_schema.columns
              WHERE table_schema = 'public' AND table_name = relation AND ordinal_position <= 5)
             <> ARRAY['source_type', 'fiscal_year', 'quarter', 'bank', 'filename'] THEN
            RAISE EXCEPTION 'Unified data key or confirmed column order mismatch: %', relation;
        END IF;
    END LOOP;

    IF (SELECT column_default FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'aegis_event_transcripts' AND column_name = 'id')
       NOT LIKE '%aegis_event_transcripts_id_seq%' THEN
        RAISE EXCEPTION 'Event transcript serial sequence must be independent';
    END IF;
END
$catalog$;

SELECT 'R-001 catalog checks passed for confirmed keys, types, defaults, and ordinals';
