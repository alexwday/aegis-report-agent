from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

import httpx
import psycopg
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import Field

from .auth import AuthProvider, CurrentUser, LocalAuth, UpstreamAuth
from .config import Settings
from .db import connect
from .engine import render_html
from .models import (
    DraftCreate,
    DraftEdit,
    DraftPatch,
    Period,
    PreviewRequest,
    ReportSpec,
    RunRequest,
    SourceName,
    SourceProbeRequest,
    Stage,
    StrictModel,
    compile_section,
)
from .repository import Reports, template
from .sources import (
    BankCatalog,
    BenchmarkFact,
    ChangeBasis,
    Citation,
    Probe,
    Readiness,
    Scope,
    SourceIssue,
    build_sources,
)

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
) -> CurrentUser:
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
    revision: int
    spec: ReportSpec


class SavedVersion(StrictModel):
    report_id: UUID
    version: int
    draft_revision: int


class RunReference(StrictModel):
    id: UUID


class Observation(Probe):
    since: datetime | None
    stable: bool
    data_stability: Literal["stable", "recently_changed", "unknown"] = "unknown"
    source: SourceName | None = None
    period: Period | None = None
    bank: str | None = None
    required: bool = True


class RunResponse(StrictModel):
    id: UUID
    mode: Literal["generate", "preview"]
    trigger_kind: Literal["manual", "automatic"]
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


class Note(StrictModel):
    citation_id: str
    text: str


class SectionResult(StrictModel):
    id: str
    title: str
    rows: list[BenchmarkFact]
    note: Note | None
    comparison: Comparison | None


class ReportDiff(StrictModel):
    added: list[str]
    removed: list[str]
    changed: list[str]


class Result(StrictModel):
    title: str
    period: Period
    basis: Literal["vendor_fiscal_label"]
    sections: list[SectionResult]
    diff: ReportDiff | None = None
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


class Status(StrictModel):
    status: Literal["ok"] = "ok"


def create_app(settings: Settings | None = None, auth_provider: AuthProvider | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application):
        active = settings or Settings.from_env()
        with httpx.Client(trust_env=False) as client:
            application.state.settings = active
            application.state.reports = Reports(active.report_dsn, active.retention_days)
            application.state.catalog = BankCatalog()
            application.state.sources = build_sources(active.currencies)
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
    def list_templates(owner: OwnerKey):
        return [TemplateResponse(id="quarterly-earnings", title="Quarterly earnings")]

    @api.post("/v1/drafts", response_model=DraftResponse, status_code=201)
    def create_draft(body: DraftCreate, owner: OwnerKey, reports: Storage, request: Request):
        try:
            with connect(request.app.state.settings.source_dsn, source=True) as conn:
                bank = request.app.state.catalog.resolve(conn, body.bank)
        except SourceIssue as exc:
            raise HTTPException(422, exc.reason) from exc
        return reports.create_draft(owner, template(bank.symbol))

    @api.get("/v1/drafts/{draft_id}", response_model=DraftResponse)
    def get_draft(draft_id: UUID, owner: OwnerKey, reports: Storage):
        return reports.get_draft(owner, draft_id)

    @api.patch("/v1/drafts/{draft_id}", response_model=DraftResponse)
    def patch_draft(draft_id: UUID, body: DraftPatch, owner: OwnerKey, reports: Storage):
        return reports.patch(owner, draft_id, body)

    @api.get("/v1/drafts/{draft_id}/stages", response_model=list[CompiledSection])
    def stages(draft_id: UUID, owner: OwnerKey, reports: Storage):
        spec = ReportSpec.model_validate(reports.get_draft(owner, draft_id)["spec"])
        return [CompiledSection(section_id=section.id, stages=compile_section(section)) for section in spec.sections]

    @api.post("/v1/drafts/{draft_id}/save", response_model=SavedVersion, status_code=201)
    def save(draft_id: UUID, body: DraftEdit, owner: OwnerKey, reports: Storage):
        return reports.save(owner, draft_id, body.revision)

    @api.get("/v1/reports/{report_id}/versions/{version}", response_model=ReportSpec)
    def version(report_id: UUID, version: Annotated[int, Field(ge=1)], owner: OwnerKey, reports: Storage):
        return reports.get_version(owner, report_id, version)

    @api.post("/v1/drafts/{draft_id}/previews", response_model=RunReference, status_code=202)
    def preview(draft_id: UUID, body: PreviewRequest, owner: OwnerKey, reports: Storage):
        return reports.enqueue_preview(owner, draft_id, body)

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

    @api.get("/v1/runs/{run_id}/evidence/{evidence_id}", response_model=Citation)
    def evidence(run_id: UUID, evidence_id: str, owner: OwnerKey, reports: Storage):
        return reports.citation(owner, run_id, evidence_id)

    return api


app = create_app()
