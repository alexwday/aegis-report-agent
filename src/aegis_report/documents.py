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
        topic = scope.topics[0] if scope.topics else ""
        query = vector_literal(vector)
        rows = conn.execute("""
            WITH candidates AS (
                SELECT d.file_path, d.file_hash, d.chunk_id, d.page_number, left(d.chunk_content, 16000) AS body,
                       strpos(lower(concat_ws(' ', d.name, d.chunk_content, d.keywords::text)), lower(%s)) > 0 AS hit,
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
            )
            SELECT file_path, file_hash, chunk_id, page_number, body, distance FROM candidates
            WHERE hit OR distance <= %s
            ORDER BY hit DESC, distance NULLS LAST, file_path, page_number, chunk_id LIMIT 8
        """, (topic, query, query, scope.bank.symbol, str(scope.period.year), f"Q{scope.period.quarter}",
              self.threshold))
        return [
            Passage(
                bank=scope.bank.symbol, period=scope.period, text=row["body"],
                topics=scope.topics, distance=row["distance"],
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
        topic = scope.topics[0] if scope.topics else ""
        rows = conn.execute("""
            WITH candidates AS (
                SELECT filename, created_at, page_no, chunk_id, left(raw_text, 16000) AS body,
                       strpos(lower(concat_ws(' ', source_section, raw_text)), lower(%s)) > 0 AS hit,
                       embedding OPERATOR(public.<=>) %s::public.halfvec(3072) AS distance
                FROM public.rts_embedding
                WHERE bank = %s AND year = %s AND quarter = %s AND page_no IS NOT NULL AND raw_text <> ''
            )
            SELECT filename, created_at, page_no, chunk_id, body, distance FROM candidates
            WHERE hit OR distance <= %s
            ORDER BY hit DESC, distance NULLS LAST, filename, page_no, chunk_id LIMIT 8
        """, (topic, vector_literal(vector), scope.bank.symbol, scope.period.year, f"Q{scope.period.quarter}",
              self.threshold))
        return [
            Passage(
                bank=scope.bank.symbol, period=scope.period, text=row["body"],
                topics=scope.topics, distance=row["distance"],
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
