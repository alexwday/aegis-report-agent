import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from time import sleep
from uuid import uuid4

import httpx
import psycopg
from psycopg.types.json import Jsonb

from .auth import OwnerStatusChecker, UnwiredOwnerStatus
from .config import Settings
from .db import connect
from .engine import generate_report, report_diff
from .gateway import CredentialProvider, GatewayError, ModelGateway, build_gateway
from .models import Period, ReportSpec, SourceName
from .readiness import observe, record_observation
from .repository import period_scopes
from .sources import BankCatalog, BenchmarkingSource, Probe, Readiness, Scope, SourceIssue, opaque_id

logger = logging.getLogger(__name__)


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
        self.source = BenchmarkingSource(settings.currencies)

    def _claim(self, now):
        with connect(self.settings.report_dsn) as conn:
            conn.execute("DELETE FROM rpt.runs WHERE mode = 'preview' AND expires_at <= %s", (now,))
            return conn.execute("""
                WITH next_run AS (
                    SELECT id FROM rpt.runs
                    WHERE ((state IN ('queued', 'waiting') AND next_probe_at <= %s)
                        OR (state = 'running' AND lease_until <= %s))
                      AND (expires_at IS NULL OR expires_at > %s)
                    ORDER BY next_probe_at, created_at, id LIMIT 1 FOR UPDATE SKIP LOCKED
                )
                UPDATE rpt.runs r SET state = 'running', lease_token = %s, lease_until = %s
                FROM next_run WHERE r.id = next_run.id
                RETURNING r.id, r.owner_key, r.mode, r.trigger_kind, r.report_id, r.period, r.spec,
                          r.baseline_id, r.preview_section_id, r.readiness, r.lease_token
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
            spec = ReportSpec.model_validate(job["spec"])
            period = Period.model_validate(job["period"])
            automatic = job["trigger_kind"] == "automatic"
            try:
                readiness, facts = self._observe_sources(spec, period, readiness, started_at, automatic)
            except psycopg.Error:
                unavailable = Probe(state=Readiness.UNKNOWN, reason="source_unavailable")
                readiness = {"source": observe(unavailable, {}, started_at, self.settings.quiet_seconds)}
                facts = None if automatic else {section.id: {} for section in spec.sections}
            if facts is None:
                physical_ready = all(entry["state"] == Readiness.READY for entry in readiness.values())
                interval = self.settings.quiet_seconds if physical_ready else min(self.settings.quiet_seconds, 60)
                next_probe += timedelta(seconds=max(self.settings.poll_seconds, interval))
                state = "waiting"
            else:
                result = generate_report(spec, period, facts, self.gateway)
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
            conn.execute("""
                UPDATE rpt.runs SET state = %s, result = %s, readiness = %s, error_code = %s, next_probe_at = %s,
                                    lease_token = NULL, lease_until = NULL
                WHERE id = %s AND lease_token = %s AND lease_until > %s
            """, (state, Jsonb(result) if result is not None else None, Jsonb(readiness), error_code, next_probe,
                  job["id"], job["lease_token"], finished_at))
        return True

    def _active_owner(self, job):
        with connect(self.settings.report_dsn) as conn:
            active_report = conn.execute("""
                SELECT id FROM rpt.reports WHERE id = %s AND owner_key = %s AND archived_at IS NULL
            """, (job["report_id"], job["owner_key"])).fetchone()
        return bool(active_report and self.owner_status.is_active(job["owner_key"]))

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
            comparison = {"sections": [
                section for section in comparison["sections"] if section["id"] == job["preview_section_id"]
            ]}
        output["diff"] = report_diff(comparison, output)
        output["baseline_run_id"] = str(job["baseline_id"])

    def _observe_sources(self, spec, period, previous, now, automatic):
        with connect(self.settings.source_dsn, source=True) as source_conn:
            items = []
            shifts = period_scopes(spec, period)
            for section in spec.sections:
                bank = self.catalog.resolve(source_conn, section.bank)
                query = section.sources[0]
                for offset, target in shifts[section.id].items():
                    items.append((section.id, offset, Scope(bank, target, query.metric, query.segment)))
            hint = {scope: self.catalog.hinted(source_conn, scope, SourceName.BENCHMARKING)
                    for scope in dict.fromkeys(item[2] for item in items)}
            probes = {scope: self.source.probe(source_conn, scope) for scope in sorted(hint, key=lambda s: not hint[s])}
            with connect(self.settings.report_dsn) as report_conn:
                # Establish the same row-lock order for runs sharing multiple scope keys.
                keys = {scope: opaque_id(SourceName.BENCHMARKING, scope.bank.symbol, str(scope.period),
                                         scope.metric, scope.segment) for scope in probes}
                stabilities = {
                    scope: record_observation(report_conn, keys[scope], probes[scope], now, self.settings.quiet_seconds)
                    for scope in sorted(probes, key=keys.get)
                }
            readiness = {}
            for section_id, offset, scope in items:
                key = f"{section_id}:{offset}"
                readiness[key] = observe(probes[scope], previous.get(key, {}), now, self.settings.quiet_seconds) | {
                    "data_stability": stabilities[scope], "source": SourceName.BENCHMARKING,
                    "bank": scope.bank.symbol, "period": scope.period.model_dump(), "required": True,
                }
            if automatic and not all(entry["stable"] for entry in readiness.values()):
                return readiness, None
            # Read each ready scope from the same read-only snapshot used to probe it.
            by_scope = {scope: self.source.search(source_conn, scope)[0]
                        for scope, probe in probes.items() if probe.state is Readiness.READY}
            facts = {section.id: {} for section in spec.sections}
            for section_id, offset, scope in items:
                if scope in by_scope:
                    facts[section_id][offset] = by_scope[scope]
            return readiness, facts


def main(
    owner_status: OwnerStatusChecker | None = None, credentials: CredentialProvider | None = None
) -> None:
    settings = Settings.from_env()
    logging.basicConfig(level=logging.INFO)
    with httpx.Client(trust_env=False) as client:
        worker = Worker(settings, build_gateway(settings, client, credentials), owner_status)
        logger.info("Report worker started")
        while True:
            try:
                busy = worker.run_one()
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
