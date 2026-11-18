"""Print compact Markdown examples from the running disposable API."""
import argparse
import json
import re
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from demo import Q2, wait_for_run

UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")


class Capture:
    def __init__(self, client):
        self.client = client
        self.ids = {}

    def normalize(self, text):
        def substitute(match):
            value = match.group()
            if value not in self.ids:
                self.ids[value] = f"00000000-0000-4000-8000-{len(self.ids) + 1:012d}"
            return self.ids[value]

        return UUID.sub(substitute, text)

    def block(self, data, language="json"):
        print(f"```{language}")
        text = data if isinstance(data, str) else json.dumps(data, indent=2, ensure_ascii=False)
        print(self.normalize(text.rstrip()))
        print("```\n")

    def call(self, method, path, body=None, select=lambda data: data, *, status=200):
        response = self.client.request(method, path, json=body)
        assert response.status_code == status, response.text
        result = response.json()
        print(f"### {method} `{self.normalize(path)}`\n")
        if body is not None:
            self.block(body)
        print(f"HTTP {response.status_code} response\n")
        self.block(select(result))
        return result


def selected(*keys):
    return lambda result: {key: result[key] for key in keys}


def capture(client):
    capture = Capture(client)
    call = capture.call
    print("# API examples from the local fixture\n")
    print("Regenerate with `uv run --no-sync python scripts/capture_api_examples.py` while")
    print("`./scripts/dev` is running. Responses are selected fields from the live synthetic API.")
    print("Resource IDs are normalized consistently. Values and state transitions come from the fixture.\n")
    call("GET", "/v1/templates", select=lambda items: items[:1])
    draft = call("POST", "/v1/drafts", {"template": "quarterly-earnings", "bank": "SYN1"},
                 selected("id", "revision", "report_id"), status=201)
    drafts = f"/v1/drafts/{draft['id']}"
    saved = call("POST", drafts + "/save", {"revision": draft["revision"]}, status=201)
    report = f"/v1/reports/{saved['report_id']}"
    base = call("POST", report + "/runs", {"version": 1, "period": Q2, "request_key": str(uuid4())}, status=202)
    base_path = f"/v1/runs/{base['id']}"
    wait_for_run(client, base["id"])
    call("GET", base_path, select=selected("id", "state", "mode", "period"))
    output = client.get(base_path + "/output.json").raise_for_status().json()
    citation_id = output["sections"][0]["rows"][0]["citation"]["id"]
    call("GET", f"{base_path}/evidence/{citation_id}/detail", select=selected("source", "locator", "excerpt"))

    conversation = call("POST", "/v1/conversations", {"draft_id": draft["id"], "period": Q2}, status=201)
    turns = f"/v1/conversations/{conversation['id']}/turns"
    turn = call("POST", turns, {"message": "Make Net income staged.", "request_key": "stage-first"},
                selected("id", "state", "last_sequence"), status=202)
    tpath = f"{turns}/{turn['id']}"
    stream = client.get(tpath + "/events", headers={"Last-Event-ID": str(turn["last_sequence"])})
    stream.raise_for_status()
    print(f"### GET `{capture.normalize(tpath)}/events`\n\n"
          f"The request used `Last-Event-ID: {turn['last_sequence']}`. The first resumed frames follow.\n")
    capture.block("\n\n".join(stream.text.strip().split("\n\n")[:3]), "text")
    final = call("GET", tpath, select=selected("state", "proposal", "last_sequence"))
    accept = call("POST", tpath + "/accept", {"revision": final["proposal"]["revision"]})
    call("POST", drafts + "/save", {"revision": final["proposal"]["revision"]}, status=409)
    gather = call("POST", drafts + "/previews", {
        "revision": accept["revision"], "period": Q2, "section_id": "net-income", "stop_after": "gather",
    }, status=202)
    wait_for_run(client, gather["id"])
    call("GET", f"/v1/runs/{gather['id']}/output.json", select=lambda result: {
        "completion": result["completion"],
        "section": {key: result["sections"][0][key] for key in ("id", "mode", "resolved_periods")},
        "stage_kinds": [stage["kind"] for stage in result["sections"][0]["stage_outputs"]],
        "source": {key: result["readiness"]["net-income:0"][key] for key in ("evidence_state", "message")},
    })

    diff = call("POST", drafts + "/previews", {
        "revision": accept["revision"], "period": Q2, "baseline_run_id": base["id"],
    }, status=202)
    wait_for_run(client, diff["id"])
    call("GET", f"/v1/runs/{diff['id']}/output.json", select=selected("diff", "baseline_run_id"))
    version = call("POST", drafts + "/save", {"revision": accept["revision"]}, status=201)
    call("PUT", report + "/schedule", {"version": version["version"], "enabled": True, "period": Q2})
    scheduled = call("POST", report + "/schedule/enqueue", status=202)
    call("GET", report + "/schedule/runs?limit=1", select=lambda items: [
        {key: row[key] for key in ("id", "version", "period", "state", "error_code")} for row in items
    ])
    print("The schedule run ID is also a normal run resource. The fixture's worker applies the quiet period.\n")
    print(f"### GET `{capture.normalize(base_path)}/output.pdf`\n")
    pdf = client.get(base_path + "/output.pdf").raise_for_status()
    print(f"The saved run returned `HTTP {pdf.status_code}`, `{pdf.headers['content-type']}` and a valid PDF signature.")
    assert pdf.content.startswith(b"%PDF-") and scheduled["id"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    target = urlsplit(args.base_url)
    if target.scheme != "http" or target.hostname != "127.0.0.1" or target.username or target.password:
        parser.error("Use the loopback fixture URL from ./scripts/dev.")
    with httpx.Client(base_url=args.base_url, trust_env=False, timeout=35) as client:
        dev = client.get("/console/context").raise_for_status().json()
        if not dev.get("identities"):
            parser.error("The target must be a local developer fixture.")
        capture(client)


if __name__ == "__main__":
    main()
