import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import sleep
from uuid import uuid4

import httpx
import psycopg
from psycopg.types.json import Jsonb

from .auth import OwnerStatusChecker, UnwiredOwnerStatus
from .chat_agent import ChatAgent
from .claims import shortlist_passages
from .config import Settings
from .db import connect
from .diff import report_diff
from .documents import build_sources
from .engine import generate_report
from .gateway import CredentialProvider, GatewayError, ModelGateway, build_gateway
from .models import BenchmarkInput, EarningsInput, Period, ReportSpec, SectionInput, SourceName
from .readiness import observe, record_observation
from .repository import period_scopes
from .sources import BankCatalog, Passage, Probe, Readiness, Scope, SourceIssue, opaque_id
from .topics import search_terms

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 3



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
        return tuple(self.selector.terms) if not isinstance(self.selector, (BenchmarkInput, EarningsInput)) else ()

    def source_scope(self, bank) -> Scope:
        if isinstance(self.selector, BenchmarkInput):
            return Scope(bank, self.period, self.selector.metric, self.selector.segment)
        return Scope(bank, self.period, topics=self.topics, terms=self.terms)

    def describe(self) -> dict:
        return {
            "source": self.source, "bank": self.bank, "period": self.period.model_dump(),
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


class Worker:
    def __init__(
        self, settings: Settings, gateway: ModelGateway,
        owner_status: OwnerStatusChecker | None = None, *, clock: Callable[[], datetime] | None = None,
    ):
        self.settings = settings
        self.gateway = gateway
        self.owner_status = owner_status or UnwiredOwnerStatus(settings.local)
        self.clock = clock or (lambda: datetime.now(UTC))
        self.catalog = BankCatalog()
        self.sources = build_sources(settings)

    def _claim(self, now):
        with connect(self.settings.report_dsn) as conn:
            conn.execute("DELETE FROM rpt.runs WHERE mode = 'preview' AND expires_at <= %s", (now,))
            conn.execute("""
                UPDATE rpt.runs SET state = 'failed', error_code = 'attempts_exhausted',
                                    lease_token = NULL, lease_until = NULL
                WHERE state = 'running' AND lease_until <= %s AND attempt_count >= %s
            """, (now, MAX_ATTEMPTS))
            return conn.execute("""
                WITH next_run AS (
                    SELECT id FROM rpt.runs
                    WHERE ((state IN ('queued', 'waiting') AND next_probe_at <= %s)
                        OR (state = 'running' AND lease_until <= %s))
                      AND (expires_at IS NULL OR expires_at > %s)
                    ORDER BY next_probe_at, created_at, id LIMIT 1 FOR UPDATE SKIP LOCKED
                )
                UPDATE rpt.runs r SET state = 'running', lease_token = %s, lease_until = %s,
                                      attempt_count = r.attempt_count + 1
                FROM next_run WHERE r.id = next_run.id
                RETURNING r.id, r.owner_key, r.mode, r.trigger_kind, r.report_id, r.period, r.spec,
                          r.baseline_id, r.preview_section_id, r.readiness, r.lease_token, r.stop_after, r.schedule_revision
            """, (now, now, now, uuid4(), now + timedelta(minutes=3))).fetchone()

    def run_one(self, now: datetime | None = None) -> bool:
        started_at = now or self.clock()
        job = self._claim(started_at)
        if not job:
            return False
        result, state, error_code = None, "failed", None
        readiness = job["readiness"]
        next_probe = started_at
        try:
            if job["mode"] == "generate" and not self._active_owner(job):
                raise SourceIssue(Readiness.UNKNOWN, "report_or_owner_inactive")
            if job["schedule_revision"] is not None:
                with connect(self.settings.report_dsn) as conn:
                    if not self._active_schedule(conn, job):
                        raise SourceIssue(Readiness.UNKNOWN, "schedule_inactive_or_changed")
            spec = ReportSpec.model_validate(job["spec"])
            period = Period.model_validate(job["period"])
            automatic = job["trigger_kind"] == "automatic"
            requests = requests_for(spec, period)
            try:
                readiness, evidence = self._observe_sources(requests, readiness, started_at, automatic)
            except psycopg.Error:
                unavailable = Probe(state=Readiness.UNKNOWN, reason="source_unavailable")
                readiness = {
                    item.key: observe(unavailable, {}, started_at, self.settings.quiet_seconds) | item.describe()
                    for item in requests
                }
                evidence = None if automatic else {section.id: [] for section in spec.sections}
            if evidence is None:
                physical_ready = all(
                    entry["state"] == Readiness.READY for entry in readiness.values() if entry["required"]
                )
                interval = self.settings.quiet_seconds if physical_ready else min(self.settings.quiet_seconds, 60)
                next_probe += timedelta(seconds=max(self.settings.poll_seconds, interval))
                state = "waiting"
            else:
                result = generate_report(
                    spec, period, evidence, self.gateway,
                    trace=job["mode"] == "preview" and job["preview_section_id"] is not None,
                    gather_only=job["stop_after"] == "gather",
                )
                result["readiness"] = readiness
                if job["baseline_id"] is not None:
                    self._apply_diff(job, result)
                state = "succeeded"
        except (GatewayError, SourceIssue) as exc:
            error_code = exc.reason if isinstance(exc, SourceIssue) else str(exc)
        except (ValueError, ArithmeticError):
            error_code = "invalid_report_input"

        finished_at = now or self.clock()
        with connect(self.settings.report_dsn) as conn:
            if state == "succeeded" and job["schedule_revision"] is not None:
                # Schedule mutations and archive take this same report lock first.
                conn.execute("SELECT id FROM rpt.reports WHERE id = %s FOR SHARE", (job["report_id"],))
                if not self._active_schedule(conn, job):
                    state, result, error_code = "failed", None, "schedule_inactive_or_changed"
            conn.execute("""
                UPDATE rpt.runs SET state = %s, result = %s, readiness = %s, error_code = %s, next_probe_at = %s,
                                    lease_token = NULL, lease_until = NULL,
                                    attempt_count = CASE WHEN %s = 'waiting' THEN 0 ELSE attempt_count END
                WHERE id = %s AND lease_token = %s AND lease_until > %s
            """, (state, Jsonb(result) if result is not None else None, Jsonb(readiness), error_code, next_probe,
                  state, job["id"], job["lease_token"], finished_at))
        return True

    def _active_owner(self, job):
        with connect(self.settings.report_dsn) as conn:
            active_report = conn.execute("""
                SELECT id FROM rpt.reports WHERE id = %s AND owner_key = %s AND archived_at IS NULL
            """, (job["report_id"], job["owner_key"])).fetchone()
        return bool(active_report and self.owner_status.is_active(job["owner_key"]))

    def _active_schedule(self, conn, job):
        return conn.execute("""
            SELECT s.report_id FROM rpt.schedules s JOIN rpt.reports r ON r.id = s.report_id
            WHERE s.report_id = %s AND r.owner_key = %s AND r.archived_at IS NULL
              AND s.enabled AND s.revision = %s
        """, (job["report_id"], job["owner_key"], job["schedule_revision"])).fetchone() is not None

    def _apply_diff(self, job, output):
        with connect(self.settings.report_dsn) as conn:
            baseline = conn.execute("""
                SELECT result FROM rpt.runs
                WHERE id = %s AND owner_key = %s AND mode = 'generate' AND state = 'succeeded'
            """, (job["baseline_id"], job["owner_key"])).fetchone()
        if not baseline:
            raise SourceIssue(Readiness.UNKNOWN, "baseline_unavailable")
        comparison = baseline["result"]
        if job["preview_section_id"]:
            comparison = comparison | {"sections": [
                section for section in comparison["sections"] if section["id"] == job["preview_section_id"]
            ]}
        output["diff"], details = report_diff(comparison, output)
        output["diff_details"] = details.model_dump(mode="json")
        output["baseline_run_id"] = str(job["baseline_id"])

    def _vectors(self, requests, previous, automatic):
        if (automatic and not previous) or not getattr(self.gateway, "supports_semantic_ranking", False):
            return {}
        topics = dict.fromkeys(
            search_terms(request.topics, request.terms)
            for request in requests if getattr(request.selector, "vector", False)
        )
        vectors = {}
        for selection in list(topics)[:6]:
            try:
                vectors[selection] = self.gateway.embed(" · ".join(selection))
            except GatewayError:
                # Lexical classification and lookup remain available after an optional embedding failure.
                continue
        return vectors

    def _observe_sources(self, requests, previous, now, automatic):
        vectors = self._vectors(requests, previous, automatic)
        with connect(self.settings.source_dsn, source=True) as source_conn:
            banks, items, readiness = {}, [], {}
            catalog = self.catalog.list(source_conn)
            for item in requests:
                if item.bank not in banks:
                    try:
                        banks[item.bank] = self.catalog.match(catalog, item.bank)
                    except SourceIssue as issue:
                        banks[item.bank] = issue
                bank = banks[item.bank]
                if item.peer_group and not isinstance(bank, SourceIssue) and "canadian_bank" not in bank.tags:
                    bank = SourceIssue(Readiness.UNKNOWN, "peer_group_membership_unconfirmed")
                if isinstance(bank, SourceIssue):
                    probe = Probe(state=bank.state, reason=bank.reason)
                    readiness[item.key] = observe(probe, {}, now, self.settings.quiet_seconds) | item.describe()
                else:
                    items.append((item, (item.source, item.source_scope(bank))))

            distinct = dict.fromkeys(query for _, query in items)
            hints = {query: self.catalog.hinted(source_conn, query[1], query[0]) for query in distinct}
            probes = {
                (source, scope): self.sources[source].probe(source_conn, scope)
                for source, scope in sorted(distinct, key=lambda q: not hints[q])
            }
            keys = {
                (source, scope): opaque_id(source, scope.bank.symbol, str(scope.period), scope.metric, scope.segment)
                for source, scope in probes
            }
            # The marker records physical scope and intentionally ignores topical or ranking preferences.
            by_key = {keys[query]: probe for query, probe in probes.items()}
            with connect(self.settings.report_dsn) as report_conn:
                stabilities = {
                    key: record_observation(report_conn, key, by_key[key], now, self.settings.quiet_seconds)
                    for key in sorted(by_key)
                }

            for item, query in items:
                readiness[item.key] = observe(
                    probes[query], previous.get(item.key, {}), now, self.settings.quiet_seconds
                ) | item.describe() | {"data_stability": stabilities[keys[query]]}
                if not automatic:
                    readiness[item.key]["stable"] = stabilities[keys[query]] == "stable"

            if automatic and any(entry["required"] and not entry["stable"] for entry in readiness.values()):
                return readiness, None

            evidence = {item.section_id: [] for item in requests}
            selected = {}
            for item, query in items:
                if probes[query].state is not Readiness.READY:
                    continue
                source, scope = query
                use_vector = getattr(item.selector, "vector", False)
                search_key = (query, use_vector, item.instruction)
                if search_key not in selected:
                    try:
                        hits = self.sources[source].search(
                            source_conn, scope, vectors.get(search_terms(item.topics, item.terms)) if use_vector else None,
                        )
                        selected[search_key] = shortlist_passages(
                            hits, item.instruction, semantic=use_vector and bool(vectors),
                        ) if hits and isinstance(hits[0], Passage) else hits
                    except SourceIssue as issue:
                        selected[search_key] = issue
                hits = selected[search_key]
                if isinstance(hits, SourceIssue):
                    readiness[item.key].update(
                        state=hits.state, reason=hits.reason, stable=False, since=None, data_stability="unknown",
                    )
                    if automatic and item.selector.required:
                        return readiness, None
                else:
                    readiness[item.key]["evidence_state"] = "matched" if hits else "no_match"
                    evidence[item.section_id].extend(hits)
            return readiness, evidence


def main(
    owner_status: OwnerStatusChecker | None = None, credentials: CredentialProvider | None = None
) -> None:
    settings = Settings.from_env()
    logging.basicConfig(level=logging.INFO)
    with httpx.Client(trust_env=False) as client:
        gateway = build_gateway(settings, client, credentials)
        worker = Worker(settings, gateway, owner_status)
        chat = ChatAgent(settings, gateway)
        logger.info("Report worker started")
        while True:
            try:
                busy = chat.run_one()
                busy = worker.run_one() or busy
            except psycopg.Error:
                logger.warning("Database unavailable during worker attempt")
                busy = False
            if not busy:
                sleep(settings.poll_seconds)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
