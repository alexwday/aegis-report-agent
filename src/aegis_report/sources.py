import json
import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from typing import Literal, Protocol

from psycopg import Connection
from psycopg.rows import DictRow

from .models import Period, SourceName, StrictModel

SourceConnection = Connection[DictRow]


def opaque_id(*parts: object) -> str:
    return sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


class Readiness(StrEnum):
    READY = "ready"
    INCOMPLETE = "incomplete"
    ABSENT = "absent"
    UNKNOWN = "unknown"


class Probe(StrictModel):
    state: Readiness
    marker: str | None = None
    generation: Literal["legacy", "unified", "conflict"] | None = None
    reason: str | None = None


class Citation(StrictModel):
    id: str
    source: SourceName
    locator: str


@dataclass(frozen=True)
class Bank:
    id: int
    symbol: str
    name: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class Scope:
    bank: Bank
    period: Period
    metric: str | None = None
    segment: str = "Enterprise"


ChangeBasis = Literal["basis_points", "percent_change", "unknown"]


class BenchmarkFact(StrictModel):
    bank: str
    period: Period
    metric: str
    segment: str
    actual: Decimal | None
    unit: str | None
    unit_source: Literal["kpi_metadata", "row", "unknown"] = "unknown"
    currency: str | None
    currency_confirmed: bool | None
    raw_qoq: Decimal | None
    raw_yoy: Decimal | None
    change_basis: ChangeBasis
    citation: Citation


class EarningsBlock(StrictModel):
    bank: str
    period: Period
    generation: str
    edition: str
    version: str | None
    text: str
    citation: Citation


class SourceIssue(Exception):
    def __init__(self, state: Readiness, reason: str):
        super().__init__(reason)
        self.state = state
        self.reason = reason


class SourceAdapter(Protocol):
    def probe(self, conn: SourceConnection, scope: Scope) -> Probe: ...
    def search(self, conn: SourceConnection, scope: Scope) -> list[BenchmarkFact] | list[EarningsBlock]: ...
    def anchors(self, conn: SourceConnection, scope: Scope) -> list[Citation]: ...


class BankCatalog:
    def list(self, conn: SourceConnection) -> list[Bank]:
        rows = conn.execute("""
            SELECT bank_id, bank_symbol, bank_name, bank_aliases
            FROM public.aegis_data_availability
            ORDER BY fiscal_year DESC, quarter DESC, id DESC
        """)
        names = {}
        aliases = defaultdict(set)
        for row in rows:
            key = (row["bank_id"], row["bank_symbol"])
            names.setdefault(key, row["bank_name"])
            aliases[key].update(alias for alias in (row["bank_aliases"] or []) if alias)
        return [
            Bank(id_, symbol, names[(id_, symbol)], tuple(sorted(aliases[(id_, symbol)])))
            for id_, symbol in sorted(names, key=lambda key: (key[1], key[0]))
        ]

    def resolve(self, conn: SourceConnection, name: str) -> Bank:
        banks = self.list(conn)
        folded = name.strip().casefold()
        exact = [bank for bank in banks if bank.symbol.casefold() == folded]
        matches = exact or [
            bank for bank in banks
            if folded in {alias.casefold() for alias in (bank.name, *bank.aliases)}
        ]
        if len(matches) != 1:
            reason = "ambiguous_bank" if matches else "unknown_bank"
            raise SourceIssue(Readiness.UNKNOWN, reason)
        return matches[0]

    def hinted(self, conn: SourceConnection, scope: Scope, source: SourceName) -> bool:
        flag = "investor_relations_benchmarking" if source is SourceName.BENCHMARKING else source.value
        result = conn.execute("""
            SELECT database_names
            FROM public.aegis_data_availability
            WHERE bank_id = %s AND fiscal_year = %s AND quarter = %s
        """, (scope.bank.id, scope.period.year, f"Q{scope.period.quarter}")).fetchone()
        flags = (result["database_names"] or []) if result else []
        return flag in flags or (source is SourceName.SUPPLEMENT and "supplementary" in flags)


class BenchmarkingSource:
    def __init__(self, currencies: dict[str, str]):
        self.currencies = currencies

    def _rows(self, conn: SourceConnection, scope: Scope) -> list[DictRow]:
        return conn.execute("""
            SELECT b.bank_symbol, b.bank, b."Parameter" AS metric, b."Platform" AS segment,
                   b."Actual" AS actual, b."QoQ" AS qoq, b."YoY" AS yoy,
                   b."BPS" AS bps, b."Units" AS row_units, b.updated_at, b.filepath, m.unit
            FROM public.benchmarking_report b
            LEFT JOIN public.kpi_metadata m ON m.kpi_name = b."Parameter"
            WHERE b.bank_symbol = %s AND b.fiscal_year = %s AND b.quarter = %s
              AND b."Parameter" = %s AND b."Platform" = %s
            LIMIT 2
        """, (scope.bank.symbol, scope.period.year, f"Q{scope.period.quarter}", scope.metric, scope.segment)).fetchall()

    def probe(self, conn: SourceConnection, scope: Scope) -> Probe:
        if scope.metric is None:
            return Probe(state=Readiness.UNKNOWN, reason="metric_required")
        marker = conn.execute("""
            SELECT count(*) AS row_count, max(updated_at) AS latest,
                   array_agg(DISTINCT filepath ORDER BY filepath) AS files
            FROM public.benchmarking_report
            WHERE bank_symbol = %s AND fiscal_year = %s AND quarter = %s
        """, (scope.bank.symbol, scope.period.year, f"Q{scope.period.quarter}")).fetchone()
        rows = self._rows(conn, scope)
        if not rows:
            state, reason = Readiness.ABSENT, "benchmark_observation_absent"
        elif len(rows) != 1:
            state, reason = Readiness.INCOMPLETE, "duplicate_benchmark_observation"
        elif rows[0]["actual"] is None:
            state, reason = Readiness.INCOMPLETE, "null_benchmark_observation"
        else:
            state, reason = Readiness.READY, None
        return Probe(state=state, reason=reason, marker=opaque_id(marker))

    def search(self, conn: SourceConnection, scope: Scope) -> list[BenchmarkFact]:
        if scope.metric is None:
            raise SourceIssue(Readiness.UNKNOWN, "metric_required")
        rows = self._rows(conn, scope)
        if len(rows) > 1:
            raise SourceIssue(Readiness.INCOMPLETE, "duplicate_benchmark_observation")
        if not rows:
            return []
        row = rows[0]
        country = scope.bank.symbol.rsplit("-", 1)[-1]
        metadata_unit = (row["unit"] or "").strip()
        row_unit = (row["row_units"] or "").strip()
        unit = metadata_unit or row_unit or None
        unit_source = "kpi_metadata" if metadata_unit else "row" if row_unit else "unknown"
        if row["bps"] == "Yes":
            basis = "basis_points"
        elif (
            country == "US" and scope.segment == "Capital Markets"
            and "%" in (unit, row["row_units"])
        ) or row["bps"] not in (None, "No", ""):
            basis = "unknown"
        else:
            basis = "percent_change"
        currency = (self.currencies.get(scope.bank.symbol) or self.currencies.get(country)) if unit == "millions" else None
        citation = Citation(
            id=opaque_id("benchmarking", row["filepath"], row["updated_at"], scope.bank.symbol,
                         str(scope.period), row["metric"], row["segment"]),
            source=SourceName.BENCHMARKING,
            locator=f"Derived dataset · snapshot {row['updated_at'] or 'undated'} · "
                    f"{scope.bank.symbol} · {row['metric']} · {row['segment']} · {scope.period}",
        )
        return [BenchmarkFact(
            bank=scope.bank.symbol, period=scope.period, metric=row["metric"], segment=row["segment"],
            actual=row["actual"], unit=unit, unit_source=unit_source, currency=currency, currency_confirmed=False if currency else None,
            raw_qoq=row["qoq"], raw_yoy=row["yoy"], change_basis=basis, citation=citation,
        )]

    def anchors(self, conn: SourceConnection, scope: Scope) -> list[Citation]:
        return [fact.citation for fact in self.search(conn, scope)]


class EarningsSource:
    def _inventory(self, conn: SourceConnection, scope: Scope) -> tuple[list[DictRow], list[DictRow]]:
        legacy = conn.execute("""
            SELECT event_id, version_id, transcript_type, filename, institution_id,
                   count(*) AS chunks, max(updated_at) AS latest
            FROM public.aegis_transcripts
            WHERE ticker = %s AND fiscal_year = %s AND fiscal_quarter = %s
            GROUP BY event_id, version_id, transcript_type, filename, institution_id
            ORDER BY event_id, version_id, transcript_type, filename, institution_id
        """, (scope.bank.symbol, scope.period.year, f"Q{scope.period.quarter}")).fetchall()
        unified = conn.execute("""
            SELECT file_id, file_hash, filename, count(*) AS chunks, max(created_at) AS latest
            FROM public."aegis-earnings-transcripts-data"
            WHERE bank = %s AND fiscal_year = %s AND quarter = %s
            GROUP BY file_id, file_hash, filename ORDER BY file_id, file_hash, filename
        """, (scope.bank.symbol, str(scope.period.year), f"Q{scope.period.quarter}")).fetchall()
        return legacy, unified

    def _coverage(self, scope: Scope, legacy: list[DictRow], unified: list[DictRow]) -> Probe:
        marker = opaque_id(legacy, unified)
        if legacy and unified:
            # The unified schema has no event_id column. Only compare IDs on vendor-pattern filenames.
            unified_ids = {
                match[1] for row in unified
                if (match := re.fullmatch(r".+_Q[1-4]_\d{4}_(?:Corrected|Raw)_(\d+)_\d+\.xml", row["filename"]))
            }
            legacy_ids = {row["event_id"] for row in legacy}
            reason = "cross_generation_event_overlap" if unified_ids & legacy_ids else "cross_generation_conflict"
            return Probe(state=Readiness.UNKNOWN, generation="conflict", marker=marker, reason=reason)
        if legacy:
            if any(row["institution_id"] != str(scope.bank.id) for row in legacy):
                return Probe(state=Readiness.UNKNOWN, generation="legacy", marker=marker, reason="bank_id_mismatch")
            try:
                self._winning_editions(legacy)
            except SourceIssue as issue:
                return Probe(state=issue.state, generation="legacy", marker=marker, reason=issue.reason)
            return Probe(state=Readiness.READY, generation="legacy", marker=marker)
        if unified:
            if len(unified) != 1:
                return Probe(state=Readiness.INCOMPLETE, generation="unified", marker=marker,
                             reason="multiple_unified_editions")
            return Probe(state=Readiness.READY, generation="unified", marker=marker)
        return Probe(state=Readiness.ABSENT, marker=marker, reason="no_earnings_call")

    def probe(self, conn: SourceConnection, scope: Scope) -> Probe:
        return self._coverage(scope, *self._inventory(conn, scope))

    def coverage_map(self, conn: SourceConnection, scopes: list[Scope]) -> dict[tuple[str, Period], Probe]:
        return {(scope.bank.symbol, scope.period): self.probe(conn, scope) for scope in scopes}

    def _winning_editions(self, editions: list[DictRow]) -> list[DictRow]:
        events = defaultdict(list)
        for edition in editions:
            version = edition["version_id"] or ""
            if (
                not edition["event_id"] or not edition["filename"]
                or edition["transcript_type"] not in ("Corrected", "Raw")
                or not re.fullmatch(r"[0-9]{1,40}", version)
            ):
                raise SourceIssue(Readiness.INCOMPLETE, "unverified_legacy_edition")
            rank = (edition["transcript_type"] == "Corrected", int(version))
            events[edition["event_id"]].append((rank, edition))
        winners = []
        for versions in events.values():
            ordered = sorted(versions, key=lambda version: version[0], reverse=True)
            if len(ordered) > 1 and ordered[0][0] == ordered[1][0]:
                raise SourceIssue(Readiness.INCOMPLETE, "ambiguous_legacy_edition")
            winners.append(ordered[0][1])
        return winners

    def search(self, conn: SourceConnection, scope: Scope) -> list[EarningsBlock]:
        legacy, unified = self._inventory(conn, scope)
        probe = self._coverage(scope, legacy, unified)
        if probe.state is Readiness.ABSENT:
            return []
        if probe.state is not Readiness.READY:
            raise SourceIssue(probe.state, probe.reason or "earnings_not_ready")
        if legacy:
            versions = self._winning_editions(legacy)
            if sum(version["chunks"] for version in versions) > 400:
                raise SourceIssue(Readiness.INCOMPLETE, "earnings_call_exceeds_chunk_limit")
            return [block for version in versions for block in self._legacy_blocks(conn, scope, version)]
        if unified[0]["chunks"] > 400:
            raise SourceIssue(Readiness.INCOMPLETE, "earnings_call_exceeds_chunk_limit")
        return self._unified_blocks(conn, scope, unified[0])

    def _legacy_blocks(self, conn: SourceConnection, scope: Scope, edition: DictRow) -> list[EarningsBlock]:
        rows = conn.execute("""
            SELECT title, section_name, speaker_block_id, qa_group_id, chunk_id, left(chunk_content, 16001) AS body
            FROM public.aegis_transcripts
            WHERE ticker = %s AND fiscal_year = %s AND fiscal_quarter = %s AND institution_id = %s
              AND event_id = %s AND transcript_type = %s AND version_id = %s AND filename = %s
            ORDER BY CASE WHEN section_name = 'MANAGEMENT DISCUSSION SECTION' THEN 0 ELSE 1 END,
                     qa_group_id NULLS FIRST, speaker_block_id, chunk_id, id
        """, (scope.bank.symbol, scope.period.year, f"Q{scope.period.quarter}", str(scope.bank.id),
              edition["event_id"], edition["transcript_type"], edition["version_id"], edition["filename"]))
        blocks = []
        for row in rows:
            text = self._verified_text(row["body"])
            coordinates = (row["section_name"], row["qa_group_id"], row["speaker_block_id"], row["chunk_id"])
            blocks.append(EarningsBlock(
                bank=scope.bank.symbol, period=scope.period, generation="legacy",
                edition=edition["transcript_type"], version=edition["version_id"], text=text,
                citation=Citation(id=opaque_id("legacy", scope.bank.symbol, edition["event_id"],
                                               edition["version_id"], edition["latest"], coordinates),
                                  source=SourceName.EARNINGS,
                                  locator=f"{row['title'] or 'Earnings call'} · {row['section_name']} · "
                                          f"speaker block {row['speaker_block_id']} · chunk {row['chunk_id']}"),
            ))
        return blocks

    def _unified_blocks(self, conn: SourceConnection, scope: Scope, edition: DictRow) -> list[EarningsBlock]:
        rows = conn.execute("""
            SELECT page_number, chunk_id, name, left(chunk_content, 16001) AS body
            FROM public."aegis-earnings-transcripts-data"
            WHERE bank = %s AND fiscal_year = %s AND quarter = %s AND file_id = %s AND file_hash = %s
            ORDER BY page_number NULLS LAST, chunk_id
        """, (scope.bank.symbol, str(scope.period.year), f"Q{scope.period.quarter}",
              edition["file_id"], edition["file_hash"]))
        return [
            EarningsBlock(
                bank=scope.bank.symbol, period=scope.period, generation="unified", edition="Corrected",
                version=None, text=self._verified_text(row["body"]),
                citation=Citation(id=opaque_id("unified", edition["file_id"], edition["file_hash"], row["chunk_id"]),
                                  source=SourceName.EARNINGS,
                                  locator=f"{row['name'] or 'Earnings call'} · sequence {row['page_number']} · "
                                          f"{row['chunk_id']}"),
            )
            for row in rows
        ]

    @staticmethod
    def _verified_text(body: str | None) -> str:
        if not body or len(body) > 16000:
            raise SourceIssue(Readiness.INCOMPLETE, "earnings_block_missing_or_exceeds_limit")
        return body

    def anchors(self, conn: SourceConnection, scope: Scope) -> list[Citation]:
        return [block.citation for block in self.search(conn, scope)]


class DisabledSource:
    def probe(self, conn: SourceConnection, scope: Scope) -> Probe:
        return Probe(state=Readiness.UNKNOWN, reason="not_enabled")

    def search(self, conn: SourceConnection, scope: Scope) -> list[BenchmarkFact]:
        raise SourceIssue(Readiness.UNKNOWN, "not_enabled")

    def anchors(self, conn: SourceConnection, scope: Scope) -> list[Citation]:
        raise SourceIssue(Readiness.UNKNOWN, "not_enabled")


def build_sources(currencies: dict[str, str]) -> dict[SourceName, SourceAdapter]:
    enabled = {SourceName.BENCHMARKING: BenchmarkingSource(currencies), SourceName.EARNINGS: EarningsSource()}
    return {name: enabled.get(name, DisabledSource()) for name in SourceName}


def compute_change(current: BenchmarkFact, prior: BenchmarkFact) -> Decimal | None:
    if (
        current.change_basis == "unknown" or prior.change_basis != current.change_basis
        or not current.unit or current.unit != prior.unit or current.currency != prior.currency
        or (current.bank, current.metric, current.segment) != (prior.bank, prior.metric, prior.segment)
        or current.actual is None or prior.actual is None
        or not current.actual.is_finite() or not prior.actual.is_finite()
    ):
        return None
    if current.change_basis == "basis_points":
        return (current.actual - prior.actual) * 100
    if prior.actual <= 0:
        return None
    return ((current.actual - prior.actual) / prior.actual * 100).quantize(Decimal("0.01"))
