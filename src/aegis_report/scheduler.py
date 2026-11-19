import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import psycopg
from psycopg.types.json import Jsonb

from .auth import OwnerStatusChecker, UnwiredOwnerStatus
from .config import Settings
from .db import connect
from .documents import build_sources
from .models import BIG_SIX, Period, ReportSpec
from .readiness import observe
from .reasons import reason_message
from .scopes import probe_scopes, requests_for
from .sources import BankCatalog, Probe, Readiness, opaque_id

logger = logging.getLogger(__name__)


def calendar_ready_at(spec: ReportSpec, period: Period, timezone: str) -> datetime | None:
    banks = {bank for section in spec.sections for bank in section.bank_symbols()}
    if not banks <= set(BIG_SIX):
        return None
    # Briefing pack page 5 confirms November-to-October fiscal years for the core Canadian banks.
    return datetime(period.year, (2, 5, 8, 11)[period.quarter - 1], 1, tzinfo=ZoneInfo(timezone))


def inspect_schedule(settings: Settings, spec: ReportSpec, period: Period, previous: dict,
                     now: datetime, quiet_seconds: float, *, catalog=None, sources=None) -> dict:
    requests = requests_for(spec, period)
    catalog = catalog if catalog is not None else BankCatalog()
    sources = sources if sources is not None else build_sources(settings)
    try:
        with connect(settings.source_dsn, source=True) as conn:
            probes = [(item, probe) for item, _, probe in probe_scopes(conn, requests, catalog, sources)]
    except psycopg.Error:
        unavailable = Probe(state=Readiness.UNKNOWN, reason="source_unavailable")
        probes = [(request, unavailable) for request in requests]
    observations = {}
    for item, probe in probes:
        entry = observe(probe, previous.get(item.key, {}), now, quiet_seconds) | item.describe()
        if entry["stable"]:
            entry["stable_at"] = previous.get(item.key, {}).get("stable_at") or now.isoformat()
        entry["message"] = reason_message(probe.reason) if probe.reason else None
        observations[item.key] = entry
    return observations


def correction_changes(previous: dict, current: dict, observations: dict) -> list[dict]:
    changes = []
    for key in sorted(previous.keys() | current.keys()):
        if previous.get(key) == current.get(key):
            continue
        fields = {name: observations[key][name] for name in ("section_id", "bank", "source", "period") if key in observations}
        change = "added" if key not in previous else "removed" if key not in current else "changed"
        changes.append({"scope": key, "change": change} | fields)
    return changes


class Scheduler:
    def __init__(self, settings: Settings, owner_status: OwnerStatusChecker | None = None,
                 *, clock: Callable[[], datetime] | None = None):
        self.settings = settings
        self.owner_status = owner_status or UnwiredOwnerStatus(settings.local)
        self.clock = clock or (lambda: datetime.now(UTC))
        self.catalog = BankCatalog()
        self.sources = build_sources(settings)

    def poll(self, now: datetime | None = None) -> int:
        now = now or self.clock()
        with connect(self.settings.report_dsn) as conn:
            due = conn.execute("""
                SELECT s.*, r.owner_key, v.spec
                FROM rpt.schedules s
                JOIN rpt.reports r ON r.id = s.report_id
                JOIN rpt.report_versions v ON v.report_id = s.report_id AND v.version = s.version
                WHERE s.enabled AND r.archived_at IS NULL AND s.next_poll_at <= %s
                ORDER BY s.next_poll_at, s.report_id LIMIT 20
            """, (now,)).fetchall()
        dispatched = 0
        for schedule in due:
            dispatched += self._poll_schedule(schedule, now)
        return dispatched

    def _poll_schedule(self, schedule, now):
        report_id = schedule["report_id"]
        target = schedule["dispatch_period"] or schedule["period"]
        spec = ReportSpec.model_validate(schedule["spec"])
        quiet = schedule["quiet_seconds"]
        if quiet is None:
            quiet = self.settings.quiet_seconds
        grace = timedelta(seconds=quiet + 2 * self.settings.schedule_poll_seconds)
        with connect(self.settings.report_dsn) as conn:
            old_periods = conn.execute("""
                SELECT * FROM rpt.schedule_periods WHERE report_id = %s
                  AND (period = %s OR (current_version = %s AND current_kind = 'complete'
                    AND (correction_until >= %s OR (status = 'waiting_for_data' AND correction_until >= %s))))
                ORDER BY period
            """, (report_id, Jsonb(target), schedule["version"], now, now - grace)).fetchall()
        prior = {Period.model_validate(row["period"]): row for row in old_periods}
        periods = dict.fromkeys([Period.model_validate(target), *prior])
        active = self.owner_status.is_active(schedule["owner_key"])
        observations = {
            period: inspect_schedule(
                self.settings, spec, period,
                prior[period]["readiness"] if period in prior and prior[period]["version"] == schedule["version"] else {},
                now, quiet, catalog=self.catalog, sources=self.sources,
            ) if active else None
            for period in periods
        }
        next_poll = now + timedelta(seconds=self.settings.schedule_poll_seconds)
        count = 0
        with connect(self.settings.report_dsn) as conn:
            locked = conn.execute("""
                SELECT archived_at FROM rpt.reports WHERE id = %s FOR UPDATE SKIP LOCKED
            """, (report_id,)).fetchone()
            if not locked or locked["archived_at"] is not None:
                return 0
            fresh = conn.execute("SELECT * FROM rpt.schedules WHERE report_id = %s", (report_id,)).fetchone()
            if (not fresh["enabled"] or fresh["revision"] != schedule["revision"]
                or fresh["next_poll_at"] != schedule["next_poll_at"]
                or (fresh["dispatch_period"] or fresh["period"]) != target):
                return 0
            for period, readiness in observations.items():
                count += self._save_check(conn, schedule, spec, period, readiness, now, next_poll)
            conn.execute("UPDATE rpt.schedules SET next_poll_at = %s WHERE report_id = %s", (next_poll, report_id))
        logger.info("schedule poll lag=%.3fs periods=%s enqueued=%s",
                    max(0.0, (now - schedule["next_poll_at"]).total_seconds()), len(periods), count)
        return count

    def _save_check(self, conn, schedule, spec, period, readiness, now, next_poll):
        report_id, version = schedule["report_id"], schedule["version"]
        encoded = Jsonb(period.model_dump())
        conn.execute("""
            INSERT INTO rpt.schedule_periods
                (report_id, period, version, policy_revision, first_checked_at, checked_at)
            VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (report_id, period) DO NOTHING
        """, (report_id, encoded, version, schedule["revision"], now, now))
        prior = conn.execute("""
            SELECT * FROM rpt.schedule_periods WHERE report_id = %s AND period = %s
        """, (report_id, encoded)).fetchone()
        first = prior["first_checked_at"] if prior["version"] == version else now
        state, reason, queued = "waiting_for_data", "schedule_inputs_pending", 0
        if readiness is None:
            readiness = prior["readiness"]
            state, reason = "failed", "report_or_owner_inactive"
        else:
            earliest = calendar_ready_at(spec, period, schedule["timezone"])
            included = {key: item["marker"] for key, item in readiness.items() if item["stable"]}
            complete = bool(included) and all(key in included for key, item in readiness.items() if item["required"])
            hour_limit = schedule["provisional_after_hours"]
            deadline = max(first, earliest) + timedelta(hours=hour_limit) if earliest and hour_limit is not None else (
                first + timedelta(hours=hour_limit) if hour_limit is not None else None
            )
            eligible = bool(included) and (
                complete or (deadline is not None and now >= deadline and prior["current_kind"] != "complete")
            )
            cutoff = prior["correction_until"] if prior["current_version"] == version else None
            past_cutoff = cutoff is not None and now > cutoff
            tracked_before_cutoff = {
                key for key, entry in readiness.items() if entry["since"]
                and entry["marker"] != prior["current_evidence"].get(key)
                and cutoff is not None and datetime.fromisoformat(entry["since"]) <= cutoff
            }
            post_cutoff_change = any(
                marker != prior["current_evidence"].get(key) and key not in tracked_before_cutoff
                for key, marker in included.items()
            )
            if earliest and now < earliest:
                reason = "schedule_quarter_open"
            elif past_cutoff and (not tracked_before_cutoff or post_cutoff_change):
                state, reason, next_poll = "published", None, None
            elif eligible:
                kind = "complete" if complete else "provisional"
                if (prior["current_run_id"] and prior["current_version"] == version
                    and prior["current_kind"] == kind and prior["current_evidence"] == included):
                    state, reason = ("published" if complete else "provisional"), None
                else:
                    key = opaque_id(kind, {key: [marker, readiness[key]["since"]] for key, marker in included.items()})
                    queued, state, reason = self._dispatch(
                        conn, schedule, prior, encoded, key, kind, included, readiness, now,
                    )
        conn.execute("""
            UPDATE rpt.schedule_periods
            SET version = %s, policy_revision = %s, status = %s, reason = %s, first_checked_at = %s,
                checked_at = %s, next_check_at = %s, readiness = %s
            WHERE report_id = %s AND period = %s
        """, (version, schedule["revision"], state, reason, first, now, next_poll, Jsonb(readiness), report_id, encoded))
        return queued

    @staticmethod
    def _dispatch(conn, schedule, prior, period, evidence_key, kind, evidence, readiness, now):
        report_id, version, revision = schedule["report_id"], schedule["version"], schedule["revision"]
        existing = conn.execute("""
            SELECT id, state, schedule_revision, error_code, publication_state FROM rpt.runs
            WHERE report_id = %s AND version = %s AND period = %s AND evidence_key = %s
              AND schedule_generation IS NOT NULL
        """, (report_id, version, period, evidence_key)).fetchone()
        generation = prior["generation"] + 1
        if existing:
            if existing["publication_state"] in ("published", "provisional", "superseded"):
                state = "published" if prior["current_kind"] == "complete" else "provisional"
                return 0, state, None
            if existing["schedule_revision"] == revision and existing["error_code"] != "report_or_owner_inactive":
                if existing["state"] == "failed":
                    return 0, "failed", existing["error_code"]
                return 0, "ready_to_run", None
            if existing["state"] == "failed" and existing["error_code"] not in (
                "schedule_inactive_or_changed", "report_or_owner_inactive", "schedule_generation_superseded",
            ):
                return 0, "failed", existing["error_code"]
            run_id = existing["id"]
            conn.execute("""
                UPDATE rpt.runs SET state = 'queued', schedule_revision = %s, schedule_generation = %s,
                    next_probe_at = %s, readiness = %s, error_code = NULL, lease_token = NULL, lease_until = NULL,
                    attempt_count = 0 WHERE id = %s
            """, (revision, generation, now, Jsonb(readiness), run_id))
        else:
            explicit = conn.execute("""
                SELECT id FROM rpt.runs WHERE report_id = %s AND version = %s AND period = %s
                  AND schedule_revision = %s AND schedule_generation IS NULL AND state IN ('queued', 'waiting')
                ORDER BY created_at, id LIMIT 1 FOR UPDATE
            """, (report_id, version, period, revision)).fetchone()
            run_id = explicit["id"] if explicit else uuid4()
            conn.execute("""
                INSERT INTO rpt.runs (id, owner_key, mode, trigger_kind, report_id, version, period, spec,
                    next_probe_at, schedule_revision, schedule_generation, evidence_key, evidence_snapshot,
                    publication_kind, readiness)
                VALUES (%s, %s, 'generate', 'automatic', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET state = 'queued', next_probe_at = excluded.next_probe_at,
                    schedule_generation = excluded.schedule_generation, evidence_key = excluded.evidence_key,
                    evidence_snapshot = excluded.evidence_snapshot, publication_kind = excluded.publication_kind,
                    readiness = excluded.readiness, attempt_count = 0
            """, (run_id, schedule["owner_key"], report_id, version, period, Jsonb(schedule["spec"]), now,
                  revision, generation, evidence_key, Jsonb(evidence), kind, Jsonb(readiness)))
        conn.execute("""
            UPDATE rpt.schedule_periods SET latest_run_id = %s, generation = %s
            WHERE report_id = %s AND period = %s
        """, (run_id, generation, report_id, period))
        return 1, "ready_to_run", None


def is_latest_generation(conn, job: dict) -> bool:
    return conn.execute("""
        SELECT 1 FROM rpt.schedule_periods
        WHERE report_id = %s AND period = %s AND generation = %s AND latest_run_id = %s
    """, (job["report_id"], Jsonb(job["period"]), job["schedule_generation"], job["id"])).fetchone() is not None


def publish(conn, job: dict, readiness: dict, now: datetime) -> tuple[UUID, str]:
    report_id, period = job["report_id"], Jsonb(job["period"])
    prior = conn.execute("""
        SELECT * FROM rpt.schedule_periods WHERE report_id = %s AND period = %s
    """, (report_id, period)).fetchone()
    config = conn.execute("""
        SELECT correction_days, coalesce(dispatch_period, period) AS target FROM rpt.schedules WHERE report_id = %s
    """, (report_id,)).fetchone()
    complete = job["publication_kind"] == "complete"
    status = "published" if complete else "provisional"
    earlier = prior["current_run_id"]
    changes = correction_changes(prior["current_evidence"], job["evidence_snapshot"], readiness) if earlier else []
    correction_until = prior["correction_until"]
    if complete and (correction_until is None or prior["current_version"] != job["version"]):
        correction_until = now + timedelta(days=config["correction_days"])
    if earlier:
        conn.execute("UPDATE rpt.runs SET publication_state = 'superseded' WHERE id = %s", (earlier,))
    conn.execute("UPDATE rpt.runs SET publication_state = %s WHERE id = %s", (status, job["id"]))
    conn.execute("""
        UPDATE rpt.schedule_periods SET status = %s, reason = NULL, current_run_id = %s, current_kind = %s, current_version = %s,
            current_evidence = %s, published_at = %s, correction_until = %s, last_correction = %s
        WHERE report_id = %s AND period = %s
    """, (status, job["id"], job["publication_kind"], job["version"], Jsonb(job["evidence_snapshot"]), now, correction_until,
          Jsonb(changes), report_id, period))
    if complete and config["target"] == job["period"]:
        target = Period.model_validate(job["period"])
        if (target.year, target.quarter) < (2200, 4):
            conn.execute("""
                UPDATE rpt.schedules SET dispatch_period = %s, next_poll_at = %s WHERE report_id = %s
            """, (Jsonb(target.shifted(1).model_dump()), now, report_id))
    logger.info("schedule publication state=%s generation=%s supersessions=%s changed_scopes=%s",
                status, job["schedule_generation"], int(bool(earlier)), len(changes))
    return job["id"], status
