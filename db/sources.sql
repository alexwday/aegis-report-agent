-- Disposable local source fixture v3 (R-002). Production adapters use SELECT-only credentials.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE public.aegis_data_availability (
    id serial PRIMARY KEY,
    bank_id integer NOT NULL,
    bank_name varchar(100) NOT NULL,
    bank_symbol varchar(10) NOT NULL,
    bank_aliases text[],
    bank_tags text[],
    fiscal_year integer NOT NULL,
    quarter varchar(2) NOT NULL,
    database_names text[],
    last_updated timestamp DEFAULT now(),
    last_updated_by varchar(100),
    UNIQUE (bank_id, fiscal_year, quarter)
);

CREATE INDEX ON public.aegis_data_availability (bank_id);
CREATE INDEX ON public.aegis_data_availability (bank_id, fiscal_year, quarter);
CREATE INDEX ON public.aegis_data_availability (fiscal_year, quarter);

CREATE TABLE public.benchmarking_report (
    bank varchar(500),
    source varchar(500),
    "ID" varchar(500),
    "Parameter" varchar(500),
    "Platform" varchar(500),
    "yr_Qtr" varchar(500),
    "Actual" numeric,
    "QoQ" numeric,
    "YoY" numeric,
    "2Y" numeric,
    "3Y" numeric,
    "4Y" numeric,
    "5Y" numeric,
    "BPS" varchar(500),
    "Report" varchar(500),
    "Units" varchar(500),
    bank_symbol varchar(500),
    quarter varchar(10) NOT NULL,
    fiscal_year integer NOT NULL,
    updated_at timestamp DEFAULT now(),
    filepath text
);

CREATE TABLE public.kpi_metadata (
    id integer PRIMARY KEY,
    kpi_name text UNIQUE,
    description text,
    synonyms text[],
    platforms text[],
    unit text,
    higher_is_better boolean,
    key_drivers text,
    analyst_usage text
);

CREATE TABLE public."aegis-investor-slides-data" (
    source_type text NOT NULL,
    fiscal_year text NOT NULL,
    quarter text NOT NULL,
    bank text NOT NULL,
    filename text NOT NULL,
    file_id text NOT NULL,
    file_type text NOT NULL,
    file_path text NOT NULL,
    file_hash text NOT NULL,
    page_number integer,
    name text,
    summary text,
    chunk_id text NOT NULL,
    chunk_content text,
    keywords jsonb NOT NULL DEFAULT '[]'::jsonb,
    metrics jsonb NOT NULL DEFAULT '[]'::jsonb,
    keyword_embedding vector(3072),
    metric_embedding vector(3072),
    summary_embedding vector(3072),
    chunk_embedding vector(3072),
    created_at timestamptz,
    PRIMARY KEY (file_id, chunk_id)
);

CREATE TABLE public."aegis-investor-slides-embeddings" (
    embedding_id text PRIMARY KEY,
    embedding_type text NOT NULL,
    embedding_scope text NOT NULL,
    source_type text NOT NULL,
    fiscal_year text NOT NULL,
    quarter text NOT NULL,
    bank text NOT NULL,
    filename text NOT NULL,
    file_id text NOT NULL,
    file_type text NOT NULL,
    file_path text NOT NULL,
    file_hash text NOT NULL,
    content_unit_id text,
    content_unit_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    chunk_id text,
    section_id text,
    embedding_text text NOT NULL,
    text_hash text,
    embedding vector(3072),
    embedding_model text NOT NULL,
    embedding_dimensions integer NOT NULL,
    created_at timestamptz NOT NULL
);

CREATE TABLE public."aegis-financial-supp-data"
    (LIKE public."aegis-investor-slides-data" INCLUDING ALL);
CREATE TABLE public."aegis-financial-supp-embeddings"
    (LIKE public."aegis-investor-slides-embeddings" INCLUDING ALL);
ALTER TABLE public."aegis-financial-supp-embeddings" ALTER COLUMN embedding SET NOT NULL;

-- The pack describes these as twins. Confirm parity before enabling real reads.
CREATE TABLE public."aegis-earnings-transcripts-data"
    (LIKE public."aegis-investor-slides-data" INCLUDING ALL);
CREATE TABLE public."aegis-earnings-transcripts-embeddings"
    (LIKE public."aegis-investor-slides-embeddings" INCLUDING ALL);
CREATE TABLE public."aegis-event-transcripts-data"
    (LIKE public."aegis-investor-slides-data" INCLUDING ALL);
CREATE TABLE public."aegis-event-transcripts-embeddings"
    (LIKE public."aegis-investor-slides-embeddings" INCLUDING ALL);
CREATE TABLE public."aegis-pillar3-data"
    (LIKE public."aegis-investor-slides-data" INCLUDING ALL);
CREATE TABLE public."aegis-pillar3-embeddings"
    (LIKE public."aegis-investor-slides-embeddings" INCLUDING ALL);
CREATE TABLE public."aegis-rts-data"
    (LIKE public."aegis-investor-slides-data" INCLUDING ALL);
CREATE TABLE public."aegis-rts-embeddings"
    (LIKE public."aegis-investor-slides-embeddings" INCLUDING ALL);

CREATE TABLE public.aegis_transcripts (
    id serial PRIMARY KEY,
    file_path text,
    filename text,
    date_last_modified timestamptz,
    title text,
    transcript_type text,
    event_id text,
    version_id text,
    fiscal_year integer NOT NULL,
    fiscal_quarter text NOT NULL,
    institution_type text,
    institution_id text,
    ticker text NOT NULL,
    company_name text,
    section_name text,
    speaker_block_id integer,
    qa_group_id integer,
    classification_ids text[],
    classification_names text[],
    block_summary text,
    chunk_id integer,
    chunk_tokens integer,
    chunk_content text,
    chunk_paragraph_ids text[],
    chunk_embedding vector(3072),
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);

CREATE INDEX ON public.aegis_transcripts (ticker);
CREATE INDEX ON public.aegis_transcripts (ticker, fiscal_year, fiscal_quarter);
CREATE INDEX ON public.aegis_transcripts (fiscal_year, fiscal_quarter);
CREATE INDEX ON public.aegis_transcripts (company_name);
CREATE INDEX ON public.aegis_transcripts (event_id);

CREATE TABLE public.aegis_event_transcripts
    (LIKE public.aegis_transcripts INCLUDING ALL);
CREATE SEQUENCE public.aegis_event_transcripts_id_seq AS integer
    OWNED BY public.aegis_event_transcripts.id;
ALTER TABLE public.aegis_event_transcripts ALTER COLUMN id
    SET DEFAULT nextval('public.aegis_event_transcripts_id_seq'::regclass);

CREATE TABLE public.pillar3_embedding (
    id integer GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    created_at timestamptz DEFAULT now(),
    sheet_name varchar(100) NOT NULL,
    bank varchar(100) NOT NULL,
    quarter varchar(10) NOT NULL,
    year varchar(50) NOT NULL,
    filename varchar(255) NOT NULL,
    raw_text text,
    source_section varchar(500),
    embedding halfvec(3072) NOT NULL
);

CREATE INDEX ON public.pillar3_embedding (bank);
CREATE INDEX ON public.pillar3_embedding (bank, year);
CREATE INDEX ON public.pillar3_embedding (bank, year, quarter);
CREATE INDEX ON public.pillar3_embedding (quarter);
CREATE INDEX ON public.pillar3_embedding (year);
CREATE INDEX ON public.pillar3_embedding (year, quarter);

CREATE TABLE public.rts_embedding (
    id integer GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    created_at timestamptz DEFAULT now(),
    chunk_id integer NOT NULL,
    page_no integer,
    bank varchar(100) NOT NULL,
    quarter varchar(10) NOT NULL,
    year integer NOT NULL,
    filename varchar(255) NOT NULL,
    summary_title text,
    raw_text text,
    propositions text,
    tables text,
    source_section text,
    embedding halfvec(3072) NOT NULL
);

CREATE INDEX ON public.rts_embedding (bank);
CREATE INDEX ON public.rts_embedding (bank, year);
CREATE INDEX ON public.rts_embedding (year);
CREATE INDEX ON public.rts_embedding (quarter);
CREATE INDEX ON public.rts_embedding (year, quarter);
CREATE INDEX ON public.rts_embedding (bank, year, quarter);
CREATE INDEX ON public.rts_embedding (chunk_id);
