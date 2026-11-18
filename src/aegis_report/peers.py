from statistics import median
from typing import Literal

from pydantic import Field

from .models import BenchmarkInput, Period, SectionSpec, StrictModel
from .sources import BenchmarkFact


class PeerRank(StrictModel):
    bank: str
    rank: int
    value: str
    citation_id: str


class PeerStatistics(StrictModel):
    metric: str
    segment: str
    period: Period
    basis: Literal["vendor_fiscal_label"]
    unit: str | None = None
    currency: str | None = None
    currency_confirmed: bool | None = None
    reason: Literal["missing_member", "unknown_unit", "mixed_units", "unknown_currency", "mixed_currencies",
                    "mixed_change_basis"] | None = None
    high: str | None = None
    low: str | None = None
    median: str | None = None
    ranks: list[PeerRank] = Field(default_factory=list)


def peer_statistics(section: SectionSpec, quarter: Period, rows: list[BenchmarkFact]) -> list[dict]:
    banks = section.bank_symbols()
    if len(banks) < 2:
        return []
    index = {(row.bank, row.metric, row.segment, row.period): row for row in rows}
    output = []
    for selector in section.sources:
        if not isinstance(selector, BenchmarkInput):
            continue
        for offset in section.time.resolved_offsets():
            period = quarter.shifted(offset)
            scope = [index.get((bank, selector.metric, selector.segment, period)) for bank in banks]
            points = [row for row in scope if row is not None and row.actual is not None and row.actual.is_finite()]
            output.append(summarize_peers(
                selector, period, section.time.basis, points, len(banks),
            ).model_dump(mode="json"))
    return output


def summarize_peers(selector, period, basis, rows, expected) -> PeerStatistics:
    result = PeerStatistics(metric=selector.metric, segment=selector.segment, period=period, basis=basis)
    units = {row.unit for row in rows}
    currencies = {row.currency or row.peer_currency for row in rows}
    if len(rows) != expected:
        result.reason = "missing_member"
    elif None in units:
        result.reason = "unknown_unit"
    elif len(units) != 1:
        result.reason = "mixed_units"
    elif None in currencies:
        result.reason = "unknown_currency"
    elif len(currencies) != 1:
        result.reason = "mixed_currencies"
    elif len({row.change_basis for row in rows}) != 1:
        result.reason = "mixed_change_basis"
    else:
        ordered = sorted(sorted(rows, key=lambda row: row.bank), key=lambda row: row.actual, reverse=True)
        values = [row.actual for row in ordered]
        result.unit = next(iter(units))
        result.currency = next(iter(currencies))
        result.currency_confirmed = all(row.currency_confirmed is True for row in rows)
        result.high, result.low, result.median = str(values[0]), str(values[-1]), str(median(values))
        rank = 0
        previous = None
        for position, row in enumerate(ordered, 1):
            if row.actual != previous:
                rank = position
            result.ranks.append(PeerRank(bank=row.bank, rank=rank, value=str(row.actual), citation_id=row.citation.id))
            previous = row.actual
    return result


def peer_text(peer: dict) -> str:
    scope = f"{peer['metric']} · {peer['segment']} · {Period.model_validate(peer['period'])}"
    if peer["reason"]:
        return f"{scope}: Peer comparison unavailable ({peer['reason'].replace('_', ' ')})."
    ranks = ", ".join(f"{row['bank']} #{row['rank']}" for row in peer["ranks"])
    currency = peer["currency"] + (" (unconfirmed)" if peer.get("currency_confirmed") is not True else "")
    return f"{scope}: Peer high {peer['high']}, low {peer['low']}, median {peer['median']}. {ranks}. Currency scope {currency}."
