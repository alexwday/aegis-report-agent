DO $contract$
DECLARE
    spec record;
    actual_columns text;
    actual_indexes text[];
BEGIN
    FOR spec IN
        WITH pairs AS (
            SELECT 'aegis-' || variant || '-' || suffix AS relation, columns, indexes
            FROM unnest(ARRAY['investor-slides', 'financial-supp', 'earnings-transcripts', 'event-transcripts',
                              'pillar3', 'rts']) AS variants(variant)
            CROSS JOIN (VALUES
                ('data', 'source_type fiscal_year quarter bank filename file_id file_type file_path file_hash page_number name summary chunk_id chunk_content keywords metrics keyword_embedding metric_embedding summary_embedding chunk_embedding created_at', ARRAY['P:file_id,chunk_id']),
                ('embeddings', 'embedding_id embedding_type embedding_scope source_type fiscal_year quarter bank filename file_id file_type file_path file_hash content_unit_id content_unit_ids chunk_id section_id embedding_text text_hash embedding embedding_model embedding_dimensions created_at', ARRAY['P:embedding_id'])
            ) AS shape(suffix, columns, indexes)
        ), legacy_transcripts AS (
            SELECT relation, 'id file_path filename date_last_modified title transcript_type event_id version_id fiscal_year fiscal_quarter institution_type institution_id ticker company_name section_name speaker_block_id qa_group_id classification_ids classification_names block_summary chunk_id chunk_tokens chunk_content chunk_paragraph_ids chunk_embedding created_at updated_at' AS columns,
                   ARRAY['P:id', 'N:company_name', 'N:event_id', 'N:fiscal_year,fiscal_quarter', 'N:ticker',
                         'N:ticker,fiscal_year,fiscal_quarter'] AS indexes
            FROM unnest(ARRAY['aegis_transcripts', 'aegis_event_transcripts']) AS relations(relation)
        )
        SELECT relation, columns, indexes FROM pairs
        UNION ALL SELECT relation, columns, indexes FROM legacy_transcripts
        UNION ALL
        SELECT relation, columns, indexes FROM (VALUES
            ('benchmarking_report', 'bank source ID Parameter Platform yr_Qtr Actual QoQ YoY 2Y 3Y 4Y 5Y BPS Report Units bank_symbol quarter fiscal_year updated_at filepath', ARRAY[]::text[]),
            ('aegis_data_availability', 'id bank_id bank_name bank_symbol bank_aliases bank_tags fiscal_year quarter database_names last_updated last_updated_by',
                 ARRAY['P:id', 'U:bank_id,fiscal_year,quarter', 'N:bank_id', 'N:bank_id,fiscal_year,quarter', 'N:fiscal_year,quarter']),
            ('kpi_metadata', 'id kpi_name description synonyms platforms unit higher_is_better key_drivers analyst_usage', ARRAY['P:id', 'U:kpi_name']),
            ('pillar3_embedding', 'id created_at sheet_name bank quarter year filename raw_text source_section embedding',
                 ARRAY['P:id', 'N:bank', 'N:bank,year', 'N:bank,year,quarter', 'N:quarter', 'N:year', 'N:year,quarter']),
            ('rts_embedding', 'id created_at chunk_id page_no bank quarter year filename summary_title raw_text propositions tables source_section embedding',
                 ARRAY['P:id', 'N:bank', 'N:bank,year', 'N:bank,year,quarter', 'N:chunk_id', 'N:quarter', 'N:year', 'N:year,quarter'])
        ) AS other(relation, columns, indexes)
    LOOP
        SELECT string_agg(column_name::text, ' ' ORDER BY ordinal_position) INTO actual_columns
        FROM information_schema.columns WHERE table_schema = 'public' AND table_name = spec.relation;
        IF actual_columns IS DISTINCT FROM spec.columns THEN
            RAISE EXCEPTION 'R-002 column ordinal mismatch for %: %', spec.relation, actual_columns;
        END IF;

        SELECT array_agg(description ORDER BY description) INTO actual_indexes
        FROM (
            SELECT (CASE WHEN i.indisprimary THEN 'P' WHEN i.indisunique THEN 'U' ELSE 'N' END) || ':' ||
                (SELECT string_agg(pg_get_indexdef(i.indexrelid, position, true), ',' ORDER BY position)
                 FROM generate_series(1, i.indnkeyatts) AS keys(position)) AS description
            FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid JOIN pg_am am ON am.oid = c.relam
            WHERE i.indrelid = format('public.%I', spec.relation)::regclass AND am.amname = 'btree'
        ) AS definitions;
        IF coalesce(actual_indexes, ARRAY[]::text[]) IS DISTINCT FROM
            ARRAY(SELECT definition FROM unnest(spec.indexes) AS definitions(definition) ORDER BY definition) THEN
            RAISE EXCEPTION 'R-002 index definition mismatch for %: %', spec.relation, actual_indexes;
        END IF;
    END LOOP;
END
$contract$;

SELECT 'R-002 exact column order and B-tree index definitions passed for all 19 relations';
