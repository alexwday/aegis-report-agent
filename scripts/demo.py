import argparse
import time
from uuid import uuid4

import httpx

Q2 = {"year": 2090, "quarter": 2}
Q3 = {"year": 2090, "quarter": 3}
EFFICIENCY = {
    "id": "efficiency",
    "title": "Efficiency ratio",
    "bank": "SYN1-CA",
    "sources": [{"source": "benchmarking", "metric": "Efficiency Ratio", "segment": "Enterprise"}],
    "time": {"offsets": [0], "compare_offset": -1},
    "instruction": "Highlight the cited ratio and show a change from the prior fiscal quarter.",
    "output_format": "table_with_note",
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
        time.sleep(0.15)
    raise RuntimeError("Worker did not finish within the demo window")


def demonstrate(client, wait=wait_for_run, show=print):
    run_prefix = uuid4().hex
    draft = submit(client, "POST", "/v1/drafts", {"template": "quarterly-earnings", "bank": "SYN1-CA"})
    drafts = f"/v1/drafts/{draft['id']}"
    show("Draft created from the quarterly earnings template.")

    saved = submit(client, "POST", f"{drafts}/save", {"revision": draft["revision"]})
    reports = f"/v1/reports/{saved['report_id']}"
    baseline = submit(client, "POST", f"{reports}/runs", {
        "version": 1, "period": Q2, "request_key": f"{run_prefix}-baseline",
    })
    wait(client, baseline["id"])
    show("Saved baseline v1 generated for FY2090 Q2.")

    patched = submit(client, "PATCH", drafts, {
        "revision": saved["draft_revision"], "op": "add_section", "section": EFFICIENCY,
    })
    stage_list = submit(client, "GET", f"{drafts}/stages")
    kinds = [stage["kind"] for stage in stage_list[1]["stages"]]
    assert kinds == ["retrieve", "calculate", "draft", "numeric_check", "format"]
    show("Efficiency section compiled: " + " → ".join(kinds))

    preview = submit(client, "POST", f"{drafts}/previews", {
        "revision": patched["revision"], "period": Q2, "baseline_run_id": baseline["id"], "section_id": "efficiency",
    })
    wait(client, preview["id"])
    preview_result = submit(client, "GET", f"/v1/runs/{preview['id']}/output.json")
    diff = preview_result["diff"]
    assert diff == {"added": ["efficiency"], "removed": [], "changed": []}
    unchanged = submit(client, "GET", f"{reports}/versions/1")
    assert [section["id"] for section in unchanged["sections"]] == ["net-income"]
    show("Preview diff against v1 (FY2090 Q2): added efficiency. Saved v1 retains its original section.")

    v2 = submit(client, "POST", f"{drafts}/save", {"revision": patched["revision"]})
    assert v2["version"] == 2
    next_run = submit(client, "POST", f"{reports}/runs", {
        "version": v2["version"], "period": Q3, "request_key": f"{run_prefix}-next-quarter",
    })
    wait(client, next_run["id"])
    run_path = f"/v1/runs/{next_run['id']}"
    result = submit(client, "GET", f"{run_path}/output.json")
    html = client.get(f"{run_path}/output.html")
    html.raise_for_status()
    efficiency = result["sections"][1]
    citation = efficiency["rows"][0]["citation"]
    evidence = submit(client, "GET", f"{run_path}/evidence/{citation['id']}")
    assert evidence == citation and f'#e-{citation["id"]}' in html.text
    assert result["period"] == Q3 and efficiency["comparison"]["basis"] == "basis_points"
    assert efficiency["comparison"]["value"] == "-40.0"
    show("Saved v2 generated for FY2090 Q3 by the worker with the stub LLM.")
    show(f"HTML and JSON have {len(result['sections'])} sections with citations.")
    show(f"Efficiency change: {efficiency['comparison']['value']} basis points.")
    show(f"Citation: {citation['locator']}")
    return {"draft": draft, "saved": v2, "baseline": baseline, "preview": preview, "run": next_run, "result": result}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url", nargs="?", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    with httpx.Client(base_url=args.base_url, timeout=10, trust_env=False) as client:
        demonstrate(client)


if __name__ == "__main__":
    main()
