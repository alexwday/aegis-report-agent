import re

from .config import Settings
from .models import SourceName
from .sources import (
    BenchmarkingSource,
    Citation,
    DisabledSource,
    EarningsSource,
    FollowingChunk,
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
                       CASE WHEN %s OR concat_ws(' ', d.name, left(d.chunk_content, 120)) !~*
                            'glossary|endnotes?|^[# ]*notes|reconciliation|forward.looking|disclaimer'
                       THEN 1 ELSE 0.15 END AS heading_weight,
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
                                 WHERE lexemes @@ term), 0) * heading_weight AS rank
                FROM candidates
            )
            SELECT file_path, file_hash, chunk_id, page_number, name, body, distance, rank
            FROM ranked
            WHERE rank > 0 OR distance <= %s OR %s
            ORDER BY rank + CASE WHEN distance IS NULL THEN 0 ELSE greatest(0, %s - distance) * 0.05 END DESC,
                     rank DESC, distance NULLS LAST, file_path, page_number, chunk_id LIMIT 8
        """, (terms, scope.include_definitions, query, query, scope.bank.symbol, str(scope.period.year), f"Q{scope.period.quarter}",
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
        rows = conn.execute(r"""
            WITH terms AS (
                SELECT phraseto_tsquery('english', phrase) AS term FROM unnest(%(terms)s::text[]) AS phrases(phrase)
            ), scoped AS (
                SELECT id, filename, created_at, page_no, chunk_id, source_section, summary_title,
                       btrim(regexp_replace(left(raw_text, 16000), '<!--.*?-->', 'g')) AS body,
                       embedding OPERATOR(public.<=>) %(vector)s::public.halfvec(3072) AS distance
                FROM public.rts_embedding
                WHERE bank = %(bank)s AND year = %(year)s AND quarter = %(quarter)s
                  AND page_no IS NOT NULL AND raw_text <> ''
            ), fields AS (
                SELECT *, to_tsvector('english', coalesce(source_section, '')) AS heading,
                       to_tsvector('english', coalesce(summary_title, '')) AS summary,
                       to_tsvector('english', body) AS content,
                       ARRAY(
                           SELECT to_tsvector('english', unit)
                           FROM regexp_split_to_table(body, '[.!?][[:space:]]+|[[:space:]]*\n[[:space:]]*') AS unit
                           WHERE unit ~* '[0-9][0-9.,]*[[:space:]]*(%%|bps?|basis points?|million|billion)([^a-z]|$)'
                       ) AS quantified,
                       CASE
                           WHEN coalesce(source_section, '') ~* 'md[[:space:]]*&[[:space:]]*a|management.s discussion'
                           THEN 1.3 ELSE 1 END AS section_weight
                FROM scoped
                WHERE body ~ '[[:alpha:]]'
                  AND body !~* '^[[:space:]]*(<figure[ >]|(page|footer|header)[[:space:]:#-]*[0-9[:space:]|/-]+$)'
                  AND concat_ws(' > ', source_section, summary_title) !~* %(reference_headings)s
                  AND left(body, 360) !~* %(reference_text)s
            ), ranked AS (
                SELECT *, coalesce((SELECT sum(
                            (heading @@ term)::int * 3 + (summary @@ term)::int * 2
                            + least(1.8, ts_rank_cd(content, term, 0) * 6)
                                * least(1.0, char_length(body) / 220.0)
                            + 7 * EXISTS (SELECT 1 FROM unnest(quantified) AS figure WHERE figure @@ term)::int
                        ) FROM terms), 0) * section_weight AS rank,
                       EXISTS (SELECT 1 FROM terms WHERE heading @@ term AND
                               (numnode(term) > 1 OR summary @@ term)) AS heading_match
                FROM fields
            ), eligible AS (
                SELECT *, rank + CASE WHEN distance <= %(threshold)s
                     THEN 5 * (1 - distance / greatest(0.001, %(threshold)s)) ELSE 0 END AS score
                FROM ranked
                WHERE (char_length(body) >= 75 OR (char_length(body) >= 38 AND
                       (heading_match OR cardinality(quantified) > 0)))
                  AND (rank > 0 OR distance <= %(threshold)s OR %(unfocused)s)
            ), pages AS (
                SELECT *, row_number() OVER (
                    PARTITION BY filename, page_no ORDER BY score DESC, rank DESC, distance NULLS LAST, chunk_id, id
                ) AS position, max(score) OVER () AS best
                FROM eligible
            ), chosen AS (
                SELECT * FROM pages
                WHERE position <= 2 AND (%(unfocused)s OR (score >= 1.15 AND score >= best * 0.24))
                ORDER BY score DESC, rank DESC, distance NULLS LAST, filename, page_no, chunk_id, id LIMIT 8
            )
            SELECT chosen.*, previous.body AS previous_text,
                   following.body AS next_text, following.created_at AS next_created_at
            FROM chosen
            LEFT JOIN LATERAL (
                SELECT body FROM scoped
                WHERE filename = chosen.filename AND page_no = chosen.page_no AND chunk_id = chosen.chunk_id - 1
                ORDER BY created_at DESC NULLS LAST, id DESC LIMIT 1
            ) previous ON true
            LEFT JOIN LATERAL (
                SELECT body, created_at FROM scoped
                WHERE filename = chosen.filename AND page_no = chosen.page_no AND chunk_id = chosen.chunk_id + 1
                ORDER BY created_at DESC NULLS LAST, id DESC LIMIT 1
            ) following ON true
            ORDER BY score DESC, rank DESC, distance NULLS LAST, filename, page_no, chunk_id, id
        """, {
            "terms": terms, "vector": vector_literal(vector), "bank": scope.bank.symbol, "year": scope.period.year,
            "quarter": f"Q{scope.period.quarter}", "threshold": self.threshold, "unfocused": not terms,
            "reference_headings": (
                r"(^|[>/–—:] *)[ #_*]*(glossary|definitions?|abbreviations?|endnotes?|footnotes?|"
                r"notes to (the )?(consolidated )?financial|accounting polic(y|ies)|non.gaap|"
                r"forward.looking|disclaimers?|legal notices?|cover( page)?|table of contents|index)\M"
            ),
            "reference_text": (
                r"^[ #_*]*(glossary|list of abbreviations|table of contents|forward.looking statements|legal notice)\M"
                r"|^.{0,100}\m(is|are) (defined|calculated|computed) (as|by)\M"
            ),
        })
        passages = []
        for row in rows:
            locator = f"Report to Shareholders · {scope.bank.symbol} · {scope.period} · page {row['page_no']}"
            reference = (SourceName.RTS, row["filename"], row["created_at"], row["page_no"], row["chunk_id"])
            previous = (row["previous_text"] or "").strip()
            mid_sentence = bool(previous and re.search(r"[,;]$", previous))
            following = None
            if row["next_text"]:
                following = FollowingChunk(
                    text=row["next_text"], citation=Citation(
                        source=SourceName.RTS,
                        id=opaque_id(*reference, row["next_created_at"], row["chunk_id"] + 1),
                        locator=f"{locator} · chunks {row['chunk_id']}–{row['chunk_id'] + 1}",
                    ),
                )
            passages.append(Passage(
                bank=scope.bank.symbol, period=scope.period, text=row["body"],
                topics=scope.topics or scope.terms[:1], terms=scope.terms, distance=row["distance"], relevance=row["rank"],
                heading=" > ".join(filter(None, (row["source_section"], row["summary_title"]))),
                begins_mid_sentence=mid_sentence, following=following,
                citation=Citation(source=SourceName.RTS, id=opaque_id(*reference), locator=locator),
            ))
        return passages

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
