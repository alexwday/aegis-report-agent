from dataclasses import dataclass

from .claims import DEFINITION_REQUEST
from .models import BenchmarkInput, EarningsInput, Period, ReportSpec, SectionInput, SourceName
from .repository import period_scopes
from .sources import BankCatalog, Probe, Readiness, Scope, SourceIssue, opaque_id


@dataclass(frozen=True)
class RequestScope:
    key: str
    section_id: str
    bank: str
    period: Period
    selector: SectionInput
    instruction: str
    peer_group: str | None = None

    @property
    def source(self) -> SourceName:
        return SourceName(self.selector.source)

    @property
    def topics(self) -> tuple[str, ...]:
        if isinstance(self.selector, EarningsInput):
            return tuple(self.selector.topics)
        if not isinstance(self.selector, BenchmarkInput) and self.selector.topic:
            return (self.selector.topic,)
        return ()

    @property
    def terms(self) -> tuple[str, ...]:
        return tuple(self.selector.terms) if not isinstance(self.selector, BenchmarkInput) else ()

    def source_scope(self, bank) -> Scope:
        if isinstance(self.selector, BenchmarkInput):
            return Scope(bank, self.period, self.selector.metric, self.selector.segment)
        return Scope(bank, self.period, topics=self.topics, terms=self.terms,
                     include_definitions=bool(DEFINITION_REQUEST.search(self.instruction)))

    def describe(self) -> dict:
        return {
            "section_id": self.section_id, "source": self.source, "bank": self.bank, "period": self.period.model_dump(),
            "required": self.selector.required, "selector": self.selector.model_dump(mode="json"),
        }


def requests_for(spec: ReportSpec, period: Period) -> list[RequestScope]:
    shifts = period_scopes(spec, period)
    return [
        RequestScope(
            (f"{section.id}:{index}:{offset}" if index else f"{section.id}:{offset}")
            + (f":{bank}" if section.bank is None else ""),
            section.id, bank, target, selector, section.instruction, section.peer_group,
        )
        for section in spec.sections
        for offset, target in shifts[section.id].items()
        for index, selector in enumerate(section.sources)
        for bank in section.bank_symbols()
    ]


def physical_key(source: SourceName, scope: Scope) -> str:
    return opaque_id(source, scope.bank.symbol, str(scope.period), scope.metric, scope.segment)


def probe_scopes(conn, requests: list[RequestScope], catalog: BankCatalog, sources):
    """Use one repeatable-read source snapshot and share probes for repeated physical scopes."""
    banks = {}
    probes = {}
    available = catalog.list(conn)
    for item in requests:
        if item.bank not in banks:
            try:
                banks[item.bank] = catalog.match(available, item.bank)
            except SourceIssue as issue:
                banks[item.bank] = issue
        bank = banks[item.bank]
        if item.peer_group and not isinstance(bank, SourceIssue) and "canadian_bank" not in bank.tags:
            bank = SourceIssue(Readiness.UNKNOWN, "peer_group_membership_unconfirmed")
        if isinstance(bank, SourceIssue):
            yield item, None, Probe(state=bank.state, reason=bank.reason)
            continue
        scope = item.source_scope(bank)
        key = physical_key(item.source, scope)
        if key not in probes:
            probes[key] = sources[item.source].probe(conn, scope)
        yield item, scope, probes[key]
