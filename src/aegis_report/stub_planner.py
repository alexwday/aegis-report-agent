import re

from .models import ReportSpec, SectionSpec


def plan_stub(message: str, spec: ReportSpec) -> list[tuple[str, dict]]:
    """Local deterministic intent fixtures. Real language planning uses function calls."""
    text = message.casefold()
    matched = [item for item in spec.sections if item.id in text or item.title.casefold() in text]
    target = max(matched, key=lambda item: len(item.title)) if matched else spec.sections[0]
    if re.search(r"\b(?:build|prepare|draft)\b.*\breport\b", text):
        setup = new_section(text, target)
        if setup:
            operations = []
            if setup["id"] == target.id:
                operations.append({"op": "set_banks", "section_id": target.id,
                                   **{key: setup[key] for key in ("banks", "peer_group") if key in setup}})
                if "four quarters" in text:
                    setup["time"] = {"preset": {"kind": "trailing_quarters", "count": 4}}
                if "time" in setup:
                    operations.append({"op": "set_time", "section_id": target.id, "time": setup["time"]})
            else:
                operations.append({"op": "add_section", "section": setup})
            return [("propose_patch", {"operations": operations})]
    if re.search(r"\b(?:add|create|insert)\b", text):
        section = new_section(text, target)
        if section:
            steps = [("propose_patch", {"operations": [{"op": "add_section", "section": section}]})]
            if "preview" in text:
                steps.append(("start_preview", {"compare_saved": "saved" in text}))
            return steps
    if re.search(r"\b(?:drop|remove|delete)\b", text):
        return patch("remove_section", target)
    if ("move" in text or "put" in text) and ("first" in text or "last" in text):
        others = [item.id for item in spec.sections if item.id != target.id]
        order = [target.id, *others] if "first" in text else [*others, target.id]
        return [("propose_patch", {"operations": [{"op": "reorder_sections", "section_ids": order}]})]
    if "replace" in text:
        section = new_section(text, target)
        if section:
            return [("propose_patch", {"operations": [
                {"op": "replace_section", "section": section | {"id": target.id}},
            ]})]
    if "staged" in text or "gathered evidence first" in text:
        return patch("set_mode", target, mode="staged")
    if "one step" in text or "one-step" in text:
        return patch("set_mode", target, mode="one_step")
    if "big six" in text or "six big banks" in text or "big 6" in text:
        return patch("set_banks", target, peer_group="big-6-canadian-banks")
    banks = specified_banks(text)
    if banks:
        return patch("set_banks", target, banks=banks)
    if "current quarter" in text and ("only" in text or "just" in text):
        return patch("set_time", target, time={"offsets": [0]})
    if "same quarter last year" in text or "year over year" in text or re.search(r"\bcompare(?:d)? (?:with|to) last year\b", text):
        return patch("set_time", target, time={"compare": "prior_year"})
    if "prior quarter" in text or "previous quarter" in text:
        return patch("set_time", target, time={"compare": "prior_quarter"})
    if "four years" in text:
        return patch("set_time", target, time={"preset": {"kind": "same_quarter_years", "count": 4}})
    if "four quarters" in text:
        return patch("set_time", target, time={"preset": {"kind": "trailing_quarters", "count": 4}})
    if "table only" in text or "just the table" in text:
        return patch("set_output_format", target, output_format="table")
    if "table with a note" in text:
        return patch("set_output_format", target, output_format="table_with_note")
    if "plain" in text and ("short" in text or "brief" in text):
        return patch("set_instruction", target, instruction="Use plain language and keep the explanation short.")
    if "use rts" in text or "use the shareholder report" in text:
        return patch("set_sources", target, sources=[{"source": "rts", "terms": ["net interest margin"]}])
    if "what changed" in text:
        return [("explain_diff", {})]
    if "preview" in text:
        args = {"compare_saved": True} if "saved" in text else {}
        if "gather" in text:
            args |= {"section_id": target.id, "stop_after": "gather"}
        return [("start_preview", args)]
    if "evidence" in text or "coverage" in text:
        tool = "search_evidence" if "evidence" in text else "inspect_coverage"
        return [(tool, {"bank": target.bank_symbols()[0], "selector": target.sources[0].model_dump(mode="json")})]
    if "draft" in text:
        return [("read_draft", {})]
    return []


def patch(op: str, target: SectionSpec, **details) -> list[tuple[str, dict]]:
    return [("propose_patch", {"operations": [{"op": op, "section_id": target.id, **details}]})]


def specified_banks(text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"\b[A-Z0-9.]{1,7}-[A-Z]{2}\b", text.upper())))


def new_section(text: str, target: SectionSpec) -> dict | None:
    if "margin" in text:
        metric = "Net Interest Margin"
    elif "efficiency" in text:
        metric = "Efficiency Ratio"
    elif "net income" in text:
        metric = "Net Income"
    else:
        return None
    detail = {
        "id": metric.casefold().replace(" ", "-"), "title": metric,
        "sources": [{"source": "benchmarking", "metric": metric}],
        "instruction": f"Compare cited {metric.lower()} values.", "output_format": "table",
    }
    if "big six" in text or "six big banks" in text or "big 6" in text:
        detail["peer_group"] = "big-6-canadian-banks"
    elif banks := specified_banks(text):
        detail["banks"] = banks
    elif target.peer_group:
        detail["peer_group"] = target.peer_group
    else:
        detail["banks"] = list(target.bank_symbols())
    if "four years" in text:
        detail["time"] = {"preset": {"kind": "same_quarter_years", "count": 4}}
    return detail
