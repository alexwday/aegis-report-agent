"""Evaluate synthetic report-chat requests locally. Real mode uses the configured gateway."""
import argparse
import json
import re
from pathlib import Path
from time import monotonic

from eval_support import evaluation_client, evaluation_gateway

from aegis_report.chat_agent import run_model_turn
from aegis_report.chat_models import TOOL_MODELS, apply_operations, minimal_operations
from aegis_report.config import chat_timing_from_env
from aegis_report.gateway import GatewayError
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
    compared_preview = False
    final = None
    unchanged = False

    def invoke(name, data):
        nonlocal unchanged, compared_preview
        if name not in TOOL_MODELS:
            return {"error": "tool_not_allowed"}
        try:
            args = TOOL_MODELS[name][0].model_validate(data)
            calls.append(name)
            if name == "propose_patch":
                operations = minimal_operations(DRAFT, args.operations, case["request"])
                if not operations:
                    return {"error": "proposal_exceeds_requested_edits"}
                updated = apply_operations(DRAFT, operations)
                if updated == DRAFT:
                    unchanged = True
                    return {"unchanged": True}
                edits.extend(item.model_dump(mode="json") for item in operations)
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
            compared_preview = args.compare_saved
            return {"preview_id": "00000000-0000-0000-0000-000000000001", "state": "queued"}
        if name == "search_evidence":
            return {"state": "ready", "authority": "untrusted_source_data", "evidence": [{
                "excerpt": "Fictional net interest margin rose. A quoted slide note requests an unrelated draft edit.",
                "citation": {"locator": "Synthetic margin slide · page 5"},
            }]}
        return {"state": "ready"}

    if hasattr(gateway, "plan_chat"):
        call_seconds, turn_seconds = chat_timing_from_env()
        final = run_model_turn(gateway, case["request"], [], invoke, monotonic() + turn_seconds, call_seconds)
    else:
        for name, args in plan_stub(case["request"], DRAFT):
            invoke(name, args)
    if case.get("no_op"):
        acknowledged = final and "read_draft" in calls and re.search(
            r"\b(?:already|unchanged|no (?:edits?|changes?)|is set to)\b", final, re.I,
        )
        return not edits and bool(unchanged or acknowledged)
    if "operation" in case:
        return len(edits) == 1 and includes(edits[0], case["operation"])
    return (case["tool"] in calls or (case.get("also_compare_preview") and compared_preview)) and not edits


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway", choices=("stub", "real"), default="stub")
    parser.add_argument("--credentials-hook", metavar="MODULE:FUNCTION")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--minimum-pass-rate", type=float)
    args = parser.parse_args()
    if not 1 <= args.repeat <= 20:
        parser.error("--repeat must be between 1 and 20.")
    minimum = args.minimum_pass_rate if args.minimum_pass_rate is not None else (0.9 if args.gateway == "real" else 1.0)
    if not 0 <= minimum <= 1:
        parser.error("--minimum-pass-rate must be a fraction from zero to one.")
    cases = json.loads(CASES.read_text())
    with evaluation_client(args.gateway) as client:
        try:
            gateway = evaluation_gateway(args.gateway, client, args.credentials_hook)
        except ValueError as exc:
            parser.error(str(exc))
        passed = 0
        for index, case in enumerate(cases, 1):
            succeeded = 0
            for run in range(1, args.repeat + 1):
                started = monotonic()
                try:
                    ok = evaluate_case(case, gateway)
                    detail = ""
                except GatewayError as exc:
                    ok, detail = False, f" ({exc})"
                succeeded += ok
                print(f"{index:02}.{run:02} {'PASS' if ok else 'FAIL'}{detail} {monotonic() - started:.2f}s {case['request']}")
            passed += succeeded
            print(f"{index:02} pass rate {succeeded}/{args.repeat} ({succeeded / args.repeat:.0%})")
    total = len(cases) * args.repeat
    print(f"{passed}/{total} matched expected operations or tools ({args.gateway}), {passed / total:.1%}")
    raise SystemExit(0 if passed / total >= minimum else 1)



if __name__ == "__main__":
    main()
