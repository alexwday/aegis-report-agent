from datetime import datetime, timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException
from psycopg.types.json import Jsonb

from .db import connect
from .models import DraftPatch, Period, PreviewRequest, ReportSpec, RunRequest


class Reports:
    def __init__(self, dsn: str, retention_days: int):
        self.dsn = dsn
        self.preview_retention = timedelta(days=retention_days)

    def _draft(self, conn, owner, draft_id, *, lock=False):
        # The suffix is selected from application-owned constants.
        lock_sql = " FOR UPDATE" if lock else ""
        row = conn.execute("""
            SELECT id, report_id, base_version, revision, spec FROM rpt.drafts
            WHERE id = %s AND owner_key = %s
        """ + lock_sql, (draft_id, owner)).fetchone()
        if not row:
            raise HTTPException(404, "draft_not_found")
        return row

    def _assert_revision(self, row, revision):
        if row["revision"] != revision:
            raise HTTPException(409, "stale_draft_revision")

    def create_draft(self, owner: bytes, spec: ReportSpec):
        with connect(self.dsn) as conn:
            return conn.execute("""
                INSERT INTO rpt.drafts (id, owner_key, revision, spec) VALUES (%s, %s, 1, %s)
                RETURNING id, report_id, base_version, revision, spec
            """, (uuid4(), owner, Jsonb(spec.model_dump(mode="json")))).fetchone()

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
            spec = ReportSpec(title=spec.title, sections=list(sections.values()))
            return conn.execute("""
                UPDATE rpt.drafts SET spec = %s, revision = revision + 1 WHERE id = %s AND owner_key = %s
                RETURNING id, report_id, base_version, revision, spec
            """, (Jsonb(spec.model_dump(mode="json")), draft_id, owner)).fetchone()

    def _report_version(self, conn, owner, report_id, version):
        row = conn.execute("""
            SELECT v.spec FROM rpt.report_versions v JOIN rpt.reports r ON r.id = v.report_id
            WHERE r.id = %s AND r.owner_key = %s AND r.archived_at IS NULL AND v.version = %s
        """, (report_id, owner, version)).fetchone()
        if not row:
            raise HTTPException(404, "report_version_not_found")
        return row

    def get_version(self, owner: bytes, report_id: UUID, version: int):
        with connect(self.dsn) as conn:
            return self._report_version(conn, owner, report_id, version)["spec"]

    def save(self, owner: bytes, draft_id: UUID, revision: int):
        with connect(self.dsn) as conn:
            draft = self._draft(conn, owner, draft_id, lock=True)
            self._assert_revision(draft, revision)
            report_id, base = draft["report_id"], draft["base_version"]
            if report_id is None:
                report_id, version = uuid4(), 1
                conn.execute("""
                    INSERT INTO rpt.reports (id, owner_key, head) VALUES (%s, %s, 1)
                """, (report_id, owner))
            else:
                latest = conn.execute("""
                    UPDATE rpt.reports SET head = head + 1
                    WHERE id = %s AND owner_key = %s AND archived_at IS NULL AND head = %s
                    RETURNING head
                """, (report_id, owner, base)).fetchone()
                if latest is None:
                    raise HTTPException(409, "stale_or_archived_report")
                version = latest["head"]
            conn.execute("""
                INSERT INTO rpt.report_versions (report_id, version, spec) VALUES (%s, %s, %s)
            """, (report_id, version, Jsonb(draft["spec"])))
            conn.execute("""
                UPDATE rpt.drafts SET report_id = %s, base_version = %s, revision = revision + 1
                WHERE id = %s AND owner_key = %s
            """, (report_id, version, draft_id, owner))
            return {"report_id": report_id, "version": version, "draft_revision": revision + 1}

    def _run(self, conn, owner, run_id):
        run = conn.execute("""
            SELECT id, mode, trigger_kind, report_id, version, draft_revision, period, state, result, error_code, readiness
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
            version = self._report_version(conn, owner, report_id, request.version)
            period = request.period.model_dump(mode="json")
            job = conn.execute("""
                INSERT INTO rpt.runs
                    (id, owner_key, mode, trigger_kind, report_id, version, period, spec, idempotency_key, next_probe_at)
                VALUES (%s, %s, 'generate', %s, %s, %s, %s, %s, %s, coalesce(%s, now()))
                ON CONFLICT (owner_key, idempotency_key) DO NOTHING
                RETURNING id
            """, (uuid4(), owner, trigger_kind, report_id, request.version, Jsonb(period), Jsonb(version["spec"]),
                  request.request_key, due_at)).fetchone()
            if job:
                return job
            previous = conn.execute("""
                SELECT id, report_id, version, period, trigger_kind FROM rpt.runs
                WHERE owner_key = %s AND idempotency_key = %s
            """, (owner, request.request_key)).fetchone()
            if (previous["report_id"], previous["version"], previous["period"], previous["trigger_kind"]) != (
                report_id, request.version, period, trigger_kind
            ):
                raise HTTPException(409, "request_key_reused")
            return {"id": previous["id"]}

    def enqueue_preview(self, owner: bytes, draft_id: UUID, request: PreviewRequest):
        with connect(self.dsn) as conn:
            draft = self._draft(conn, owner, draft_id)
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
            spec = ReportSpec.model_validate(draft["spec"])
            if request.section_id is not None:
                selected = [section for section in spec.sections if section.id == request.section_id]
                if not selected:
                    raise HTTPException(404, "section_not_found")
                spec = ReportSpec(title=spec.title, sections=selected)
            return conn.execute("""
                INSERT INTO rpt.runs
                    (id, owner_key, mode, draft_revision, preview_section_id, baseline_id, period, spec, expires_at)
                VALUES (%s, %s, 'preview', %s, %s, %s, %s, %s, now() + %s)
                RETURNING id
            """, (uuid4(), owner, draft["revision"], request.section_id, request.baseline_run_id, Jsonb(period),
                  Jsonb(spec.model_dump(mode="json")), self.preview_retention)).fetchone()

    def output(self, owner: bytes, run_id: UUID):
        row = self.get_run(owner, run_id)
        if row["state"] != "succeeded":
            raise HTTPException(409, "run_output_not_ready")
        return row["result"]

    def citation(self, owner: bytes, run_id: UUID, evidence_id: str):
        result = self.output(owner, run_id)
        for section in result["sections"]:
            for row in section["rows"]:
                if row["citation"]["id"] == evidence_id:
                    return row["citation"]
            for claim in section.get("claims", []):
                for citation in claim["citations"]:
                    if citation["id"] == evidence_id:
                        return citation
        raise HTTPException(404, "citation_not_found")


def template(bank: str) -> ReportSpec:
    return ReportSpec.model_validate({
        "title": "Quarterly earnings",
        "sections": [{
            "id": "net-income",
            "title": "Net income",
            "bank": bank,
            "sources": [{"metric": "Net Income"}],
            "instruction": "Highlight the cited enterprise net income observation.",
        }],
    })


def period_scopes(spec: ReportSpec, period: Period) -> dict[str, dict[int, Period]]:
    return {
        section.id: {offset: period.shifted(offset) for offset in section.time.resolved_offsets()}
        for section in spec.sections
    }
