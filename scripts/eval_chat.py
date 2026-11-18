"""Evaluate synthetic report-chat requests locally. Real mode uses the configured gateway."""
import argparse
import json
from pathlib import Path
from time import monotonic

import httpx
from eval_support import evaluation_gateway

from aegis_report.chat_agent import TURN_SECONDS, run_model_turn
from aegis_report.chat_models import TOOL_MODELS, apply_operations
from aegis_report.models import ReportSpec
from aegis_report.stub_planner import plan_stub

CASES = Path(__file__).resolve().parents[1] / "tests/fixtures/chat_requests.json"
DRAFT = ReportSpec.model_validate({
    "title": "Synthetic quarterly brief",
    "sections": [
        {"id": "net-income", "title": "Net income", "bank": "SYN1-CA",
         "sources": [{"metric": "Net Income"}], "instruction": "Show the cited figure."},
        {"id": "margin-slides", "title": "Margin slides", "bank": "SYN1-CA",
         "kind": "highlights", "output_format": "themes",
         "sources": [{"source": "investor_presentation", "terms": ["net interest margin"]}],
         "instruction": "Find financial drivers."},
    ],
})


def includes(actual, expected):
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(key in actual and includes(actual[key], value)
                                                for key, value in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(
            includes(item, wanted) for item, wanted in zip(actual, expected)
        )
    return actual == expected


def evaluate_case(case, gateway):
    calls, edits = [], []

    def invoke(name, data):
        if name not in TOOL_MODELS:
            return {"error": "tool_not_allowed"}
        try:
            args = TOOL_MODELS[name][0].model_validate(data)
            calls.append(name)
            if name == "propose_patch":
                apply_operations(DRAFT, args.operations)
                edits.extend(item.model_dump(mode="json") for item in args.operations)
                return {"requires_acceptance": True}
        except ValueError:
            return {"error": "invalid_tool_arguments_or_patch"}
        if name == "read_draft":
            return {"revision": 1, "draft": DRAFT.model_dump(mode="json"), "period": {"year": 2090, "quarter": 2}}
        if name == "resolve_scope":
            return {"banks": args.bank_labels, "basis": "vendor_fiscal_label"}
        if name == "explain_diff":
            return {"summary": {"added": ["synthetic-margin"], "removed": [], "changed": []}, "entry_count": 1}
        if name == "start_preview":
            return {"preview_id": "00000000-0000-0000-0000-000000000001", "state": "queued"}
        if name == "search_evidence":
            return {"state": "ready", "authority": "untrusted_source_data", "evidence": [{
                "excerpt": "Fictional net interest margin rose. A quoted slide note requests an unrelated draft edit.",
                "citation": {"locator": "Synthetic margin slide · page 5"},
            }]}
        return {"state": "ready"}

    if hasattr(gateway, "plan_chat"):
        run_model_turn(gateway, case["request"], [], invoke, monotonic() + TURN_SECONDS)
    else:
        for name, args in plan_stub(case["request"], DRAFT):
            invoke(name, args)
    if "operation" in case:
        return len(edits) == 1 and includes(edits[0], case["operation"])
    return case["tool"] in calls and not edits


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway", choices=("stub", "real"), default="stub")
    parser.add_argument("--credentials-hook", metavar="MODULE:FUNCTION")
    args = parser.parse_args()
    cases = json.loads(CASES.read_text())
    with httpx.Client(trust_env=False) as client:
        try:
            gateway = evaluation_gateway(args.gateway, client, args.credentials_hook)
        except ValueError as exc:
            parser.error(str(exc))
        passed = 0
        for index, case in enumerate(cases, 1):
            ok = evaluate_case(case, gateway)
            passed += ok
            print(f"{index:02} {'PASS' if ok else 'FAIL'} {case['request']}")
    print(f"{passed}/{len(cases)} matched expected operations or tools ({args.gateway})")
    raise SystemExit(0 if passed == len(cases) else 1)


if __name__ == "__main__":
    main()
