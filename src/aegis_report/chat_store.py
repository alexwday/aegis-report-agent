from datetime import timedelta
from uuid import uuid4

from fastapi import HTTPException
from psycopg.types.json import Jsonb

from .chat_models import TERMINAL, ChatProposal, TurnResult, apply_operations
from .db import connect
from .models import Period, PreviewRequest, ReportSpec
from .repository import Reports

TURN_LEASE = timedelta(seconds=75)


class TurnStopped(Exception):
    pass


class ChatStore:
    def __init__(self, reports: Reports):
        self.reports = reports
        self.dsn = reports.dsn

    def conversation(self, conn, owner, conversation_id, *, lock=False):
        query = "SELECT id, owner_key, draft_id, period FROM rpt.conversations WHERE id = %s AND owner_key = %s"
        row = conn.execute(query + (" FOR UPDATE" if lock else ""), (conversation_id, owner)).fetchone()
        if not row:
            raise HTTPException(404, "conversation_not_found")
        return row

    def create(self, owner, body):
        with connect(self.dsn) as conn:
            self.reports._draft(conn, owner, body.draft_id)
            return conn.execute("""
                INSERT INTO rpt.conversations (id, owner_key, draft_id, period) VALUES (%s, %s, %s, %s)
                RETURNING id, draft_id, period
            """, (uuid4(), owner, body.draft_id, Jsonb(body.period.model_dump()))).fetchone()

    def _turn(self, conn, owner, conversation_id, turn_id, *, lock=False):
        conversation = self.conversation(conn, owner, conversation_id)
        query = "SELECT * FROM rpt.chat_turns WHERE id = %s AND conversation_id = %s"
        turn = conn.execute(query + (" FOR UPDATE" if lock else ""), (turn_id, conversation_id)).fetchone()
        if not turn:
            raise HTTPException(404, "turn_not_found")
        return conversation, turn

    @staticmethod
    def _result(turn):
        return TurnResult.model_validate({key: turn[key] for key in TurnResult.model_fields})

    def post(self, owner, conversation_id, body):
        with connect(self.dsn) as conn:
            self.conversation(conn, owner, conversation_id, lock=True)
            prev = conn.execute("""
                SELECT * FROM rpt.chat_turns WHERE conversation_id = %s AND request_key = %s
            """, (conversation_id, body.request_key)).fetchone()
            if prev:
                if prev["user_message"] != body.message:
                    raise HTTPException(409, "request_key_conflict")
                return self._result(prev)
            active = conn.execute("""
                SELECT 1 FROM rpt.chat_turns WHERE conversation_id = %s AND state IN ('queued', 'running')
            """, (conversation_id,)).fetchone()
            if active:
                raise HTTPException(409, "conversation_turn_active")
            turn = conn.execute("""
                INSERT INTO rpt.chat_turns (id, conversation_id, request_key, user_message)
                VALUES (%s, %s, %s, %s) RETURNING *
            """, (uuid4(), conversation_id, body.request_key, body.message)).fetchone()
            turn["last_sequence"] = self._event(conn, turn["id"], "queued")
            return self._result(turn)

    @staticmethod
    def _event(conn, turn_id, kind, data=None):
        updated = conn.execute("""
            UPDATE rpt.chat_turns SET last_sequence = last_sequence + 1 WHERE id = %s RETURNING last_sequence
        """, (turn_id,)).fetchone()
        sequence = updated["last_sequence"]
        conn.execute("""
            INSERT INTO rpt.chat_events (turn_id, sequence, kind, data) VALUES (%s, %s, %s, %s)
        """, (turn_id, sequence, kind, Jsonb(data or {})))
        return sequence

    def result(self, owner, conversation_id, turn_id):
        with connect(self.dsn) as conn:
            _, turn = self._turn(conn, owner, conversation_id, turn_id)
            return self._result(turn)

    def events(self, owner, conversation_id, turn_id, cursor):
        with connect(self.dsn) as conn:
            _, turn = self._turn(conn, owner, conversation_id, turn_id)
            rows = conn.execute("""
                SELECT sequence, kind, data FROM rpt.chat_events WHERE turn_id = %s AND sequence > %s
                ORDER BY sequence
            """, (turn_id, cursor)).fetchall()
            return turn["state"], rows

    def cancel(self, owner, conversation_id, turn_id):
        with connect(self.dsn) as conn:
            _, turn = self._turn(conn, owner, conversation_id, turn_id, lock=True)
            if turn["state"] not in TERMINAL:
                self._terminal(conn, turn_id, "cancelled")
                _, turn = self._turn(conn, owner, conversation_id, turn_id)
            return self._result(turn)

    def claim(self, lease: timedelta = TURN_LEASE):
        with connect(self.dsn) as conn:
            expired = conn.execute("""
                SELECT id FROM rpt.chat_turns WHERE state = 'running' AND lease_until <= clock_timestamp()
                ORDER BY lease_until LIMIT 1 FOR UPDATE SKIP LOCKED
            """).fetchone()
            if expired:
                self._terminal(conn, expired["id"], "failed", error_code="turn_worker_timeout")
            job = conn.execute("""
                SELECT t.id, c.id AS conversation_id, c.owner_key, c.draft_id, c.period, t.user_message
                FROM rpt.chat_turns t JOIN rpt.conversations c ON c.id = t.conversation_id
                WHERE t.state = 'queued' ORDER BY t.created_at, t.id LIMIT 1 FOR UPDATE OF t SKIP LOCKED
            """).fetchone()
            if not job:
                return None
            conn.execute("""
                UPDATE rpt.chat_turns SET state = 'running', lease_until = clock_timestamp() + %s WHERE id = %s
            """, (lease, job["id"]))
            self._event(conn, job["id"], "started")
            return job

    def _active(self, conn, job):
        row = conn.execute("""
            SELECT preview_id FROM rpt.chat_turns
            WHERE id = %s AND state = 'running' AND lease_until > clock_timestamp() FOR UPDATE
        """, (job["id"],)).fetchone()
        if not row:
            raise TurnStopped
        return row

    def context(self, job):
        with connect(self.dsn) as conn:
            self._active(conn, job)
            rows = conn.execute("""
                SELECT user_message, message FROM rpt.chat_turns
                WHERE conversation_id = %s AND state = 'succeeded'
                ORDER BY created_at DESC, id DESC LIMIT 4
            """, (job["conversation_id"],)).fetchall()
            return rows[::-1]

    def progress(self, job, tool):
        with connect(self.dsn) as conn:
            self._active(conn, job)
            self._event(conn, job["id"], "tool", {"name": tool})

    def _terminal(self, conn, turn_id, state, message=None, error_code=None, proposal=None):
        conn.execute("""
            UPDATE rpt.chat_turns SET state = %s, lease_until = NULL, message = %s, error_code = %s, proposal = %s
            WHERE id = %s
        """, (state, message, error_code, Jsonb(proposal) if proposal else None, turn_id))
        if proposal:
            self._event(conn, turn_id, "patch_proposed", proposal)
        if message:
            self._event(conn, turn_id, "message", {"text": message})
        self._event(conn, turn_id, state, {"error_code": error_code} if error_code else None)

    def finish(self, job, state, *, message=None, error_code=None, proposal=None):
        with connect(self.dsn) as conn:
            self._active(conn, job)
            self._terminal(conn, job["id"], state, message, error_code, proposal)

    def preview(self, job, args, revision, proposed_spec):
        with connect(self.dsn) as conn:
            active = self._active(conn, job)
            if active["preview_id"]:
                raise HTTPException(409, "turn_preview_limit")
            owner = job["owner_key"]
            draft = self.reports._draft(conn, owner, job["draft_id"], lock=True)
            baseline = None
            if args.compare_saved:
                row = conn.execute("""
                    SELECT id FROM rpt.runs WHERE owner_key = %s AND report_id = %s AND version = %s
                      AND period = %s AND mode = 'generate' AND state = 'succeeded'
                    ORDER BY created_at DESC, id DESC LIMIT 1
                """, (owner, draft["report_id"], draft["base_version"], Jsonb(job["period"]))).fetchone()
                if not row:
                    raise HTTPException(404, "saved_baseline_unavailable")
                baseline = row["id"]
            request = PreviewRequest(revision=revision, period=Period.model_validate(job["period"]),
                                     baseline_run_id=baseline, section_id=args.section_id, stop_after=args.stop_after)
            run_id = self.reports._insert_preview(conn, owner, draft, request, proposed_spec=proposed_spec)["id"]
            conn.execute("UPDATE rpt.chat_turns SET preview_id = %s WHERE id = %s", (run_id, job["id"]))
            self._event(conn, job["id"], "preview_queued", {"preview_id": str(run_id)})
            return str(run_id)

    def recent_preview(self, job):
        with connect(self.dsn) as conn:
            self._active(conn, job)
            return conn.execute("""
                SELECT r.id, r.state, r.result FROM rpt.chat_turns t JOIN rpt.runs r ON r.id = t.preview_id
                WHERE t.conversation_id = %s AND r.owner_key = %s AND r.expires_at > now()
                ORDER BY t.created_at DESC, t.id DESC LIMIT 1
            """, (job["conversation_id"], job["owner_key"])).fetchone()

    def reject(self, owner, conversation_id, turn_id):
        with connect(self.dsn) as conn:
            _, turn = self._turn(conn, owner, conversation_id, turn_id, lock=True)
            if turn["state"] != "succeeded" or not turn["proposal"] or turn["applied_revision"] is not None:
                raise HTTPException(409, "proposal_unavailable")
            if not turn["rejected"]:
                conn.execute("UPDATE rpt.chat_turns SET rejected = true WHERE id = %s", (turn_id,))
                turn["last_sequence"] = self._event(conn, turn_id, "patch_rejected")
                turn["rejected"] = True
            return self._result(turn)

    def accept(self, owner, conversation_id, turn_id, revision, operations=None):
        with connect(self.dsn) as conn:
            conversation, turn = self._turn(conn, owner, conversation_id, turn_id, lock=True)
            if turn["state"] != "succeeded" or not turn["proposal"] or turn["rejected"]:
                raise HTTPException(409, "proposal_unavailable")
            proposal = ChatProposal.model_validate(turn["proposal"])
            if proposal.revision != revision:
                raise HTTPException(409, "proposal_revision_mismatch")
            draft_id = conversation["draft_id"]
            if turn["applied_revision"] is not None:
                return {"draft_id": draft_id, "revision": turn["applied_revision"]}
            draft = self.reports._draft(conn, owner, draft_id, lock=True)
            self.reports._assert_revision(draft, revision)
            try:
                updated = apply_operations(ReportSpec.model_validate(draft["spec"]), operations or proposal.operations)
            except ValueError as exc:
                raise HTTPException(409, "proposal_operation_conflict") from exc
            saved = self.reports._write_draft(conn, owner, draft_id, updated)
            conn.execute("""
                UPDATE rpt.chat_turns SET applied_revision = %s WHERE id = %s
            """, (saved["revision"], turn_id))
            self._event(conn, turn_id, "patch_applied", {"revision": saved["revision"]})
            return {"draft_id": draft_id, "revision": saved["revision"]}
