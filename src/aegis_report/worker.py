import logging
from datetime import UTC, datetime, timedelta
from time import sleep

import httpx
import psycopg
from psycopg.types.json import Jsonb

from .auth import OwnerStatusChecker, UnwiredOwnerStatus
from .config import Settings
from .db import connect
from .engine import generate_report, report_diff
from .gateway import CredentialProvider, GatewayError, ModelGateway, build_gateway
from .models import Period, ReportSpec, SourceName
from .repository import period_scopes
from .sources import BankCatalog, BenchmarkingSource, Probe, Readiness, Scope, SourceIssue

logger = logging.getLogger(__name__)


def observe(probe: Probe, previous: dict, now: datetime, quiet_seconds: float) -> dict:
    observation = probe.model_dump(mode="json") | {"since": None, "stable": False}
    if probe.state is not Readiness.READY or probe.marker is None:
        return observation
    if previous.get("since") and previous.get("marker") == probe.marker:
        since = datetime.fromisoformat(previous["since"])
        observation.update(since=since.isoformat(), stable=(now - since).total_seconds() >= quiet_seconds)
    else:
        observation["since"] = now.isoformat()
    return observation


class Worker:
    def __init__(self, settings: Settings, gateway: ModelGateway, owner_status: OwnerStatusChecker | None = None):
        self.settings = settings
        self.gateway = gateway
        self.owner_status = owner_status or UnwiredOwnerStatus(settings.local)
        self.catalog = BankCatalog()
        self.source = BenchmarkingSource(settings.currencies)

    def run_one(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(UTC)
        with connect(self.settings.report_dsn) as conn:
            conn.execute("DELETE FROM rpt.runs WHERE mode = 'preview' AND expires_at <= %s", (now,))
            # Keep the G1 claim transactional. A crash releases the row and rolls back the attempt.
            job = conn.execute("""
                SELECT id, owner_key, mode, report_id, period, spec, baseline_id, preview_section_id, readiness
                FROM rpt.runs
                WHERE state IN ('queued', 'waiting') AND next_probe_at <= %s
                  AND (expires_at IS NULL OR expires_at > %s)
                ORDER BY next_probe_at, created_at, id LIMIT 1 FOR UPDATE SKIP LOCKED
            """, (now, now)).fetchone()
            if not job:
                return False
            try:
                if job["mode"] == "generate":
                    active_report = conn.execute("""
                        SELECT id FROM rpt.reports
                        WHERE id = %s AND owner_key = %s AND archived_at IS NULL
                    """, (job["report_id"], job["owner_key"])).fetchone()
                    if not active_report or not self.owner_status.is_active(job["owner_key"]):
                        self._fail(conn, job, "report_or_owner_inactive")
                        return True
                spec = ReportSpec.model_validate(job["spec"])
                period = Period.model_validate(job["period"])
                try:
                    readiness, facts = self._observe_sources(spec, period, job["readiness"], now)
                except psycopg.Error:
                    unavailable = Probe(state=Readiness.UNKNOWN, reason="source_unavailable")
                    readiness = {"source": observe(unavailable, {}, now, self.settings.quiet_seconds)}
                    facts = None
                if facts is None:
                    self._wait(conn, job, readiness, now)
                    return True
                output = generate_report(spec, period, facts, self.gateway)
                if job["baseline_id"] is not None:
                    baseline = conn.execute("""
                        SELECT result FROM rpt.runs
                        WHERE id = %s AND owner_key = %s AND mode = 'generate' AND state = 'succeeded'
                    """, (job["baseline_id"], job["owner_key"])).fetchone()
                    if not baseline:
                        self._fail(conn, job, "baseline_unavailable")
                        return True
                    comparison = baseline["result"]
                    if job["preview_section_id"]:
                        comparison = {"sections": [
                            section for section in comparison["sections"] if section["id"] == job["preview_section_id"]
                        ]}
                    output["diff"] = report_diff(comparison, output)
                    output["baseline_run_id"] = str(job["baseline_id"])
                conn.execute("""
                    UPDATE rpt.runs SET state = 'succeeded', result = %s, readiness = %s WHERE id = %s
                """, (Jsonb(output), Jsonb(readiness), job["id"]))
            except GatewayError as exc:
                self._fail(conn, job, str(exc))
            except SourceIssue as exc:
                self._fail(conn, job, exc.reason)
            except (ValueError, ArithmeticError):
                self._fail(conn, job, "invalid_report_input")
            return True

    def _observe_sources(self, spec, period, previous, now):
        with connect(self.settings.source_dsn, source=True) as source_conn:
            items = []
            shifts = period_scopes(spec, period)
            for section in spec.sections:
                bank = self.catalog.resolve(source_conn, section.bank)
                query = section.sources[0]
                for offset, target in shifts[section.id].items():
                    scope = Scope(bank, target, query.metric, query.segment)
                    items.append((section.id, offset, scope))
            hint = {
                scope: self.catalog.hinted(source_conn, scope, SourceName.BENCHMARKING)
                for scope in dict.fromkeys(item[2] for item in items)
            }
            probes = {scope: self.source.probe(source_conn, scope) for scope in sorted(hint, key=lambda s: not hint[s])}
            readiness = {}
            for section_id, offset, scope in items:
                key = f"{section_id}:{offset}"
                readiness[key] = observe(probes[scope], previous.get(key, {}), now, self.settings.quiet_seconds)
            if not all(entry["stable"] for entry in readiness.values()):
                return readiness, None
            # Reuse the same upstream snapshot for readiness and retrieval.
            by_scope = {scope: self.source.search(source_conn, scope)[0] for scope in probes}
            facts = {section.id: {} for section in spec.sections}
            for section_id, offset, scope in items:
                facts[section_id][offset] = by_scope[scope]
            return readiness, facts

    def _wait(self, conn, job, readiness, now):
        physical_ready = all(entry["state"] == Readiness.READY for entry in readiness.values())
        interval = self.settings.quiet_seconds if physical_ready else min(self.settings.quiet_seconds, 60)
        delay = max(self.settings.poll_seconds, interval)
        conn.execute("""
            UPDATE rpt.runs SET state = 'waiting', readiness = %s, next_probe_at = %s WHERE id = %s
        """, (Jsonb(readiness), now + timedelta(seconds=delay), job["id"]))

    def _fail(self, conn, job, code):
        conn.execute("UPDATE rpt.runs SET state = 'failed', error_code = %s WHERE id = %s", (code, job["id"]))


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
