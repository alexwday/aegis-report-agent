from html import escape

from .gateway import GatewayError, ModelGateway
from .models import Period, ReportSpec, StageKind, compile_section
from .sources import BenchmarkFact, compute_change


def generate_report(
    spec: ReportSpec, quarter: Period, facts: dict[str, dict[int, BenchmarkFact]], gateway: ModelGateway
) -> dict:
    output = {"title": spec.title, "period": quarter.model_dump(), "basis": "vendor_fiscal_label", "sections": []}
    for section in spec.sections:
        observations = facts[section.id]
        stages = compile_section(section)
        rows = [observations[offset] for offset in sorted(observations, reverse=True)]
        primary = observations.get(0)
        change, note = None, None
        for stage in stages:
            if stage.kind is StageKind.CALCULATE:
                baseline = observations.get(section.time.compare_offset)
                if primary is None or baseline is None:
                    continue
                value = compute_change(primary, baseline)
                change = {
                    "value": str(value) if value is not None else None,
                    "basis": primary.change_basis,
                    "offset": section.time.compare_offset,
                    "citation_ids": [primary.citation.id, baseline.citation.id],
                }
            if stage.kind is StageKind.DRAFT:
                choice = gateway.choose_observation(section.instruction, [row.citation.id for row in rows])
                if choice is not None:
                    cited = next((row for row in rows if row.citation.id == choice), None)
                    if cited is None:
                        raise GatewayError("invalid_model_output")
                    note = {"citation_id": choice, "text": f"{cited.metric} for {cited.period}: {display_value(cited)}."}
            if stage.kind is StageKind.NUMERIC_CHECK:
                if any(row.actual is None or not row.actual.is_finite() or not row.citation.id for row in rows):
                    raise GatewayError("invalid_numeric_evidence")
        output["sections"].append({
            "id": section.id,
            "title": section.title,
            "rows": [row.model_dump(mode="json") for row in rows],
            "note": note,
            "comparison": change,
        })
    return output


def display_value(fact: BenchmarkFact) -> str:
    suffix = f" {fact.unit}" if fact.unit and fact.unit != "%" else fact.unit or " (unit unknown)"
    currency = f" {fact.currency} (unconfirmed)" if fact.currency else ""
    return f"{fact.actual}{suffix}{currency}"


def report_diff(baseline: dict, preview: dict) -> dict[str, list[str]]:
    before = {section["id"]: section for section in baseline["sections"]}
    after = {section["id"]: section for section in preview["sections"]}
    return {
        "added": sorted(after.keys() - before.keys()),
        "removed": sorted(before.keys() - after.keys()),
        "changed": sorted(key for key in before.keys() & after.keys() if before[key] != after[key]),
    }


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
        blocks.extend([
            f"<section><h2>{escape(section['title'])}</h2>",
            "<table><thead><tr><th>Bank</th><th>Fiscal period</th><th>Reported value</th><th>Evidence</th>"
            "</tr></thead><tbody>",
        ])
        for row in section["rows"]:
            fact = BenchmarkFact.model_validate(row)
            sources[fact.citation.id] = fact.citation.locator
            blocks.append(
                f"<tr><td>{escape(fact.bank)}</td><td>{escape(str(fact.period))}</td>"
                f"<td>{escape(display_value(fact))}</td><td>{citation_link(fact.citation.id)}</td></tr>"
            )
        blocks.append("</tbody></table>")
        note = section["note"]
        if note:
            blocks.append(f"<p>{escape(note['text'])} {citation_link(note['citation_id'])}</p>")
        change = section["comparison"]
        if change:
            label = f"{change['value']} {change['basis'].replace('_', ' ')}" if change["value"] else "Unavailable"
            links = " ".join(citation_link(cite) for cite in change["citation_ids"])
            blocks.append(f"<p>Change versus {abs(change['offset'])} fiscal quarter(s) earlier: {escape(label)}. {links}</p>")
        blocks.append("</section>")
    blocks.append("<section><h2>Sources</h2><ol>")
    for citation_id, locator in sources.items():
        blocks.append(f'<li id="e-{escape(citation_id)}">{escape(locator)}</li>')
    blocks.append("</ol></section></main></html>")
    return "\n".join(blocks)
