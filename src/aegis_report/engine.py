from html import escape

from .claims import INSTRUCTION_TEXT, SPEAKER_TAG, draft_themes
from .gateway import GatewayError, ModelGateway
from .models import Period, ReportSpec, SectionSpec, StageKind, compile_section
from .sources import BenchmarkFact, Passage, compute_change


def generate_report(
    spec: ReportSpec, quarter: Period, evidence: dict[str, list[BenchmarkFact | Passage]], gateway: ModelGateway,
    *, trace: bool = False, gather_only: bool = False,
) -> dict:
    return {
        "title": spec.title,
        "period": quarter.model_dump(),
        "basis": "vendor_fiscal_label",
        "completion": "gathered" if gather_only else "finished",
        "sections": [
            generate_section(section, quarter, evidence[section.id], gateway, trace=trace, gather_only=gather_only)
            for section in spec.sections
        ],
    }


def evidence_excerpt(text: str) -> str:
    body = " ".join(SPEAKER_TAG.sub("", text, count=1).split())
    return body if len(body) <= 260 else body[:257].rsplit(" ", 1)[0] + "…"


def gathered_passages(passages: list[Passage]) -> list[dict]:
    distinct = {}
    for passage in passages:
        if INSTRUCTION_TEXT.search(passage.text):
            continue
        distinct.setdefault(passage.citation.id, {
            "excerpt": evidence_excerpt(passage.text),
            "citation": passage.citation.model_dump(mode="json"),
            "period": passage.period.model_dump(),
            "topics": list(passage.topics),
        })
        if len(distinct) == 50:
            break
    return list(distinct.values())


def generate_section(
    section: SectionSpec, quarter: Period, evidence: list[BenchmarkFact | Passage], gateway,
    *, trace: bool = False, gather_only: bool = False,
) -> dict:
    rows = [item for item in evidence if isinstance(item, BenchmarkFact)]
    passages = [item for item in evidence if isinstance(item, Passage)]
    row_data = [row.model_dump(mode="json") for row in rows]
    output = {
        "id": section.id, "title": section.title, "mode": section.mode,
        "resolved_periods": [quarter.shifted(offset).model_dump() for offset in section.time.resolved_offsets()],
    }
    stages = []
    comparisons, claims, note = [], [], None
    for stage in compile_section(section):
        if stage.kind is StageKind.RETRIEVE:
            if trace or gather_only:
                stages.append({"kind": stage.kind, "rows": row_data, "passages": gathered_passages(passages)})
            if gather_only:
                break
        elif stage.kind is StageKind.CALCULATE:
            comparisons = changes_for(rows, quarter, section.time.comparison_offset())
            if trace:
                stages.append({"kind": stage.kind, "comparisons": comparisons})
        elif stage.kind is StageKind.DRAFT:
            if section.kind in ("themes", "highlights"):
                claims = [claim.model_dump(mode="json") for claim in draft_themes(section.instruction, passages, gateway)]
            else:
                note = draft_note(section.instruction, rows, gateway)
            if trace:
                stages.append({"kind": stage.kind, "claims": claims, "note": note})
        elif stage.kind is StageKind.NUMERIC_CHECK:
            if any(row.actual is None or not row.actual.is_finite() or not row.citation.id for row in rows):
                raise GatewayError("invalid_numeric_evidence")
            if trace:
                stages.append({"kind": stage.kind, "validated_rows": len(rows)})
    blocks = {
        "rows": [] if gather_only else row_data,
        "claims": claims, "note": note, "comparison": comparisons[0] if comparisons else None,
        "comparisons": comparisons,
    }
    if trace and not gather_only:
        stages.append({"kind": "format", "blocks": blocks})
    return output | blocks | {"stage_outputs": stages}


def changes_for(rows: list[BenchmarkFact], quarter: Period, offset: int) -> list[dict]:
    older = quarter.shifted(offset)

    def key(row):
        return row.bank, row.metric, row.segment

    priors = {key(row): row for row in rows if row.period == older}
    comparisons = []
    for primary in rows:
        baseline = priors.get(key(primary))
        if primary.period == quarter and baseline is not None:
            vendor = {-1: primary.raw_qoq, -4: primary.raw_yoy}.get(offset)
            usable_vendor = primary.change_basis != "unknown" and vendor is not None and vendor.is_finite()
            value = vendor if usable_vendor else compute_change(primary, baseline)
            origin = {-1: "vendor_qoq", -4: "vendor_yoy"}[offset] if usable_vendor else "rounded_actuals"
            comparisons.append({
                "value": str(value) if value is not None else None,
                "basis": primary.change_basis, "metric": primary.metric, "segment": primary.segment,
                "offset": offset, "citation_ids": [primary.citation.id, baseline.citation.id],
                "provenance": origin if value is not None else None,
            })
    return comparisons


def draft_note(instruction: str, rows: list[BenchmarkFact], gateway) -> dict | None:
    choice = gateway.choose_observation(instruction, [row.citation.id for row in rows])
    if choice is None:
        return None
    cited = next((row for row in rows if row.citation.id == choice), None)
    if cited is None:
        raise GatewayError("invalid_model_output")
    return {"citation_id": choice, "text": f"{cited.metric} for {cited.period}: {display_value(cited)}."}


def display_value(fact: BenchmarkFact) -> str:
    suffix = f" {fact.unit}" if fact.unit and fact.unit != "%" else fact.unit or " (unit unknown)"
    currency = f" {fact.currency} (unconfirmed)" if fact.currency else ""
    return f"{fact.actual}{suffix}{currency}"


def render_html(result: dict) -> str:
    def citation_link(citation_id: str) -> str:
        return f'<a href="#e-{escape(citation_id)}">source</a>'

    title = escape(result["title"])
    blocks = [
        '<!doctype html><html lang="en"><meta charset="utf-8">',
        f"<title>{title}</title><main><h1>{title}</h1>",
        f"<p>{escape(str(Period.model_validate(result['period'])))} · Vendor fiscal labels</p>",
    ]
    for key, observation in result.get("readiness", {}).items():
        if observation.get("evidence_state") == "no_match":
            selector = observation.get("selector") or {}
            focus = selector.get("topic") or ", ".join(selector.get("topics") or selector.get("terms") or [])
            blocks.append(f"<p>No evidence matched {escape(focus or key)}.</p>")
        if observation.get("data_stability") != "stable" or observation["state"] != "ready":
            scope = " · ".join(str(value) for value in (
                observation.get("bank"), observation.get("source"),
                str(Period.model_validate(observation["period"])) if observation.get("period") else None,
            ) if value)
            blocks.append(
                f"<p>{escape(scope or key)}: {escape(observation['state'])}, "
                f"stability {escape(observation.get('data_stability', 'unknown').replace('_', ' '))}.</p>"
            )
    sources = {}
    for section in result["sections"]:
        blocks.append(f"<section><h2>{escape(section['title'])}</h2>")
        periods = ", ".join(str(Period.model_validate(item)) for item in section.get("resolved_periods", []))
        if periods:
            blocks.append(f"<p>Resolved periods: {escape(periods)}</p>")
        if result.get("completion") == "gathered":
            gather = section.get("stage_outputs", [])[0]
            blocks.append(f"<p>Gathered {len(gather['rows'])} rows and {len(gather['passages'])} passages.</p>")
            for passage in gather["passages"]:
                citation = passage["citation"]
                sources[citation["id"]] = citation["locator"]
                blocks.append(f"<p>{escape(passage['excerpt'])} {citation_link(citation['id'])}</p>")
        elif not section["rows"] and not section.get("claims"):
            blocks.append("<p>No cited evidence matched this section.</p>")
        if section["rows"]:
            blocks.append(
                "<table><thead><tr><th>Bank</th><th>Metric</th><th>Fiscal period</th>"
                "<th>Reported value</th><th>Evidence</th></tr></thead><tbody>"
            )
            for row in section["rows"]:
                fact = BenchmarkFact.model_validate(row)
                sources[fact.citation.id] = fact.citation.locator
                blocks.append(
                    f"<tr><td>{escape(fact.bank)}</td><td>{escape(fact.metric)}</td><td>{escape(str(fact.period))}</td>"
                    f"<td>{escape(display_value(fact))}</td><td>{citation_link(fact.citation.id)}</td></tr>"
                )
            blocks.append("</tbody></table>")
        note = section["note"]
        if note:
            blocks.append(f"<p>{escape(note['text'])} {citation_link(note['citation_id'])}</p>")
        for change in section.get("comparisons") or [section["comparison"]]:
            if change:
                label = f"{change['value']} {change['basis'].replace('_', ' ')}" if change["value"] else "Unavailable"
                if change.get("provenance") == "rounded_actuals":
                    label += " (calculated from rounded reported values)"
                elif change.get("provenance") in ("vendor_qoq", "vendor_yoy"):
                    label += " (vendor " + change["provenance"].removeprefix("vendor_").upper() + ")"
                links = " ".join(citation_link(cite) for cite in change["citation_ids"])
                metric = f"{escape(change['metric'])}: " if change.get("metric") else ""
                blocks.append(
                    f"<p>{metric}change versus {abs(change['offset'])} fiscal quarter(s) earlier: "
                    f"{escape(label)}. {links}</p>"
                )
        for claim in section.get("claims", []):
            for citation in claim["citations"]:
                sources[citation["id"]] = citation["locator"]
            refs = " ".join(citation_link(id_) for id_ in claim["evidence_ids"])
            blocks.append(f"<p><strong>{escape(claim['topic'])}</strong> · {escape(claim['text'])} {refs}</p>")
        blocks.append("</section>")
    blocks.append("<section><h2>Sources</h2><ol>")
    for citation_id, locator in sources.items():
        blocks.append(f'<li id="e-{escape(citation_id)}">{escape(locator)}</li>')
    blocks.append("</ol></section></main></html>")
    return "\n".join(blocks)
