import json
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from time import monotonic, sleep
from typing import Annotated, Literal
from uuid import UUID

import httpx
import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import Field

from .auth import AuthProvider, CurrentUser, LocalAuth, UpstreamAuth
from .chat_models import TERMINAL, ChatProposal, Conversation, ConversationCreate, TurnCreate, TurnResult
from .chat_store import ChatStore
from .claims import ThemeClaim
from .config import Settings
from .db import connect
from .diff import DiffDetails
from .documents import build_sources
from .engine import render_html
from .models import (
    DraftCreate,
    DraftEdit,
    DraftPatch,
    Period,
    PreviewRequest,
    ReportClone,
    ReportRename,
    ReportSpec,
    RunRequest,
    ScheduleWrite,
    SourceName,
    SourceProbeRequest,
    Stage,
    StrictModel,
    TemplateCreate,
    compile_section,
)
from .pdf_export import render_pdf
from .peers import PeerStatistics
from .reasons import REASONS
from .repository import Reports
from .sources import (
    BankCatalog,
    BenchmarkFact,
    ChangeBasis,
    Citation,
    Probe,
    Readiness,
    Scope,
    SourceIssue,
)
from .templates import SYSTEM_TEMPLATES, build_system_template, template_index

bearer = HTTPBearer(auto_error=False)
CONSOLE = Path(__file__).resolve().parents[2] / "ui"
CONSOLE_CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
               "base-uri 'none'; frame-ancestors 'none'; form-action 'self'")


def get_current_user(
    request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    x_aegis_local_identity: Annotated[str | None, Header(include_in_schema=False)] = None,
) -> CurrentUser:
    if x_aegis_local_identity is not None and request.app.state.local_identities:
        if x_aegis_local_identity not in request.app.state.local_identities:
            raise HTTPException(422, "unknown_local_identity")
        return LocalAuth(x_aegis_local_identity).authenticate(None)
    return request.app.state.auth.authenticate(credentials.credentials if credentials else None)


def storage(request: Request) -> Reports:
    return request.app.state.reports


def owner_key(request: Request, user: Annotated[CurrentUser, Depends(get_current_user)]) -> bytes:
    return user.owner_key(request.app.state.settings.owner_secret)


OwnerKey = Annotated[bytes, Depends(owner_key)]
Storage = Annotated[Reports, Depends(storage)]


class DraftResponse(StrictModel):
    id: UUID
    report_id: UUID | None
    base_version: int | None
    head_at_start: int | None = None
    revision: int
    spec: ReportSpec


class AppliedProposal(StrictModel):
    draft_id: UUID
    revision: int


class SavedVersion(StrictModel):
    report_id: UUID
    version: int
    draft_revision: int


class RunReference(StrictModel):
    id: UUID


class Observation(Probe):
    section_id: str | None = None
    message: str | None = None
    since: datetime | None
    stable: bool
    data_stability: Literal["stable", "recently_changed", "unknown"] = "unknown"
    source: SourceName | None = None
    period: Period | None = None
    bank: str | None = None
    required: bool = True
    selector: dict | None = None
    evidence_state: Literal["matched", "no_match"] | None = None


class RunResponse(StrictModel):
    id: UUID
    mode: Literal["generate", "preview"]
    trigger_kind: Literal["manual", "automatic"]
    stop_after: Literal["gather"] | None = None
    report_id: UUID | None
    version: int | None
    draft_revision: int | None
    period: Period
    state: Literal["queued", "waiting", "running", "succeeded", "failed"]
    error_code: str | None
    readiness: dict[str, Observation]


class Comparison(StrictModel):
    value: str | None
    basis: ChangeBasis
    offset: int
    citation_ids: list[str]
    metric: str | None = None
    segment: str | None = None
    bank: str | None = None
    provenance: Literal["vendor_qoq", "vendor_yoy", "rounded_actuals"] | None = None


class Note(StrictModel):
    citation_id: str
    text: str


class SectionBlocks(StrictModel):
    rows: list[BenchmarkFact]
    note: Note | None
    comparison: Comparison | None
    comparisons: list[Comparison] = Field(default_factory=list)
    claims: list[ThemeClaim] = Field(default_factory=list)
    peers: list[PeerStatistics] = Field(default_factory=list)


class GatheredPassage(StrictModel):
    excerpt: str
    citation: Citation
    period: Period
    topics: list[str]
    bank: str | None = None


class GatherOutput(StrictModel):
    kind: Literal["retrieve"]
    rows: list[BenchmarkFact]
    passages: list[GatheredPassage]


class CalculationOutput(StrictModel):
    kind: Literal["calculate"]
    comparisons: list[Comparison]
    peers: list[PeerStatistics] = Field(default_factory=list)


class DraftOutput(StrictModel):
    kind: Literal["draft"]
    claims: list[ThemeClaim]
    note: Note | None


class NumericCheckOutput(StrictModel):
    kind: Literal["numeric_check"]
    validated_rows: int


class FormatOutput(StrictModel):
    kind: Literal["format"]
    blocks: SectionBlocks


StageOutput = Annotated[
    GatherOutput | CalculationOutput | DraftOutput | NumericCheckOutput | FormatOutput,
    Field(discriminator="kind"),
]


class SectionResult(SectionBlocks):
    id: str
    title: str
    mode: Literal["one_step", "staged"] = "one_step"
    resolved_periods: list[Period] = Field(default_factory=list)
    stage_outputs: list[StageOutput] = Field(default_factory=list)


class ReportDiff(StrictModel):
    added: list[str]
    removed: list[str]
    changed: list[str]


class Result(StrictModel):
    title: str
    period: Period
    basis: Literal["vendor_fiscal_label"]
    completion: Literal["gathered", "finished"] = "finished"
    sections: list[SectionResult]
    diff: ReportDiff | None = None
    diff_details: DiffDetails | None = None
    baseline_run_id: UUID | None = None
    readiness: dict[str, Observation] = Field(default_factory=dict)


class BankResponse(StrictModel):
    id: int
    symbol: str
    name: str
    aliases: list[str]


class SourceProbeResponse(Probe):
    availability_hint: bool = False


class CompiledSection(StrictModel):
    section_id: str
    stages: list[Stage]


class TemplateResponse(StrictModel):
    id: str
    title: str
    kind: Literal["system", "personal"]


class ReportResponse(StrictModel):
    id: UUID
    title: str
    head: int
    created_at: datetime
    archived_at: datetime | None


class VersionResponse(StrictModel):
    version: int
    title: str
    created_at: datetime


class ScheduleResponse(StrictModel):
    report_id: UUID
    version: int
    period: Period
    enabled: bool
    revision: int


class ScheduledRun(StrictModel):
    id: UUID
    period: Period
    version: int
    schedule_revision: int
    state: Literal["queued", "waiting", "running", "succeeded", "failed"]
    error_code: str | None
    created_at: datetime


class CitationDetail(Citation):
    excerpt: str


class Status(StrictModel):
    status: Literal["ok"] = "ok"


def create_app(settings: Settings | None = None, auth_provider: AuthProvider | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application):
        active = settings or Settings.from_env()
        with httpx.Client(trust_env=False) as client:
            application.state.settings = active
            application.state.local_identities = (
                list(dict.fromkeys((active.local_user_id, "fixture-analyst", "fixture-reviewer")))
                if active.local and auth_provider is None else []
            )
            application.state.reports = Reports(active.report_dsn, active.retention_days)
            application.state.chat = ChatStore(application.state.reports)
            application.state.catalog = BankCatalog()
            application.state.sources = build_sources(active)
            if auth_provider:
                application.state.auth = auth_provider
            elif active.local:
                application.state.auth = LocalAuth(active.local_user_id)
            elif active.auth_url:
                application.state.auth = UpstreamAuth(active.auth_url, client)
            else:
                raise ValueError("Production authentication must be configured")
            yield

    api = FastAPI(title="Aegis Report Agent", version="0.1.0", lifespan=lifespan)

    @api.middleware("http")
    async def private_responses(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/v1/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @api.exception_handler(RequestValidationError)
    async def invalid_input(request: Request, error: RequestValidationError):
        # FastAPI's default validation payload echoes input values. Return field and message only.
        issues = [{"loc": error["loc"], "msg": error["msg"], "type": error["type"]} for error in error.errors()]
        return JSONResponse({"detail": issues}, status_code=422)

    @api.exception_handler(psycopg.Error)
    async def database_error(request: Request, error: psycopg.Error):
        return JSONResponse({"detail": "database_unavailable"}, status_code=503)

    @api.get("/health", response_model=Status)
    def health():
        return Status()

    @api.get("/console/context", include_in_schema=False)
    def console_context(request: Request):
        ids = request.app.state.local_identities
        if not ids:
            raise HTTPException(404)
        return JSONResponse({"identities": ids}, headers={"Cache-Control": "no-store"})

    @api.get("/console", include_in_schema=False)
    @api.get("/console/{asset}", include_in_schema=False)
    def local_console(request: Request, asset: str = "index.html"):
        if not request.app.state.local_identities or asset not in {"index.html", "app.js", "app.css"}:
            raise HTTPException(404)
        return FileResponse(CONSOLE / asset, headers={
            "Cache-Control": "no-store", "Content-Security-Policy": CONSOLE_CSP,
            "X-Content-Type-Options": "nosniff",
        })

    @api.get("/v1/reasons", response_model=dict[str, str])
    def reasons(owner: OwnerKey):
        return REASONS

    @api.get("/v1/catalog/banks", response_model=list[BankResponse])
    def banks(request: Request, owner: OwnerKey):
        with connect(request.app.state.settings.source_dsn, source=True) as conn:
            return [BankResponse.model_validate(bank, from_attributes=True) for bank in request.app.state.catalog.list(conn)]

    @api.post("/v1/sources/{source}/probe", response_model=SourceProbeResponse)
    def probe(source: SourceName, body: SourceProbeRequest, request: Request, owner: OwnerKey):
        catalog = request.app.state.catalog
        try:
            with connect(request.app.state.settings.source_dsn, source=True) as conn:
                bank = catalog.resolve(conn, body.bank)
                scope = Scope(bank, body.period, body.metric, body.segment)
                hinted = catalog.hinted(conn, scope, source)
                result = request.app.state.sources[source].probe(conn, scope)
                return SourceProbeResponse(**result.model_dump(), availability_hint=hinted)
        except SourceIssue as exc:
            return SourceProbeResponse(state=exc.state, reason=exc.reason)
        except psycopg.Error:
            return SourceProbeResponse(state=Readiness.UNKNOWN, reason="source_unavailable")

    @api.get("/v1/templates", response_model=list[TemplateResponse])
    def list_templates(owner: OwnerKey, reports: Storage):
        return template_index() + reports.list_personal_templates(owner)

    @api.post("/v1/templates", response_model=TemplateResponse, status_code=201)
    def create_template(body: TemplateCreate, owner: OwnerKey, reports: Storage):
        return reports.create_personal_template(owner, body)

    @api.post("/v1/drafts", response_model=DraftResponse, status_code=201)
    def create_draft(body: DraftCreate, owner: OwnerKey, reports: Storage, request: Request):
        is_system = body.template in SYSTEM_TEMPLATES
        if is_system and body.bank is None:
            raise HTTPException(422, "system_template_requires_bank")
        personal_spec = reports.get_personal_template(owner, body.template) if not is_system else None
        if body.bank is None and personal_spec is not None:
            return reports.create_draft(owner, personal_spec)
        try:
            with connect(request.app.state.settings.source_dsn, source=True) as conn:
                bank = request.app.state.catalog.resolve(conn, body.bank)
        except SourceIssue as exc:
            raise HTTPException(422, exc.reason) from exc
        if personal_spec is not None:
            spec = personal_spec.model_copy(update={
                "sections": [section.model_copy(update={"bank": bank.symbol, "banks": None, "peer_group": None}) for section in personal_spec.sections],
            })
        else:
            spec = build_system_template(body.template, bank.symbol)
        return reports.create_draft(owner, spec)

    @api.get("/v1/drafts/{draft_id}", response_model=DraftResponse)
    def get_draft(draft_id: UUID, owner: OwnerKey, reports: Storage):
        return reports.get_draft(owner, draft_id)

    @api.patch("/v1/drafts/{draft_id}", response_model=DraftResponse)
    def patch_draft(draft_id: UUID, body: DraftPatch, owner: OwnerKey, reports: Storage):
        return reports.patch(owner, draft_id, body)

    @api.patch("/v1/drafts/{draft_id}/operations", response_model=DraftResponse)
    def apply_draft_operations(draft_id: UUID, body: ChatProposal, owner: OwnerKey, reports: Storage):
        return reports.apply_operations(owner, draft_id, body)

    @api.post("/v1/conversations", response_model=Conversation, status_code=201)
    def new_conversation(body: ConversationCreate, owner: OwnerKey, request: Request):
        return request.app.state.chat.create(owner, body)

    @api.post("/v1/conversations/{conversation_id}/turns", response_model=TurnResult, status_code=202)
    def new_turn(conversation_id: UUID, body: TurnCreate, owner: OwnerKey, request: Request):
        return request.app.state.chat.post(owner, conversation_id, body)

    turn_path = "/v1/conversations/{conversation_id}/turns/{turn_id}"

    @api.get(turn_path, response_model=TurnResult)
    def read_turn(conversation_id: UUID, turn_id: UUID, owner: OwnerKey, request: Request):
        return request.app.state.chat.result(owner, conversation_id, turn_id)

    @api.post(turn_path + "/cancel", response_model=TurnResult)
    def cancel_turn(conversation_id: UUID, turn_id: UUID, owner: OwnerKey, request: Request):
        return request.app.state.chat.cancel(owner, conversation_id, turn_id)

    @api.post(turn_path + "/accept", response_model=AppliedProposal)
    def accept_proposal(conversation_id: UUID, turn_id: UUID, body: DraftEdit, owner: OwnerKey, request: Request):
        return request.app.state.chat.accept(owner, conversation_id, turn_id, body.revision)

    @api.get(turn_path + "/events", response_class=StreamingResponse, responses={
        200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}},
    })
    def turn_events(
        conversation_id: UUID, turn_id: UUID, owner: OwnerKey, request: Request,
        last_event_id: Annotated[int, Header(ge=0, le=2_147_483_647)] = 0,
    ):
        chat = request.app.state.chat
        turn = chat.result(owner, conversation_id, turn_id)
        if last_event_id > turn.last_sequence:
            raise HTTPException(409, "event_cursor_ahead_of_turn")

        def stream():
            cursor = last_event_id
            timeout = monotonic() + 30
            heartbeat = monotonic()
            while monotonic() < timeout:
                state, events = chat.events(owner, conversation_id, turn_id, cursor)
                for event in events:
                    cursor = event["sequence"]
                    data = json.dumps(event["data"], separators=(",", ":"))
                    yield f"id: {cursor}\nevent: {event['kind']}\ndata: {data}\n\n"
                if state in TERMINAL:
                    return
                if monotonic() >= heartbeat:
                    yield ": heartbeat\n\n"
                    heartbeat = monotonic() + 10
                sleep(0.25)

        return StreamingResponse(stream(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})

    @api.get("/v1/drafts/{draft_id}/stages", response_model=list[CompiledSection])
    def stages(draft_id: UUID, owner: OwnerKey, reports: Storage):
        spec = ReportSpec.model_validate(reports.get_draft(owner, draft_id)["spec"])
        return [CompiledSection(section_id=section.id, stages=compile_section(section)) for section in spec.sections]

    @api.post("/v1/drafts/{draft_id}/save", response_model=SavedVersion, status_code=201)
    def save(draft_id: UUID, body: DraftEdit, owner: OwnerKey, reports: Storage):
        return reports.save(owner, draft_id, body.revision)

    @api.get("/v1/reports", response_model=list[ReportResponse])
    def list_reports(owner: OwnerKey, reports: Storage, archived: bool = False,
                     limit: Annotated[int, Query(ge=1, le=100)] = 50,
                     offset: Annotated[int, Query(ge=0)] = 0):
        return reports.list_reports(owner, archived, limit, offset)

    @api.get("/v1/reports/{report_id}", response_model=ReportResponse)
    def report(report_id: UUID, owner: OwnerKey, reports: Storage):
        return reports.get_report(owner, report_id)

    @api.patch("/v1/reports/{report_id}", response_model=ReportResponse)
    def rename_report(report_id: UUID, body: ReportRename, owner: OwnerKey, reports: Storage):
        return reports.rename_report(owner, report_id, body.title)

    @api.post("/v1/reports/{report_id}/archive", response_model=ReportResponse)
    def archive_report(report_id: UUID, owner: OwnerKey, reports: Storage):
        return reports.archive_report(owner, report_id, archived=True)

    @api.post("/v1/reports/{report_id}/restore", response_model=ReportResponse)
    def restore_report(report_id: UUID, owner: OwnerKey, reports: Storage):
        return reports.archive_report(owner, report_id, archived=False)

    @api.post("/v1/reports/{report_id}/clone", response_model=ReportResponse, status_code=201)
    def clone_report(report_id: UUID, body: ReportClone, owner: OwnerKey, reports: Storage):
        return reports.clone_report(owner, report_id, body)

    @api.get("/v1/reports/{report_id}/versions", response_model=list[VersionResponse])
    def versions(report_id: UUID, owner: OwnerKey, reports: Storage,
                 limit: Annotated[int, Query(ge=1, le=100)] = 50,
                 offset: Annotated[int, Query(ge=0)] = 0):
        return reports.list_versions(owner, report_id, limit, offset)

    @api.post("/v1/reports/{report_id}/versions/{version}/drafts", response_model=DraftResponse, status_code=201)
    def historical_draft(report_id: UUID, version: Annotated[int, Field(ge=1)], owner: OwnerKey, reports: Storage):
        return reports.draft_from_version(owner, report_id, version)

    @api.get("/v1/reports/{report_id}/versions/{version}", response_model=ReportSpec)
    def version(report_id: UUID, version: Annotated[int, Field(ge=1)], owner: OwnerKey, reports: Storage):
        return reports.get_version(owner, report_id, version)

    @api.post("/v1/drafts/{draft_id}/previews", response_model=RunReference, status_code=202)
    def preview(draft_id: UUID, body: PreviewRequest, owner: OwnerKey, reports: Storage):
        return reports.enqueue_preview(owner, draft_id, body)

    @api.get("/v1/reports/{report_id}/schedule", response_model=ScheduleResponse)
    def get_schedule(report_id: UUID, owner: OwnerKey, reports: Storage):
        return reports.get_schedule(owner, report_id)

    @api.get("/v1/reports/{report_id}/schedule/runs", response_model=list[ScheduledRun])
    def schedule_runs(
        report_id: UUID, owner: OwnerKey, reports: Storage,
        limit: Annotated[int, Query(ge=1, le=100)] = 20, offset: Annotated[int, Query(ge=0)] = 0,
    ):
        return reports.schedule_history(owner, report_id, limit, offset)

    @api.put("/v1/reports/{report_id}/schedule", response_model=ScheduleResponse)
    def put_schedule(report_id: UUID, body: ScheduleWrite, owner: OwnerKey, reports: Storage):
        return reports.put_schedule(owner, report_id, body)

    @api.post("/v1/reports/{report_id}/schedule/enqueue", response_model=RunReference, status_code=202)
    def enqueue_schedule(report_id: UUID, owner: OwnerKey, reports: Storage):
        return reports.enqueue_schedule(owner, report_id)

    @api.post("/v1/reports/{report_id}/runs", response_model=RunReference, status_code=202)
    def create_run(report_id: UUID, body: RunRequest, owner: OwnerKey, reports: Storage):
        return reports.enqueue_run(owner, report_id, body)

    @api.get("/v1/runs/{run_id}", response_model=RunResponse)
    def get_run(run_id: UUID, owner: OwnerKey, reports: Storage):
        row = reports.get_run(owner, run_id)
        row.pop("result")
        return row

    @api.get("/v1/runs/{run_id}/output.json", response_model=Result)
    def json_output(run_id: UUID, owner: OwnerKey, reports: Storage):
        return reports.output(owner, run_id)

    @api.get("/v1/runs/{run_id}/output.html", response_class=HTMLResponse)
    def html_output(run_id: UUID, owner: OwnerKey, reports: Storage):
        return HTMLResponse(render_html(reports.output(owner, run_id)), headers={
            "Content-Security-Policy": "default-src 'none'; base-uri 'none'; frame-ancestors 'none'",
            "Cache-Control": "no-store",
        })

    @api.get(
        "/v1/runs/{run_id}/output.pdf", response_class=Response,
        responses={200: {"content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}}}},
    )
    def pdf_output(run_id: UUID, owner: OwnerKey, reports: Storage):
        document = render_pdf(reports.pdf_output(owner, run_id))
        return Response(document, media_type="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="report.pdf"'})

    @api.get("/v1/runs/{run_id}/evidence/{evidence_id}", response_model=Citation)
    def evidence(run_id: UUID, evidence_id: str, owner: OwnerKey, reports: Storage):
        return reports.citation(owner, run_id, evidence_id)

    @api.get("/v1/runs/{run_id}/evidence/{evidence_id}/detail", response_model=CitationDetail)
    def evidence_detail(run_id: UUID, evidence_id: str, owner: OwnerKey, reports: Storage):
        return reports.citation(owner, run_id, evidence_id, detail=True)

    return api


app = create_app()
