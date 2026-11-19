from datetime import datetime, timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException
from psycopg.types.json import Jsonb

from .chat_models import apply_operations
from .db import connect
from .models import (
    DraftPatch,
    Period,
    PreviewRequest,
    ReportClone,
    ReportSpec,
    RunRequest,
    ScheduleWrite,
    TemplateCreate,
)


class Reports:
    def __init__(self, dsn: str, retention_days: int):
        self.dsn = dsn
        self.preview_retention = timedelta(days=retention_days)

    def _draft(self, conn, owner, draft_id, *, lock=False):
        # The suffix is selected from application-owned constants.
        lock_sql = " FOR UPDATE" if lock else ""
        row = conn.execute("""
            SELECT id, report_id, base_version, head_at_start, revision, spec FROM rpt.drafts
            WHERE id = %s AND owner_key = %s
        """ + lock_sql, (draft_id, owner)).fetchone()
        if not row:
            raise HTTPException(404, "draft_not_found")
        return row

    def _assert_revision(self, row, revision):
        if row["revision"] != revision:
            raise HTTPException(409, "stale_draft_revision")

    def _insert_draft(self, conn, owner, spec, report_id=None, version=None, head=None):
        return conn.execute("""
            INSERT INTO rpt.drafts (id, owner_key, revision, spec, report_id, base_version, head_at_start)
            VALUES (%s, %s, 1, %s, %s, %s, %s)
            RETURNING id, report_id, base_version, head_at_start, revision, spec
        """, (uuid4(), owner, Jsonb(spec), report_id, version, head)).fetchone()

    def create_draft(self, owner: bytes, spec: ReportSpec):
        with connect(self.dsn) as conn:
            return self._insert_draft(conn, owner, spec.model_dump(mode="json"))

    def get_draft(self, owner: bytes, draft_id: UUID):
        with connect(self.dsn) as conn:
            return self._draft(conn, owner, draft_id)

    def patch(self, owner: bytes, draft_id: UUID, patch: DraftPatch):
        with connect(self.dsn) as conn:
            row = self._draft(conn, owner, draft_id, lock=True)
            self._assert_revision(row, patch.revision)
            spec = ReportSpec.model_validate(row["spec"])
            sections = {section.id: section for section in spec.sections}
            exists = patch.section.id in sections
            if patch.op == "add_section" and exists:
                raise HTTPException(409, "section_already_exists")
            if patch.op == "replace_section" and not exists:
                raise HTTPException(404, "section_not_found")
            if patch.op == "add_section" and len(sections) >= 6:
                raise HTTPException(422, "section_limit")
            sections[patch.section.id] = patch.section
            try:
                spec = ReportSpec(title=spec.title, sections=list(sections.values()))
            except ValueError as exc:
                raise HTTPException(422, "invalid_report_scope") from exc
            return self._write_draft(conn, owner, draft_id, spec)

    def apply_operations(self, owner, draft_id, patch):
        with connect(self.dsn) as conn:
            draft = self._draft(conn, owner, draft_id, lock=True)
            self._assert_revision(draft, patch.revision)
            try:
                spec = apply_operations(ReportSpec.model_validate(draft["spec"]), patch.operations)
            except ValueError as exc:
                raise HTTPException(422, "invalid_tool_arguments_or_patch") from exc
            return self._write_draft(conn, owner, draft_id, spec)

    def _write_draft(self, conn, owner, draft_id, spec):
        return conn.execute("""
            UPDATE rpt.drafts SET spec = %s, revision = revision + 1 WHERE id = %s AND owner_key = %s
            RETURNING id, report_id, base_version, head_at_start, revision, spec
        """, (Jsonb(spec.model_dump(mode="json")), draft_id, owner)).fetchone()

    def list_reports(self, owner: bytes, archived: bool, limit: int, offset: int):
        with connect(self.dsn) as conn:
            return conn.execute("""
                SELECT id, title, head, archived_at, created_at FROM rpt.reports
                WHERE owner_key = %s AND (archived_at IS NOT NULL) = %s
                ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s
            """, (owner, archived, limit, offset)).fetchall()

    def _report(self, conn, owner, report_id, *, active=False, lock=False):
        locking = " FOR UPDATE" if lock else ""
        report = conn.execute("""
            SELECT id, title, head, archived_at, created_at FROM rpt.reports
            WHERE owner_key = %s AND id = %s
        """ + locking, (owner, report_id)).fetchone()
        if report is None:
            raise HTTPException(404, "report_not_found")
        if active and report["archived_at"] is not None:
            raise HTTPException(409, "report_archived")
        return report

    def get_report(self, owner: bytes, report_id: UUID):
        with connect(self.dsn) as conn:
            return self._report(conn, owner, report_id)

    def rename_report(self, owner: bytes, report_id: UUID, title: str):
        with connect(self.dsn) as conn:
            self._report(conn, owner, report_id, lock=True)
            return conn.execute("""
                UPDATE rpt.reports SET title = %s WHERE id = %s AND owner_key = %s
                RETURNING id, title, head, archived_at, created_at
            """, (title, report_id, owner)).fetchone()

    def archive_report(self, owner: bytes, report_id: UUID, archived: bool):
        with connect(self.dsn) as conn:
            self._report(conn, owner, report_id, lock=True)
            updated = conn.execute("""
                UPDATE rpt.reports SET archived_at = CASE WHEN %s THEN coalesce(archived_at, now()) END
                WHERE id = %s AND owner_key = %s
                RETURNING id, title, head, archived_at, created_at
            """, (archived, report_id, owner)).fetchone()
            if archived:
                conn.execute("""
                    UPDATE rpt.schedules SET enabled = false, revision = revision + 1
                    WHERE report_id = %s AND enabled
                """, (report_id,))
                self._pause_periods(conn, report_id)
                self._close_pending_schedule_requests(conn, report_id)
            return updated

    def _report_version(self, conn, owner, report_id, version, *, active=True):
        self._report(conn, owner, report_id, active=active)
        row = conn.execute("""
            SELECT spec FROM rpt.report_versions WHERE report_id = %s AND version = %s
        """, (report_id, version)).fetchone()
        if not row:
            raise HTTPException(404, "report_version_not_found")
        return row

    def get_version(self, owner: bytes, report_id: UUID, version: int):
        with connect(self.dsn) as conn:
            return self._report_version(conn, owner, report_id, version, active=False)["spec"]

    def list_versions(self, owner: bytes, report_id: UUID, limit: int, offset: int):
        with connect(self.dsn) as conn:
            self._report(conn, owner, report_id)
            return conn.execute("""
                SELECT version, spec->>'title' AS title, created_at FROM rpt.report_versions
                WHERE report_id = %s ORDER BY version DESC LIMIT %s OFFSET %s
            """, (report_id, limit, offset)).fetchall()

    def draft_from_version(self, owner: bytes, report_id: UUID, version: int):
        with connect(self.dsn) as conn:
            report = self._report(conn, owner, report_id, active=True, lock=True)
            spec = self._report_version(conn, owner, report_id, version)["spec"]
            return self._insert_draft(conn, owner, spec, report_id, version, report["head"])

    def clone_report(self, owner: bytes, report_id: UUID, request: ReportClone):
        with connect(self.dsn) as conn:
            original = self._report(conn, owner, report_id)
            spec = self._report_version(
                conn, owner, report_id, request.version or original["head"], active=False,
            )["spec"]
            title = request.title or f"{original['title'][:95]} copy"
            clone = conn.execute("""
                INSERT INTO rpt.reports (id, owner_key, head, title) VALUES (%s, %s, 1, %s)
                RETURNING id, title, head, created_at, archived_at
            """, (uuid4(), owner, title)).fetchone()
            self._insert_version(conn, clone["id"], 1, spec | {"title": title})
            return clone

    def _insert_version(self, conn, report_id, version, spec):
        conn.execute("""
            INSERT INTO rpt.report_versions (report_id, version, spec) VALUES (%s, %s, %s)
        """, (report_id, version, Jsonb(spec)))

    def list_personal_templates(self, owner: bytes):
        with connect(self.dsn) as conn:
            return conn.execute("""
                SELECT id::text AS id, title, 'personal' AS kind FROM rpt.personal_templates
                WHERE owner_key = %s ORDER BY created_at DESC, id DESC
            """, (owner,)).fetchall()

    def get_personal_template(self, owner: bytes, template_id: str):
        try:
            identifier = UUID(template_id)
        except ValueError as exc:
            raise HTTPException(404, "template_not_found") from exc
        with connect(self.dsn) as conn:
            row = conn.execute("""
                SELECT spec FROM rpt.personal_templates WHERE id = %s AND owner_key = %s
            """, (identifier, owner)).fetchone()
            if not row:
                raise HTTPException(404, "template_not_found")
            return ReportSpec.model_validate(row["spec"])

    def create_personal_template(self, owner: bytes, request: TemplateCreate):
        with connect(self.dsn) as conn:
            report = self._report(conn, owner, request.report_id)
            snapshot = self._report_version(
                conn, owner, request.report_id, request.version or report["head"], active=False,
            )["spec"] | {"title": request.title}
            return conn.execute("""
                INSERT INTO rpt.personal_templates (id, owner_key, title, spec) VALUES (%s, %s, %s, %s)
                RETURNING id::text AS id, title, 'personal' AS kind
            """, (uuid4(), owner, request.title, Jsonb(snapshot))).fetchone()

    def save(self, owner: bytes, draft_id: UUID, revision: int):
        with connect(self.dsn) as conn:
            draft = self._draft(conn, owner, draft_id, lock=True)
            self._assert_revision(draft, revision)
            report_id, expected_head = draft["report_id"], draft["head_at_start"]
            if report_id is None:
                report_id, version = uuid4(), 1
                conn.execute("""
                    INSERT INTO rpt.reports (id, owner_key, head, title) VALUES (%s, %s, 1, %s)
                """, (report_id, owner, draft["spec"]["title"]))
            else:
                latest = conn.execute("""
                    UPDATE rpt.reports SET head = head + 1
                    WHERE id = %s AND owner_key = %s AND archived_at IS NULL AND head = %s
                    RETURNING head
                """, (report_id, owner, expected_head)).fetchone()
                if latest is None:
                    raise HTTPException(409, "stale_or_archived_report")
                version = latest["head"]
            self._insert_version(conn, report_id, version, draft["spec"])
            conn.execute("""
                UPDATE rpt.drafts SET report_id = %s, base_version = %s, head_at_start = %s, revision = revision + 1
                WHERE id = %s AND owner_key = %s
            """, (report_id, version, version, draft_id, owner))
            return {"report_id": report_id, "version": version, "draft_revision": revision + 1}

    def _run(self, conn, owner, run_id):
        run = conn.execute("""
            SELECT id, mode, trigger_kind, stop_after, report_id, version, draft_revision, period, state, result, error_code, readiness
            FROM rpt.runs WHERE id = %s AND owner_key = %s AND (expires_at IS NULL OR expires_at > now())
        """, (run_id, owner)).fetchone()
        if not run:
            raise HTTPException(404, "run_not_found")
        return run

    def get_run(self, owner: bytes, run_id: UUID):
        with connect(self.dsn) as conn:
            return self._run(conn, owner, run_id)

    def enqueue_run(self, owner: bytes, report_id: UUID, request: RunRequest):
        return self._enqueue_generation(owner, report_id, request, "manual")

    def enqueue_automatic(self, owner: bytes, report_id: UUID, request: RunRequest, due_at: datetime):
        """Internal entry point for automatic generation. The scheduler supplies the due time."""
        return self._enqueue_generation(owner, report_id, request, "automatic", due_at)

    def _enqueue_generation(self, owner, report_id, request, trigger_kind, due_at=None):
        with connect(self.dsn) as conn:
            return self._insert_generation(conn, owner, report_id, request, trigger_kind, due_at)

    def _insert_generation(self, conn, owner, report_id, request, trigger_kind, due_at=None, schedule_revision=None):
        version = self._report_version(conn, owner, report_id, request.version)
        period = request.period.model_dump(mode="json")
        job = conn.execute("""
            INSERT INTO rpt.runs
                (id, owner_key, mode, trigger_kind, report_id, version, period, spec, idempotency_key, next_probe_at, schedule_revision)
            VALUES (%s, %s, 'generate', %s, %s, %s, %s, %s, %s, coalesce(%s, now()), %s)
            ON CONFLICT (owner_key, idempotency_key) DO NOTHING
            RETURNING id
        """, (uuid4(), owner, trigger_kind, report_id, request.version, Jsonb(period), Jsonb(version["spec"]),
              request.request_key, due_at, schedule_revision)).fetchone()
        if job:
            return job
        previous = conn.execute("""
            SELECT id, report_id, version, period, trigger_kind, schedule_revision FROM rpt.runs
            WHERE owner_key = %s AND idempotency_key = %s
        """, (owner, request.request_key)).fetchone()
        if (previous["report_id"], previous["version"], previous["period"], previous["trigger_kind"], previous["schedule_revision"],
        ) != (
            report_id, request.version, period, trigger_kind, schedule_revision
        ):
            raise HTTPException(409, "request_key_reused")
        return {"id": previous["id"]}

    def _schedule(self, conn, report_id):
        return conn.execute("""
            SELECT report_id, version, period, enabled, revision, timezone, quiet_seconds, correction_days,
                   provisional_after_hours, coalesce(dispatch_period, period) AS next_period
            FROM rpt.schedules WHERE report_id = %s
        """, (report_id,)).fetchone()

    def get_schedule(self, owner: bytes, report_id: UUID):
        with connect(self.dsn) as conn:
            self._report(conn, owner, report_id)
            schedule = self._schedule(conn, report_id)
            if schedule is None:
                raise HTTPException(404, "schedule_not_found")
            return schedule

    def schedule_history(self, owner: bytes, report_id: UUID, limit: int, offset: int):
        with connect(self.dsn) as conn:
            self._report(conn, owner, report_id)
            return conn.execute("""
                SELECT id, period, version, schedule_revision, state, error_code, created_at,
                       schedule_generation AS generation, publication_state
                FROM rpt.runs WHERE owner_key = %s AND report_id = %s AND schedule_revision IS NOT NULL
                ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s
            """, (owner, report_id, limit, offset)).fetchall()

    def schedule_periods(self, owner: bytes, report_id: UUID, limit: int, offset: int):
        with connect(self.dsn) as conn:
            self._report(conn, owner, report_id)
            return conn.execute("""
                SELECT p.period, p.version, p.generation, r.state AS run_state,
                       CASE WHEN p.status = 'ready_to_run' AND r.state IN ('running', 'failed') THEN r.state
                            ELSE p.status END AS state,
                       coalesce(p.reason, CASE WHEN p.status = 'ready_to_run' THEN r.error_code END) AS reason,
                       CASE WHEN p.status = 'published' AND p.correction_until < now()
                            THEN NULL ELSE p.next_check_at END AS next_check_at,
                       p.checked_at, p.current_run_id, p.current_kind, p.published_at,
                       p.correction_until, p.last_correction, p.readiness
                FROM rpt.schedule_periods p LEFT JOIN rpt.runs r ON r.id = p.latest_run_id
                WHERE p.report_id = %s
                ORDER BY (p.period->>'year')::integer DESC, (p.period->>'quarter')::integer DESC
                LIMIT %s OFFSET %s
            """, (report_id, limit, offset)).fetchall()

    @staticmethod
    def _pause_periods(conn, report_id):
        conn.execute("""
            UPDATE rpt.schedule_periods SET status = 'failed', reason = 'schedule_inactive_or_changed',
                next_check_at = NULL
            WHERE report_id = %s AND status IN ('waiting_for_data', 'ready_to_run')
        """, (report_id,))

    @staticmethod
    def _close_pending_schedule_requests(conn, report_id):
        conn.execute("""
            UPDATE rpt.runs SET state = 'failed', error_code = 'schedule_inactive_or_changed'
            WHERE report_id = %s AND schedule_revision IS NOT NULL AND schedule_generation IS NULL
              AND state IN ('queued', 'waiting')
        """, (report_id,))

    def put_schedule(self, owner: bytes, report_id: UUID, request: ScheduleWrite):
        with connect(self.dsn) as conn:
            self._report(conn, owner, report_id, active=True, lock=True)
            self._report_version(conn, owner, report_id, request.version)
            current = self._schedule(conn, report_id)
            if request.expected_revision != (current["revision"] if current else None):
                raise HTTPException(409, "stale_schedule_revision")
            conn.execute("""
                INSERT INTO rpt.schedules (report_id, version, period, enabled, revision, timezone, quiet_seconds,
                                           correction_days, provisional_after_hours)
                VALUES (%s, %s, %s, %s, 1, %s, %s, %s, %s)
                ON CONFLICT (report_id) DO UPDATE
                SET version = excluded.version, period = excluded.period, enabled = excluded.enabled,
                    timezone = excluded.timezone, quiet_seconds = excluded.quiet_seconds,
                    correction_days = excluded.correction_days, provisional_after_hours = excluded.provisional_after_hours,
                    dispatch_period = CASE WHEN rpt.schedules.period = excluded.period
                                           THEN rpt.schedules.dispatch_period END,
                    revision = rpt.schedules.revision + 1, next_poll_at = now()
            """, (report_id, request.version, Jsonb(request.period.model_dump()), request.enabled, request.timezone,
                  request.quiet_seconds, request.correction_days, request.provisional_after_hours))
            if current:
                self._close_pending_schedule_requests(conn, report_id)
            if not request.enabled:
                self._pause_periods(conn, report_id)
            return self._schedule(conn, report_id)

    def enqueue_schedule(self, owner: bytes, report_id: UUID):
        with connect(self.dsn) as conn:
            self._report(conn, owner, report_id, active=True, lock=True)
            schedule = self._schedule(conn, report_id)
            if schedule is None or not schedule["enabled"]:
                raise HTTPException(409, "schedule_inactive")
            period = Period.model_validate(schedule["next_period"])
            existing = conn.execute("""
                SELECT latest_run_id FROM rpt.schedule_periods WHERE report_id = %s AND period = %s
                  AND version = %s AND latest_run_id IS NOT NULL
            """, (report_id, Jsonb(period.model_dump()), schedule["version"])).fetchone()
            if existing:
                return {"id": existing["latest_run_id"]}
            request = RunRequest(
                version=schedule["version"], period=period,
                request_key=f"schedule:{report_id}:{schedule['revision']}:{period.year}:{period.quarter}",
            )
            conn.execute("UPDATE rpt.schedules SET next_poll_at = now() WHERE report_id = %s", (report_id,))
            queued = self._insert_generation(
                conn, owner, report_id, request, "automatic", schedule_revision=schedule["revision"],
            )
            conn.execute("""
                UPDATE rpt.runs SET state = 'waiting'
                WHERE id = %s AND state = 'queued' AND schedule_generation IS NULL
            """, (queued["id"],))
            return queued

    def enqueue_preview(self, owner: bytes, draft_id: UUID, request: PreviewRequest):
        with connect(self.dsn) as conn:
            draft = self._draft(conn, owner, draft_id)
            return self._insert_preview(conn, owner, draft, request)

    def _insert_preview(self, conn, owner, draft, request, *, proposed_spec=None):
        self._assert_revision(draft, request.revision)
        period = request.period.model_dump(mode="json")
        if request.baseline_run_id is not None:
            baseline = self._run(conn, owner, request.baseline_run_id)
            if (
                baseline["mode"] != "generate" or baseline["state"] != "succeeded"
                or (baseline["report_id"], baseline["version"]) != (draft["report_id"], draft["base_version"])
                or baseline["period"] != period
            ):
                raise HTTPException(409, "baseline_must_match_saved_version_and_period")
        spec = proposed_spec or ReportSpec.model_validate(draft["spec"])
        if request.section_id is not None:
            selected = [section for section in spec.sections if section.id == request.section_id]
            if not selected:
                raise HTTPException(404, "section_not_found")
            if request.stop_after is not None and selected[0].mode != "staged":
                raise HTTPException(422, "gather_only_requires_staged_section")
            spec = ReportSpec(title=spec.title, sections=selected)
        return conn.execute("""
            INSERT INTO rpt.runs
                (id, owner_key, mode, draft_revision, preview_section_id, baseline_id, period, spec, stop_after, expires_at)
            VALUES (%s, %s, 'preview', %s, %s, %s, %s, %s, %s, now() + %s)
            RETURNING id
        """, (uuid4(), owner, draft["revision"], request.section_id, request.baseline_run_id, Jsonb(period),
              Jsonb(spec.model_dump(mode="json")), request.stop_after, self.preview_retention)).fetchone()

    def output(self, owner: bytes, run_id: UUID):
        row = self.get_run(owner, run_id)
        if row["state"] != "succeeded":
            raise HTTPException(409, "run_output_not_ready")
        return row["result"]

    def pdf_output(self, owner: bytes, run_id: UUID):
        row = self.get_run(owner, run_id)
        if row["mode"] != "generate" or row["state"] != "succeeded":
            raise HTTPException(409, "finished_report_required")
        return row["result"]

    def citation(self, owner: bytes, run_id: UUID, evidence_id: str, *, detail: bool = False):
        result = self.output(owner, run_id)
        for section in result["sections"]:
            for row in section["rows"]:
                if row["citation"]["id"] == evidence_id:
                    excerpt = " ".join(str(value) for value in (
                        row["metric"], row["actual"], row["unit"], row["currency"],
                    ) if value is not None)
                    return citation_result(row["citation"], excerpt, detail)
            for claim in section.get("claims", []):
                for citation in claim["citations"]:
                    if citation["id"] == evidence_id:
                        return citation_result(citation, claim.get("source_text") or claim["text"], detail)
            for stage in section.get("stage_outputs", []):
                if stage["kind"] != "retrieve":
                    continue
                for passage in stage["passages"]:
                    if passage["citation"]["id"] == evidence_id:
                        return citation_result(passage["citation"], passage["excerpt"], detail)
                for row in stage["rows"]:
                    if row["citation"]["id"] == evidence_id:
                        excerpt = f"{row['metric']} {row['actual']}"
                        return citation_result(row["citation"], excerpt, detail)
        raise HTTPException(404, "citation_not_found")


def citation_result(citation, excerpt, detail):
    return citation | {"excerpt": excerpt[:260]} if detail else citation


def period_scopes(spec: ReportSpec, period: Period) -> dict[str, dict[int, Period]]:
    return {
        section.id: {offset: period.shifted(offset) for offset in section.time.resolved_offsets()}
        for section in spec.sections
    }
