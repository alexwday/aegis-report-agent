import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from random import uniform
from threading import Event, Thread
from time import sleep
from uuid import uuid4

import httpx
import psycopg
from psycopg.types.json import Jsonb

from .auth import OwnerStatusChecker, UnwiredOwnerStatus
from .chat_agent import ChatAgent
from .claims import shortlist_passages
from .config import Settings, gateway_tls
from .db import connect
from .diff import report_diff
from .documents import build_sources
from .engine import generate_report
from .gateway import CredentialProvider, GatewayError, ModelGateway, RetryableGatewayError, build_gateway
from .models import Period, ReportSpec
from .notifications import NoOpNotifier, PublicationNotifier
from .readiness import observe, record_observation
from .reasons import reason_message
from .scheduler import Scheduler, is_latest_generation, publish
from .scopes import physical_key, probe_scopes, requests_for
from .sources import BankCatalog, Passage, Probe, Readiness, SourceIssue
from .topics import search_terms

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 3



class Worker:
    def __init__(
        self, settings: Settings, gateway: ModelGateway,
        owner_status: OwnerStatusChecker | None = None, *, clock: Callable[[], datetime] | None = None,
        notifier: PublicationNotifier | None = None,
    ):
        self.settings = settings
        self.gateway = gateway
        self.owner_status = owner_status or UnwiredOwnerStatus(settings.local)
        self.clock = clock or (lambda: datetime.now(UTC))
        self.notifier = notifier or NoOpNotifier()
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
                      AND (schedule_revision IS NULL OR schedule_generation IS NOT NULL)
                    ORDER BY next_probe_at, created_at, id LIMIT 1 FOR UPDATE SKIP LOCKED
                )
                UPDATE rpt.runs r SET state = 'running', lease_token = %s, lease_until = %s,
                                      attempt_count = r.attempt_count + 1
                FROM next_run WHERE r.id = next_run.id
                RETURNING r.id, r.owner_key, r.mode, r.trigger_kind, r.report_id, r.period, r.spec,
                          r.baseline_id, r.preview_section_id, r.readiness, r.lease_token, r.stop_after, r.schedule_revision,
                          r.schedule_generation, r.evidence_snapshot, r.publication_kind, r.attempt_count, r.version
            """, (now, now, now, uuid4(), now + timedelta(minutes=3))).fetchone()

    def run_one(self, now: datetime | None = None) -> bool:
        started_at = now or self.clock()
        job = self._claim(started_at)
        if not job:
            return False
        result, state, error_code = None, "failed", None
        readiness = job["readiness"]
        next_probe = started_at
        managed = job["schedule_generation"] is not None
        try:
            if job["mode"] == "generate" and not self._active_owner(job):
                raise SourceIssue(Readiness.UNKNOWN, "report_or_owner_inactive")
            if job["schedule_revision"] is not None:
                with connect(self.settings.report_dsn) as conn:
                    if not self._active_schedule(conn, job):
                        raise SourceIssue(Readiness.UNKNOWN, "schedule_inactive_or_changed")
                    if managed and not is_latest_generation(conn, job):
                        raise SourceIssue(Readiness.UNKNOWN, "schedule_generation_superseded")
            spec = ReportSpec.model_validate(job["spec"])
            period = Period.model_validate(job["period"])
            automatic = job["trigger_kind"] == "automatic"
            requests = requests_for(spec, period)
            try:
                readiness, evidence = self._observe_sources(
                    requests, readiness, started_at, automatic, pinned=job["evidence_snapshot"],
                )
            except psycopg.Error:
                if managed:
                    raise SourceIssue(Readiness.UNKNOWN, "source_unavailable") from None
                unavailable = Probe(state=Readiness.UNKNOWN, reason="source_unavailable")
                readiness = {
                    item.key: observe(unavailable, {}, started_at, self.settings.quiet_seconds) | item.describe()
                    for item in requests
                }
                evidence = None if automatic else {section.id: [] for section in spec.sections}
            for entry in readiness.values():
                entry["message"] = reason_message(entry.get("reason") or entry.get("evidence_state")) if (
                    entry.get("reason") or entry.get("evidence_state")
                ) else None
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
                if managed:
                    result["publication"] = job["publication_kind"]
                    self._verify_snapshot(requests, job["evidence_snapshot"])
                    if not self._active_owner(job):
                        raise SourceIssue(Readiness.UNKNOWN, "report_or_owner_inactive")
                if job["baseline_id"] is not None:
                    self._apply_diff(job, result)
                state = "succeeded"
        except (GatewayError, SourceIssue, psycopg.Error) as exc:
            result = None
            error_code = exc.reason if isinstance(exc, SourceIssue) else (
                "source_unavailable" if isinstance(exc, psycopg.Error) else str(exc)
            )
            transient = isinstance(exc, (RetryableGatewayError, psycopg.Error)) or error_code == "source_unavailable"
            if managed and transient and job["attempt_count"] < MAX_ATTEMPTS:
                state = "queued"
                next_probe = (now or self.clock()) + timedelta(seconds=(2 ** job["attempt_count"]) + uniform(0.1, 0.7))
            elif managed and transient:
                error_code = "attempts_exhausted"
        except (ValueError, ArithmeticError):
            error_code = "invalid_report_input"

        finished_at = now or self.clock()
        published = self._finalize(job, state, result, readiness, error_code, next_probe, finished_at)
        if published:
            self.notifier.published(*published)
        return True

    def _finalize(self, job, state, result, readiness, error_code, next_probe, finished_at):
        managed = job["schedule_generation"] is not None
        with connect(self.settings.report_dsn) as conn:
            if job["schedule_revision"] is not None:
                lock = "UPDATE" if managed else "SHARE"
                conn.execute(f"SELECT id FROM rpt.reports WHERE id = %s FOR {lock}", (job["report_id"],))
                if state in ("succeeded", "queued") and not self._active_schedule(conn, job):
                    state, result, error_code = "failed", None, "schedule_inactive_or_changed"
                if state in ("succeeded", "queued") and managed and not is_latest_generation(conn, job):
                    state, result, error_code = "failed", None, "schedule_generation_superseded"
            updated = conn.execute("""
                UPDATE rpt.runs SET state = %s, result = %s, readiness = %s, error_code = %s, next_probe_at = %s,
                                    lease_token = NULL, lease_until = NULL,
                                    attempt_count = CASE WHEN %s = 'waiting' THEN 0 ELSE attempt_count END
                WHERE id = %s AND lease_token = %s AND lease_until > %s RETURNING id
            """, (state, Jsonb(result) if result is not None else None, Jsonb(readiness), error_code, next_probe,
                  state, job["id"], job["lease_token"], finished_at)).fetchone()
            if not updated:
                return None
            if error_code:
                logger.info("report attempt state=%s failure_code=%s", state, error_code)
            if managed and state == "succeeded":
                return publish(conn, job, readiness, finished_at)
            if managed and is_latest_generation(conn, job):
                changed = error_code == "schedule_evidence_changed"
                status = "ready_to_run" if state == "queued" else "waiting_for_data" if changed else "failed"
                conn.execute("""
                    UPDATE rpt.schedule_periods SET status = %s, reason = %s, next_check_at = %s
                    WHERE report_id = %s AND period = %s
                """, (status, error_code, next_probe if state == "queued" else finished_at if changed else None,
                      job["report_id"], Jsonb(job["period"])))
                if changed:
                    conn.execute("""
                        UPDATE rpt.schedules SET next_poll_at = least(next_poll_at, %s) WHERE report_id = %s
                    """, (finished_at, job["report_id"]))
        return None

    def _verify_snapshot(self, requests, pinned):
        with connect(self.settings.source_dsn, source=True) as conn:
            for item, _scope, probe in probe_scopes(
                conn, [item for item in requests if item.key in pinned], self.catalog, self.sources,
            ):
                if probe.state is not Readiness.READY or probe.marker != pinned[item.key]:
                    raise SourceIssue(Readiness.INCOMPLETE, "schedule_evidence_changed")

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

    def _observe_sources(self, requests, previous, now, automatic, *, pinned=None):
        vectors = self._vectors(requests, previous, automatic)
        with connect(self.settings.source_dsn, source=True) as source_conn:
            items, readiness, probes = [], {}, {}
            for item, scope, probe in probe_scopes(source_conn, requests, self.catalog, self.sources):
                if pinned is not None:
                    entry = observe(probe, previous.get(item.key, {}), now, 0) | item.describe()
                    entry["stable"] = item.key in pinned
                    entry["data_stability"] = "stable" if entry["stable"] else previous.get(item.key, {}).get(
                        "data_stability", "unknown",
                    )
                    readiness[item.key] = entry
                    if item.key in pinned:
                        if probe.state is not Readiness.READY or probe.marker != pinned[item.key]:
                            raise SourceIssue(Readiness.INCOMPLETE, "schedule_evidence_changed")
                        query = (item.source, scope)
                        probes[query] = probe
                        items.append((item, query))
                elif scope is None:
                    readiness[item.key] = observe(probe, {}, now, self.settings.quiet_seconds) | item.describe()
                else:
                    query = (item.source, scope)
                    probes[query] = probe
                    items.append((item, query))
            if pinned is None:
                keys = {query: physical_key(*query) for query in probes}
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
                    if pinned is not None:
                        raise SourceIssue(hits.state, hits.reason)
                    if automatic and item.selector.required:
                        return readiness, None
                else:
                    readiness[item.key]["evidence_state"] = "matched" if hits else "no_match"
                    evidence[item.section_id].extend(hits)
            return readiness, evidence


def poll_schedules(scheduler: Scheduler, stop: Event) -> None:
    while not stop.is_set():
        try:
            scheduler.poll()
        except psycopg.Error:
            logger.warning("Schedule polling database unavailable")
        stop.wait(scheduler.settings.schedule_poll_seconds)


def main(
    owner_status: OwnerStatusChecker | None = None, credentials: CredentialProvider | None = None
) -> None:
    settings = Settings.from_env()
    logging.basicConfig(level=logging.INFO)
    with httpx.Client(trust_env=False, verify=gateway_tls()) as client:
        gateway = build_gateway(settings, client, credentials)
        worker = Worker(settings, gateway, owner_status)
        chat = ChatAgent(settings, gateway)
        scheduler = Scheduler(settings, owner_status)
        stop = Event()
        poller = Thread(target=poll_schedules, args=(scheduler, stop), name="schedule-poller", daemon=True)
        poller.start()
        logger.info("Report worker and schedule poller started")
        try:
            while True:
                try:
                    busy = chat.run_one()
                    busy = worker.run_one() or busy
                except psycopg.Error:
                    logger.warning("Database unavailable during worker attempt")
                    busy = False
                if not busy:
                    sleep(settings.poll_seconds)
        finally:
            stop.set()
            poller.join(timeout=2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
