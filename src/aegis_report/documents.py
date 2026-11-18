from .config import Settings
from .models import SourceName
from .sources import (
    BenchmarkingSource,
    Citation,
    DisabledSource,
    EarningsSource,
    Passage,
    Probe,
    Readiness,
    Scope,
    SourceAdapter,
    SourceConnection,
    opaque_id,
    vector_literal,
)
from .topics import search_terms


class SlideSource:
    def __init__(self, threshold: float):
        self.threshold = threshold

    def probe(self, conn: SourceConnection, scope: Scope) -> Probe:
        rows = conn.execute("""
            SELECT file_id, file_hash, count(*) AS chunks, max(created_at) AS latest,
                   count(*) FILTER (WHERE page_number IS NOT NULL AND chunk_content <> '') AS usable
            FROM public."aegis-investor-slides-data"
            WHERE bank = %s AND fiscal_year = %s AND quarter = %s
            GROUP BY file_id, file_hash ORDER BY file_id, file_hash
        """, (scope.bank.symbol, str(scope.period.year), f"Q{scope.period.quarter}")).fetchall()
        return document_probe(rows, "unified")

    def search(self, conn: SourceConnection, scope: Scope, vector: list[float] | None = None) -> list[Passage]:
        terms = list(search_terms(scope.topics, scope.terms))
        query = vector_literal(vector)
        rows = conn.execute("""
            WITH terms AS (
                SELECT phraseto_tsquery('english', phrase) AS term FROM unnest(%s::text[]) AS phrases(phrase)
            ), candidates AS (
                SELECT d.file_path, d.file_hash, d.chunk_id, d.page_number, d.name, left(d.chunk_content, 16000) AS body,
                       setweight(to_tsvector('english', coalesce(d.name, '')), 'A') ||
                       setweight(to_tsvector('english', d.chunk_content), 'D') AS lexemes,
                       CASE WHEN %s::text IS NOT NULL THEN (
                           SELECT min(e.embedding OPERATOR(public.<=>) %s::public.vector(3072))
                           FROM public."aegis-investor-slides-embeddings" e
                           WHERE e.file_id = d.file_id AND e.file_hash = d.file_hash
                             AND coalesce(e.chunk_id, e.content_unit_id) = d.chunk_id
                             AND e.embedding_type = 'content' AND e.embedding_dimensions = 3072
                             AND e.embedding_model IN ('text-embedding-3-large', 'text-embedding-3-large-eastus-dz')
                       ) END AS distance
                FROM public."aegis-investor-slides-data" d
                WHERE d.bank = %s AND d.fiscal_year = %s AND d.quarter = %s
                  AND d.page_number IS NOT NULL AND d.chunk_content <> ''
            ), ranked AS (
                SELECT file_path, file_hash, chunk_id, page_number, name, body, distance,
                       coalesce((SELECT sum(ts_rank_cd(lexemes, term, 34)) FROM terms
                                 WHERE lexemes @@ term), 0) AS rank
                FROM candidates
            )
            SELECT file_path, file_hash, chunk_id, page_number, name, body, distance, rank
            FROM ranked
            WHERE rank > 0 OR distance <= %s OR %s
            ORDER BY rank + CASE WHEN distance IS NULL THEN 0 ELSE greatest(0, %s - distance) * 0.05 END DESC,
                     rank DESC, distance NULLS LAST, file_path, page_number, chunk_id LIMIT 8
        """, (terms, query, query, scope.bank.symbol, str(scope.period.year), f"Q{scope.period.quarter}",
              self.threshold, not scope.topics and not scope.terms, self.threshold))
        return [
            Passage(
                bank=scope.bank.symbol, period=scope.period, text=row["body"],
                topics=scope.topics or scope.terms[:1], terms=scope.terms, distance=row["distance"], relevance=row["rank"],
                heading=row["name"],
                citation=Citation(
                    source=SourceName.SLIDES,
                    id=opaque_id(SourceName.SLIDES, row["file_path"], row["file_hash"],
                                 row["page_number"], row["chunk_id"]),
                    locator=f"Investor slides · {scope.bank.symbol} · {scope.period} · page {row['page_number']}",
                ),
            )
            for row in rows
        ]

    def anchors(self, conn: SourceConnection, scope: Scope) -> list[Citation]:
        return [passage.citation for passage in self.search(conn, scope)]


class RtsSource:
    def __init__(self, threshold: float):
        self.threshold = threshold

    def probe(self, conn: SourceConnection, scope: Scope) -> Probe:
        rows = conn.execute("""
            SELECT filename, count(*) AS chunks, max(created_at) AS latest,
                   count(*) FILTER (WHERE page_no IS NOT NULL AND raw_text <> '') AS usable
            FROM public.rts_embedding
            WHERE bank = %s AND year = %s AND quarter = %s
            GROUP BY filename ORDER BY filename
        """, (scope.bank.symbol, scope.period.year, f"Q{scope.period.quarter}")).fetchall()
        return document_probe(rows, "legacy")

    def search(self, conn: SourceConnection, scope: Scope, vector: list[float] | None = None) -> list[Passage]:
        terms = list(search_terms(scope.topics, scope.terms))
        rows = conn.execute("""
            WITH terms AS (
                SELECT phraseto_tsquery('english', phrase) AS term FROM unnest(%s::text[]) AS phrases(phrase)
            ), clean AS (
                SELECT id, filename, created_at, page_no, chunk_id, source_section, summary_title,
                       btrim(regexp_replace(left(raw_text, 16000), '<!--.*?-->', 'g')) AS body,
                       embedding OPERATOR(public.<=>) %s::public.halfvec(3072) AS distance
                FROM public.rts_embedding
                WHERE bank = %s AND year = %s AND quarter = %s AND page_no IS NOT NULL AND raw_text <> ''
            ), fields AS (
                SELECT *, to_tsvector('english', coalesce(source_section, '')) AS heading,
                       to_tsvector('english', coalesce(summary_title, '')) AS summary,
                       to_tsvector('english', body) AS content,
                       CASE WHEN lower(coalesce(source_section, '') || ' ' || coalesce(summary_title, ''))
                             ~ 'glossary|endnotes?|footnotes?|notes to (the )?(consolidated )?financial|non.gaap|forward.looking|disclaimer'
                            THEN 0.12
                            WHEN coalesce(source_section, '') ~* 'md[[:space:]]*&[[:space:]]*a|management.s discussion'
                            THEN 1.4 ELSE 1 END AS section_weight
                FROM clean
                WHERE body ~ '[[:alpha:]]' AND body !~* '^[[:space:]]*(page|footer|header)[[:space:]:#-]*[0-9[:space:]|/-]+$'
            ), ranked AS (
                SELECT *, coalesce((SELECT sum(
                            5 * (heading @@ term)::int + 3 * (summary @@ term)::int
                            + least(2.0, ts_rank_cd(content, term, 0) * 8)
                                * least(1.0, char_length(body) / 220.0)
                        ) FROM terms), 0) * section_weight AS rank,
                       EXISTS (
                           SELECT 1 FROM terms WHERE heading @@ term
                             AND (numnode(term) > 1 OR (summary @@ term AND char_length(body) >= 35))
                       ) AS heading_match
                FROM fields
            ), eligible AS (
                SELECT *, rank + CASE WHEN distance IS NULL THEN 0
                    ELSE greatest(0, %s - distance) * 0.2 END AS score
                FROM ranked
                WHERE (char_length(body) >= 75 OR (heading_match AND section_weight >= 1))
                  AND (rank > 0 OR distance <= %s OR %s)
            ), pages AS (
                SELECT *, row_number() OVER (
                    PARTITION BY filename, page_no ORDER BY score DESC, rank DESC, distance NULLS LAST, chunk_id, id
                ) AS position
                FROM eligible
            )
            SELECT filename, created_at, page_no, chunk_id, body, source_section, summary_title, distance, rank
            FROM pages WHERE position <= 2
            ORDER BY score DESC, rank DESC, distance NULLS LAST, filename, page_no, chunk_id, id LIMIT 8
        """, (terms, vector_literal(vector), scope.bank.symbol, scope.period.year, f"Q{scope.period.quarter}",
              self.threshold, self.threshold, not scope.topics and not scope.terms))
        return [
            Passage(
                bank=scope.bank.symbol, period=scope.period, text=row["body"],
                topics=scope.topics or scope.terms[:1], terms=scope.terms, distance=row["distance"], relevance=row["rank"],
                heading=" > ".join(filter(None, (row["source_section"], row["summary_title"]))),
                citation=Citation(
                    source=SourceName.RTS,
                    id=opaque_id(SourceName.RTS, row["filename"], row["created_at"], row["page_no"], row["chunk_id"]),
                    locator=f"Report to Shareholders · {scope.bank.symbol} · {scope.period} · page {row['page_no']}",
                ),
            )
            for row in rows
        ]

    def anchors(self, conn: SourceConnection, scope: Scope) -> list[Citation]:
        return [passage.citation for passage in self.search(conn, scope)]


def document_probe(rows, generation) -> Probe:
    marker = opaque_id(rows)
    if not rows:
        return Probe(state=Readiness.ABSENT, marker=marker, generation=generation, reason="document_absent")
    if any(row["usable"] != row["chunks"] for row in rows):
        return Probe(state=Readiness.INCOMPLETE, marker=marker, generation=generation, reason="document_incomplete")
    return Probe(state=Readiness.READY, marker=marker, generation=generation)


def build_sources(settings: Settings) -> dict[SourceName, SourceAdapter]:
    enabled = {
        SourceName.BENCHMARKING: BenchmarkingSource(settings.currencies),
        SourceName.EARNINGS: EarningsSource(settings.earnings_distance),
        SourceName.SLIDES: SlideSource(settings.slides_distance),
        SourceName.RTS: RtsSource(settings.rts_distance),
    }
    return {name: enabled[name] if name in enabled else DisabledSource() for name in SourceName}
