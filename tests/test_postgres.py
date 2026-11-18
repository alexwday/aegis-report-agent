import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import psycopg
import pytest
from demo import EFFICIENCY, Q2, Q3, demonstrate, submit
from fastapi.testclient import TestClient
from psycopg import sql

from aegis_report.api import create_app
from aegis_report.auth import LocalAuth
from aegis_report.config import Settings
from aegis_report.db import connect
from aegis_report.gateway import StubGateway
from aegis_report.models import Period, SourceName
from aegis_report.sources import (
    BankCatalog,
    BenchmarkingSource,
    EarningsSource,
    Readiness,
    Scope,
    SourceIssue,
    compute_change,
)
from aegis_report.worker import Worker

pytestmark = pytest.mark.postgres


@pytest.fixture
def settings():
    if os.environ.get("AEGIS_TEST_FIXTURE") != "1":
        pytest.skip("Run through ./scripts/test for the disposable database")
    return replace(Settings.from_env(), quiet_seconds=0, poll_seconds=0.01)


@pytest.fixture
def admin(settings):
    with connect(os.environ["RPT_MIGRATION_DATABASE_URL"]) as conn:
        yield conn
        conn.rollback()


def scope(conn, quarter=3, bank="SYN1-CA", metric="Net Income", segment="Enterprise", year=2090):
    return Scope(BankCatalog().resolve(conn, bank), Period(year=year, quarter=quarter), metric, segment)


def test_source_roles_reject_unapproved_schema_access(settings):
    with (
        pytest.raises(psycopg.errors.InsufficientPrivilege),
        connect(settings.source_dsn) as conn,
    ):
        conn.execute("SET TRANSACTION READ WRITE")
        conn.execute('DELETE FROM public.benchmarking_report WHERE false')
    with (
        pytest.raises(psycopg.errors.InsufficientPrivilege),
        connect(settings.source_dsn, source=True) as conn,
    ):
        conn.execute("SELECT id FROM rpt.reports")
    with (
        pytest.raises(psycopg.errors.InsufficientPrivilege),
        connect(settings.report_dsn) as conn,
    ):
        conn.execute("SELECT id FROM public.kpi_metadata")


def test_benchmark_named_projection_does_not_rely_on_uniqueness_or_column_order(admin):
    adapter = BenchmarkingSource({"CA": "CAD"})
    query = scope(admin)
    admin.execute("""
        INSERT INTO public.benchmarking_report (bank_symbol, "Parameter", "Platform", fiscal_year, quarter, "Actual")
        VALUES ('SYN1-CA', 'Net Income', 'Enterprise', 2090, 'Q3', 501)
    """)
    assert adapter.probe(admin, query).reason == "duplicate_benchmark_observation"
    with pytest.raises(SourceIssue, match="duplicate_benchmark_observation"):
        adapter.search(admin, query)
    admin.rollback()

    reorder_columns(admin, "benchmarking_report")
    assert adapter.search(admin, query)[0].actual == Decimal("446")
    assert adapter.anchors(admin, query)[0].locator.endswith("Net Income · Enterprise · FY2090 Q3")


def reorder_columns(conn, relation):
    columns = conn.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s ORDER BY ordinal_position DESC
    """, (relation,)).fetchall()
    moved = f"{relation}_original"
    conn.execute(sql.SQL("ALTER TABLE public.{} RENAME TO {}").format(sql.Identifier(relation), sql.Identifier(moved)))
    conn.execute(sql.SQL("CREATE VIEW public.{} AS SELECT {} FROM public.{}").format(
        sql.Identifier(relation), sql.SQL(", ").join(sql.Identifier(row["column_name"]) for row in columns),
        sql.Identifier(moved),
    ))


def test_benchmark_changes_units_and_cross_year_comparison(settings, admin):
    adapter = BenchmarkingSource({"CA": "CAD", "SYN1-CA": "CAD"})
    ratio = adapter.search(admin, scope(admin, metric="Efficiency Ratio"))[0]
    prior_ratio = adapter.search(admin, scope(admin, quarter=2, metric="Efficiency Ratio"))[0]
    assert (ratio.unit, ratio.change_basis, ratio.raw_qoq) == ("%", "basis_points", Decimal("-40"))
    assert compute_change(ratio, prior_ratio) == Decimal("-40.0")
    net_income = adapter.search(admin, scope(admin))[0]
    previous = adapter.search(admin, scope(admin, quarter=2))[0]
    assert (net_income.unit, net_income.currency, net_income.currency_confirmed) == ("millions", "CAD", False)
    assert net_income.raw_qoq == Decimal("2.54")
    assert compute_change(net_income, previous) == Decimal("2.53")
    two_years_prior = adapter.search(admin, scope(admin, year=2088))[0]
    assert compute_change(net_income, two_years_prior) == Decimal("11.50")
    assert "synthetic/benchmarking.csv" not in net_income.citation.locator
    ambiguous = adapter.search(admin, scope(admin, bank="SYN3-US", metric="Efficiency Ratio", segment="Capital Markets"))[0]
    assert ambiguous.change_basis == "unknown" and ambiguous.raw_qoq == Decimal("-34")
    assert compute_change(ambiguous, ambiguous) is None


def test_coverage_uses_physical_rows_and_aliases_across_periods(settings, admin):
    catalog = BankCatalog()
    benchmark = BenchmarkingSource({})
    assert catalog.resolve(admin, "syn1").symbol == "SYN1-CA"
    target = scope(admin)
    assert not catalog.hinted(admin, target, SourceName.BENCHMARKING)
    assert benchmark.probe(admin, target).state is Readiness.READY
    assert benchmark.probe(admin, scope(admin, bank="SYN2-CA")).state is Readiness.INCOMPLETE
    assert benchmark.probe(admin, scope(admin, quarter=4)).state is Readiness.ABSENT
    assert benchmark.probe(admin, replace(target, metric=None)).state is Readiness.UNKNOWN


def test_earnings_edition_precedence_and_named_projection(admin):
    reorder_columns(admin, "aegis_transcripts")
    reorder_columns(admin, "aegis-earnings-transcripts-data")
    adapter = EarningsSource()
    legacy, unified, absent = (scope(admin, quarter=i) for i in [3, 2, 4])
    coverage = adapter.coverage_map(admin, [legacy, unified, absent])
    assert [coverage[("SYN1-CA", entry.period)].generation for entry in [legacy, unified, absent]] == [
        "legacy", "unified", None,
    ]
    assert coverage[("SYN1-CA", absent.period)].state is Readiness.ABSENT
    chosen = adapter.search(admin, legacy)
    assert len(chosen) == 3
    assert set((block.edition, block.version) for block in chosen) == {("Corrected", "11")}
    assert "speaker block 1" in chosen[0].citation.locator
    assert "speaker block 3" in chosen[-1].citation.locator
    assert len(adapter.anchors(admin, legacy)) == 3
    twin = adapter.search(admin, unified)
    assert "sequence 1" in twin[0].citation.locator
    assert "sequence 2" in twin[1].citation.locator
    assert adapter.search(admin, absent) == []


def test_earnings_conflicting_generations_never_merge(admin):
    adapter = EarningsSource()
    query = scope(admin, quarter=2)
    admin.execute("""
        INSERT INTO public.aegis_transcripts
            (ticker, fiscal_year, fiscal_quarter, institution_id, event_id, version_id, filename, transcript_type)
        VALUES ('SYN1-CA', 2090, 'Q2', '901', '990', '2', 'fixture-overlap.xml', 'Corrected')
    """)
    probe = adapter.probe(admin, query)
    assert (probe.state, probe.generation, probe.reason) == (
        Readiness.UNKNOWN, "conflict", "cross_generation_event_overlap",
    )
    with pytest.raises(SourceIssue, match="cross_generation_event_overlap"):
        adapter.search(admin, query)


def drive_run(client, worker, now, run_id):
    for tick in range(6):
        worker.run_one(now + timedelta(seconds=tick))
        current = submit(client, "GET", f"/v1/runs/{run_id}")
        if current["state"] == "succeeded":
            return
        assert current["state"] != "failed", current["error_code"]
    pytest.fail("Run did not finish")


def test_template_preview_diff_save_next_quarter_and_owner_boundaries(settings):
    worker = Worker(settings, StubGateway())
    with TestClient(create_app(settings)) as owner, TestClient(
        create_app(settings, LocalAuth("fixture-other-analyst"))
    ) as outsider:
        result = demonstrate(
            owner, wait=lambda client, run_id: drive_run(client, worker, datetime.now(UTC) + timedelta(seconds=1), run_id),
            show=lambda message: None,
        )
        draft = f"/v1/drafts/{result['draft']['id']}"
        report = f"/v1/reports/{result['saved']['report_id']}"
        run = f"/v1/runs/{result['run']['id']}"
        cite = result["result"]["sections"][0]["rows"][0]["citation"]["id"]
        for path in (draft, f"{draft}/stages", f"{report}/versions/2", run, f"{run}/output.json",
                     f"{run}/output.html", f"{run}/evidence/{cite}"):
            assert outsider.get(path).status_code == 404
            assert owner.get(path).headers["Cache-Control"] == "no-store"
        edit = {"revision": result["saved"]["draft_revision"], "op": "replace_section", "section": EFFICIENCY}
        assert outsider.patch(draft, json=edit).status_code == 404
        assert owner.patch(draft, json=edit | {"user_id": "someone"}).status_code == 422
        assert owner.patch(draft, json=edit | {"revision": 1}).status_code == 409
        foreign = submit(outsider, "POST", "/v1/drafts", {"bank": "SYN1-CA"})
        denied = outsider.post(f"/v1/drafts/{foreign['id']}/previews", json={
            "revision": foreign["revision"], "period": Q2, "baseline_run_id": result["baseline"]["id"],
        })
        assert denied.status_code == 404
        assert result["result"]["sections"][0]["note"]["citation_id"]


def test_worker_waits_again_when_mid_load_marker_changes(settings, admin):
    settings = replace(settings, quiet_seconds=30)
    worker = Worker(settings, StubGateway())
    with TestClient(create_app(settings)) as app:
        draft = submit(app, "POST", "/v1/drafts", {"bank": "SYN1-CA"})
        saved = submit(app, "POST", f"/v1/drafts/{draft['id']}/save", {"revision": 1})
        path = f"/v1/reports/{saved['report_id']}/runs"
        body = {"version": 1, "period": Q3, "request_key": "mid-load-fixture"}
        queued = submit(app, "POST", path, body)
        assert submit(app, "POST", path, body) == queued
        assert app.post(path, json=body | {"period": Q2}).status_code == 409
        status = f"/v1/runs/{queued['id']}"
        first = datetime.now(UTC) + timedelta(seconds=1)
        assert worker.run_one(first)
        assert submit(app, "GET", status)["state"] == "waiting"
        initial = submit(app, "GET", status)["readiness"]["net-income:0"]
        assert initial["state"] == "ready" and not initial["stable"]
        admin.execute("""
            INSERT INTO public.benchmarking_report
                (bank_symbol, "Parameter", "Platform", fiscal_year, quarter, "Actual", filepath)
            VALUES ('SYN1-CA', 'Fixture partial load metric', 'Enterprise', 2090, 'Q3', 17, 'fixture-reload.csv')
        """)
        admin.commit()
        try:
            assert worker.run_one(first + timedelta(seconds=31))
            current = submit(app, "GET", status)
            changed = current["readiness"]["net-income:0"]
            assert current["state"] == "waiting" and changed["marker"] != initial["marker"] and not changed["stable"]
            assert app.get(f"{status}/output.json").status_code == 409
            assert worker.run_one(first + timedelta(seconds=62))
            assert submit(app, "GET", status)["state"] == "succeeded"
        finally:
            admin.execute('DELETE FROM public.benchmarking_report WHERE "Parameter" = %s',
                          ("Fixture partial load metric",))
            admin.commit()


def test_worker_refuses_inactive_owner_and_removes_expired_preview(settings, admin):
    class InactiveOwner:
        def is_active(self, owner_key):
            return False

    worker = Worker(settings, StubGateway(), InactiveOwner())
    with TestClient(create_app(settings)) as client:
        draft = submit(client, "POST", "/v1/drafts", {"bank": "SYN1-CA"})
        draft_path = f"/v1/drafts/{draft['id']}"
        preview = submit(client, "POST", f"{draft_path}/previews", {"revision": 1, "period": Q3})
        saved = submit(client, "POST", f"{draft_path}/save", {"revision": 1})
        run = submit(client, "POST", f"/v1/reports/{saved['report_id']}/runs",
                     {"version": 1, "period": Q3, "request_key": "inactive-fixture"})
        admin.execute("UPDATE rpt.runs SET expires_at = now() - interval '1 second' WHERE id = %s", (preview["id"],))
        admin.commit()
        assert worker.run_one()
        state = submit(client, "GET", f"/v1/runs/{run['id']}")
        assert (state["state"], state["error_code"]) == ("failed", "report_or_owner_inactive")
        assert client.get(f"/v1/runs/{preview['id']}").status_code == 404
        assert admin.execute("SELECT id FROM rpt.runs WHERE id = %s", (preview["id"],)).fetchone() is None
