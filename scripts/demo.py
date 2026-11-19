import argparse
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx

from aegis_report.auth import LocalAuth
from aegis_report.config import Settings
from aegis_report.gateway import StubGateway
from aegis_report.models import RunRequest
from aegis_report.repository import Reports
from aegis_report.worker import Worker

Q2 = {"year": 2090, "quarter": 2}
Q3 = {"year": 2090, "quarter": 3}
TREND = {
    "id": "net-income",
    "title": "Net income trend",
    "bank": "SYN1-CA",
    "sources": [{"source": "benchmarking", "metric": "Net Income", "segment": "Enterprise"}],
    "time": {"preset": {"kind": "same_quarter_years", "count": 4}, "compare": "prior_year"},
    "instruction": "Highlight the cited figure and its year-over-year change.",
    "output_format": "table_with_note",
}
THEMES = {
    "id": "earnings-themes",
    "kind": "themes",
    "mode": "staged",
    "title": "Earnings themes and funding context",
    "bank": "SYN1-CA",
    "sources": [
        {"source": "transcripts", "topics": ["Funding costs"]},
        {"source": "benchmarking", "metric": "Efficiency Ratio"},
        {"source": "investor_presentation", "topic": "Funding costs", "required": False},
    ],
    "instruction": "Identify cited funding-cost claims and include the benchmark context.",
    "output_format": "themes",
}


HIGHLIGHT = {
    "id": "margin-slides",
    "kind": "highlights",
    "title": "Investor slides · Margin drivers",
    "bank": "SYN1-CA",
    "sources": [{"source": "investor_presentation", "topic": "Net Interest Income & Margins",
                 "terms": ["net interest margin"]}],
    "instruction": "Find the strongest margin driver and the cited basis-point movement.",
    "output_format": "themes",
}


def submit(client, method, path, body=None):
    response = client.request(method, path, json=body)
    response.raise_for_status()
    return response.json()


def wait_for_run(client, run_id):
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline:
        run = submit(client, "GET", f"/v1/runs/{run_id}")
        if run["state"] == "succeeded":
            return
        if run["state"] == "failed":
            raise RuntimeError(f"Worker failed: {run['error_code']}")
        time.sleep(0.1)
    raise RuntimeError("Worker did not finish within the demo window")


def demonstrate(client, wait=wait_for_run, show=print):
    prefix = uuid4().hex
    draft = submit(client, "POST", "/v1/drafts", {"template": "quarterly-earnings", "bank": "SYN1-CA"})
    drafts = f"/v1/drafts/{draft['id']}"
    show("Draft created from the quarterly earnings template.")

    initial_theme = THEMES | {
        "sources": [{"source": "transcripts", "topics": ["Net Interest Income & Margins"]}, THEMES["sources"][1]],
    }
    initial = submit(client, "PATCH", drafts, {"revision": draft["revision"], "op": "add_section", "section": initial_theme})
    saved = submit(client, "POST", f"{drafts}/save", {"revision": initial["revision"]})
    reports = f"/v1/reports/{saved['report_id']}"
    baseline = submit(client, "POST", f"{reports}/runs", {
        "version": 1, "period": Q2, "request_key": f"{prefix}-baseline",
    })
    wait(client, baseline["id"])
    show("Saved baseline v1 generated on demand for FY2090 Q2.")

    revised = submit(client, "PATCH", drafts, {
        "revision": saved["draft_revision"], "op": "replace_section", "section": TREND,
    })
    revised = submit(client, "PATCH", drafts, {
        "revision": revised["revision"], "op": "replace_section", "section": THEMES,
    })
    revised = submit(client, "PATCH", drafts, {
        "revision": revised["revision"], "op": "add_section", "section": HIGHLIGHT,
    })
    gathered = submit(client, "POST", f"{drafts}/previews", {
        "revision": revised["revision"], "period": Q2, "section_id": THEMES["id"], "stop_after": "gather",
    })
    wait(client, gathered["id"])
    gathered_result = submit(client, "GET", f"/v1/runs/{gathered['id']}/output.json")
    stage_outputs = gathered_result["sections"][0]["stage_outputs"]
    assert gathered_result["completion"] == "gathered"
    assert [stage["kind"] for stage in stage_outputs] == ["retrieve"] and stage_outputs[0]["passages"]
    show(f"Staged preview stopped after gather with {len(stage_outputs[0]['passages'])} cited passage(s).")
    stage_list = submit(client, "GET", f"{drafts}/stages")
    kinds = [stage["kind"] for stage in stage_list[0]["stages"]]
    assert kinds == ["retrieve", "calculate", "draft", "numeric_check", "format"]

    preview = submit(client, "POST", f"{drafts}/previews", {
        "revision": revised["revision"], "period": Q2, "baseline_run_id": baseline["id"],
    })
    wait(client, preview["id"])
    preview_result = submit(client, "GET", f"/v1/runs/{preview['id']}/output.json")
    detail = preview_result["diff_details"]
    periods = detail["after_periods"]["net-income"]
    assert [item["year"] for item in periods] == [2090, 2089, 2088, 2087]
    assert all(item["quarter"] == 2 for item in periods)
    assert len(preview_result["sections"][0]["rows"]) == 4
    assert preview_result["sections"][1]["claims"][0]["evidence_ids"]
    assert any(item["state"] == "absent" and not item["required"] for item in preview_result["readiness"].values())
    unchanged = submit(client, "GET", f"{reports}/versions/1")
    assert unchanged["sections"][0]["time"]["preset"] is None

    show("Preview completed against current data without waiting for the quiet period.")
    show("Resolved same-quarter trend: " + ", ".join(f"FY{item['year']} Q{item['quarter']}" for item in periods))
    for item in detail["entries"]:
        if item["entity"] == "row" and item["operation"] == "added":
            show(f"  Added trend row: {item['key']} = {item['after']['actual']}")
        if item["entity"] == "claim":
            old = item["before"]["text"] if item["before"] else ""
            new = item["after"]["text"] if item["after"] else ""
            show(f"  {item['operation'].capitalize()} claim: {old or new}")

    v2 = submit(client, "POST", f"{drafts}/save", {"revision": revised["revision"]})
    assert v2["version"] == 2
    run_path = f"/v1/runs/{preview['id']}"
    html = client.get(f"{run_path}/output.html")
    html.raise_for_status()
    for section in preview_result["sections"]:
        for claim in section["claims"]:
            for citation in claim["citations"]:
                evidence = submit(client, "GET", f"{run_path}/evidence/{citation['id']}")
                assert evidence == citation and f'#e-{citation["id"]}' in html.text
    personal = submit(client, "POST", "/v1/templates", {
        "title": "My earnings brief", "report_id": v2["report_id"], "version": v2["version"],
    })
    recreated = submit(client, "POST", "/v1/drafts", {"template": personal["id"]})
    assert len(recreated["spec"]["sections"]) == 3
    show("Saved v2 and created a personal template that instantiates all 3 sections.")
    show("Preview HTML and JSON carry linked citations.")
    return {"draft": draft, "saved": v2, "baseline": baseline, "preview": preview, "run": preview, "result": preview_result}


def demonstrate_automatic(client, settings: Settings, saved: dict, show=print, pdf_output: Path | None = None):
    if not settings.local or "host=/tmp/aegis-g1." not in settings.report_dsn:
        raise ValueError("The injected-clock demo requires the disposable local fixture")
    owner = LocalAuth(settings.local_user_id).authenticate(None).owner_key(settings.owner_secret)
    # Schedule the fixture job in the future so the wall-clock worker cannot claim it.
    simulated = datetime.now(UTC) + timedelta(hours=1)
    worker = Worker(settings, StubGateway(), clock=lambda: simulated)
    request = RunRequest.model_validate({
        "version": saved["version"], "period": Q3, "request_key": f"{uuid4().hex}-automatic",
    })
    run = Reports(settings.report_dsn, settings.retention_days).enqueue_automatic(
        owner, saved["report_id"], request, simulated,
    )
    path = f"/v1/runs/{run['id']}"
    assert worker.run_one()
    assert submit(client, "GET", path)["state"] == "waiting"
    show(f"Automatic FY2090 Q3 run is waiting after its first probe ({settings.quiet_seconds:g} s quiet period).")
    simulated += timedelta(seconds=max(settings.quiet_seconds, settings.poll_seconds))
    assert worker.run_one()
    assert submit(client, "GET", path)["state"] == "succeeded"
    result = submit(client, "GET", f"{path}/output.json")
    assert result["period"] == Q3
    assert all(item["data_stability"] == "stable" for item in result["readiness"].values() if item["required"])
    assert len(result["sections"]) == 3 and len(result["sections"][0]["rows"]) == 4
    claims = result["sections"][1]["claims"]
    assert {claim["citations"][0]["source"] for claim in claims} >= {"transcripts", "investor_presentation"}
    html = client.get(f"{path}/output.html")
    html.raise_for_status()
    assert all(f'#e-{id_}' in html.text for claim in claims for id_ in claim["evidence_ids"])
    show("After advancing the injected clock, the automatic run rendered cited HTML and JSON for saved v2.")
    show("  FY2090 Q3 themes: " + " | ".join(claim["text"] for claim in claims))
    highlight = result["sections"][2]["claims"][0]
    assert "page 19" in highlight["citations"][0]["locator"]
    show(f"  Slides highlight: {highlight['text']} ({highlight['citations'][0]['locator']})")
    pdf = client.get(f"{path}/output.pdf")
    pdf.raise_for_status()
    assert pdf.content.startswith(b"%PDF-") and pdf.headers["content-type"] == "application/pdf"
    if pdf_output:
        with pdf_output.open("xb") as file:
            file.write(pdf.content)
    show(f"Exported a cited PDF for the finished three-section report ({len(pdf.content)} bytes).")
    return result


def demonstrate_chat(client, wait=wait_for_run, show=print):
    draft = submit(client, "POST", "/v1/drafts", {"bank": "SYN1"})
    dpath = f"/v1/drafts/{draft['id']}"
    saved = submit(client, "POST", f"{dpath}/save", {"revision": draft["revision"]})
    baseline = submit(client, "POST", f"/v1/reports/{saved['report_id']}/runs", {
        "version": saved["version"], "period": Q2, "request_key": f"{uuid4().hex}-chat",
    })
    wait(client, baseline["id"])
    convo = submit(client, "POST", "/v1/conversations", {"draft_id": draft["id"], "period": Q2})
    cpath = f"/v1/conversations/{convo['id']}/turns"
    request = "Add an Efficiency Ratio section for SYN1-CA and SYN2-CA and preview against the saved version."
    turn = submit(client, "POST", cpath, {"message": request, "request_key": "peer-section"})
    tpath = f"{cpath}/{turn['id']}"
    with client.stream("GET", f"{tpath}/events", headers={"Last-Event-ID": str(turn["last_sequence"])}) as stream:
        stream.raise_for_status()
        events = [line.removeprefix("event: ") for line in stream.iter_lines() if line.startswith("event: ")]
    turn = submit(client, "GET", tpath)
    assert turn["state"] == "succeeded" and "patch_proposed" in events and "preview_queued" in events
    show(f"Chat request: {request}")
    show("  Resumed events: " + ", ".join(events))
    show(f"  Proposal at revision {turn['proposal']['revision']}; draft revision before acceptance is "
         f"{submit(client, 'GET', dpath)['revision']}.")
    wait(client, turn["preview_id"])
    result = submit(client, "GET", f"/v1/runs/{turn['preview_id']}/output.json")
    peer = result["sections"][1]["peers"][0]
    assert peer["reason"] is None and peer["median"] == "47.7"
    show(f"  Preview FY2090 Q2 peer median: {peer['median']} {peer['unit']}.")
    assert peer["direction"] == "lower_is_better" and peer["ranks"][0]["bank"] == "SYN1-CA"
    show("  Peer ranking direction: lower is better.")
    for row in peer["ranks"]:
        show(f"    #{row['rank']} {row['bank']}: {row['value']} {peer['unit']}")
    accepted = submit(client, "POST", f"{tpath}/accept", {"revision": turn["proposal"]["revision"]})
    show(f"  Accepted at draft revision {accepted['revision']}.")
    assert result["diff"]["added"] == ["efficiency-ratio"]
    show(f"  Diff against saved v1 adds {', '.join(result['diff']['added'])}.")
    delivery = submit(client, "POST", f"{dpath}/save", {"revision": accepted["revision"]})
    assert delivery["version"] == 2
    show(f"  Saved report version {delivery['version']} explicitly.")


def demonstrate_scheduler(client, show=print):
    draft = submit(client, "POST", "/v1/drafts", {"bank": "SYN1"})
    saved = submit(client, "POST", f"/v1/drafts/{draft['id']}/save", {"revision": draft["revision"]})
    path = f"/v1/reports/{saved['report_id']}/schedule"
    schedule = submit(client, "PUT", path, {
        "version": saved["version"], "period": Q2, "enabled": True, "quiet_seconds": 1,
    })
    show(f"Enabled calendar poller at FY{schedule['next_period']['year']} Q{schedule['next_period']['quarter']}.")
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline:
        rows = submit(client, "GET", path + "/periods")
        complete = {row["period"]["quarter"]: row for row in rows if row["current_kind"] == "complete"}
        if 2 in complete and 3 in complete:
            for quarter in (2, 3):
                result = submit(client, "GET", complete[quarter]["output_url"])
                assert result["publication"] == "complete"
                show(f"  FY2090 Q{quarter}: {complete[quarter]['state']} at generation {complete[quarter]['generation']}.")
            next_period = submit(client, "GET", path)["next_period"]
            assert next_period == {"year": 2090, "quarter": 4}
            show(f"  Next target after publication: FY{next_period['year']} Q{next_period['quarter']}.")
            return
        time.sleep(0.15)
    raise RuntimeError("Calendar poller did not publish both fixture quarters")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url", nargs="?", default="http://127.0.0.1:8000")
    parser.add_argument("--automatic-fixture", action="store_true")
    parser.add_argument("--pdf-output", type=Path)
    args = parser.parse_args()
    with httpx.Client(base_url=args.base_url, timeout=10, trust_env=False) as client:
        settings = Settings.from_env() if args.automatic_fixture else None
        if settings:
            print(f"Worker quiet period: {settings.quiet_seconds:g} s.")
        delivery = demonstrate(client)
        if settings:
            demonstrate_automatic(client, settings, delivery["saved"], pdf_output=args.pdf_output)
            demonstrate_chat(client)
            demonstrate_scheduler(client)


if __name__ == "__main__":
    main()
