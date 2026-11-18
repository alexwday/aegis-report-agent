from html import escape

from .claims import draft_themes
from .gateway import GatewayError, ModelGateway
from .models import Period, ReportSpec, SectionSpec, StageKind, compile_section
from .sources import BenchmarkFact, Passage, compute_change


def generate_report(
    spec: ReportSpec, quarter: Period, evidence: dict[str, list[BenchmarkFact | Passage]], gateway: ModelGateway
) -> dict:
    return {
        "title": spec.title,
        "period": quarter.model_dump(),
        "basis": "vendor_fiscal_label",
        "sections": [generate_section(section, quarter, evidence[section.id], gateway) for section in spec.sections],
    }


def generate_section(section: SectionSpec, quarter: Period, evidence: list[BenchmarkFact | Passage], gateway) -> dict:
    rows = [item for item in evidence if isinstance(item, BenchmarkFact)]
    passages = [item for item in evidence if isinstance(item, Passage)]
    comparisons, claims, note = [], [], None
    for stage in compile_section(section):
        if stage.kind is StageKind.CALCULATE:
            comparisons = changes_for(rows, quarter, section.time.comparison_offset())
        if stage.kind is StageKind.DRAFT:
            if section.kind == "themes":
                claims = [claim.model_dump(mode="json") for claim in draft_themes(section.instruction, passages, gateway)]
            else:
                note = draft_note(section.instruction, rows, gateway)
        if stage.kind is StageKind.NUMERIC_CHECK and any(
            row.actual is None or not row.actual.is_finite() or not row.citation.id for row in rows
        ):
            raise GatewayError("invalid_numeric_evidence")
    return {
        "id": section.id,
        "title": section.title,
        "resolved_periods": [quarter.shifted(offset).model_dump() for offset in section.time.resolved_offsets()],
        "rows": [row.model_dump(mode="json") for row in rows],
        "note": note,
        "claims": claims,
        "comparison": comparisons[0] if comparisons else None,
        "comparisons": comparisons,
    }


def changes_for(rows: list[BenchmarkFact], quarter: Period, offset: int) -> list[dict]:
    older = quarter.shifted(offset)

    def key(row):
        return row.bank, row.metric, row.segment

    priors = {key(row): row for row in rows if row.period == older}
    comparisons = []
    for primary in rows:
        baseline = priors.get(key(primary))
        if primary.period == quarter and baseline is not None:
            value = compute_change(primary, baseline)
            comparisons.append({
                "value": str(value) if value is not None else None,
                "basis": primary.change_basis, "metric": primary.metric, "segment": primary.segment,
                "offset": offset, "citation_ids": [primary.citation.id, baseline.citation.id],
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
        if not section["rows"] and not section.get("claims"):
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
