import re
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

from .engine import display_value
from .models import Period
from .sources import BenchmarkFact

FONT_DIR = Path(reportlab.__file__).resolve().parent / "fonts"
pdfmetrics.registerFont(TTFont("ReportSans", str(FONT_DIR / "Vera.ttf")))
pdfmetrics.registerFont(TTFont("ReportSansBold", str(FONT_DIR / "VeraBd.ttf")))

INK = colors.HexColor("#162638")
MUTED = colors.HexColor("#485D70")
ACCENT = colors.HexColor("#075F6B")
RULE = colors.HexColor("#D8E2E9")
TINT = colors.HexColor("#F0F5F8")
CONTENT_WIDTH = letter[0] - 100


def text(value: object) -> str:
    return escape(re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(value)))


def report_citations(result: dict) -> dict[str, dict]:
    indexed = {}
    for section in result["sections"]:
        for row in section["rows"]:
            indexed.setdefault(row["citation"]["id"], row["citation"])
        for claim in section.get("claims", []):
            for citation in claim["citations"]:
                indexed.setdefault(citation["id"], citation)
    return indexed


def comparison_text(change: dict) -> str:
    metric = f"{change['metric']} " if change.get("metric") else ""
    if change["value"] is None:
        return f"{metric}change unavailable"
    count = abs(change["offset"])
    direction = f"{count} fiscal quarter{'s' if count != 1 else ''} earlier"
    provenance = {
        "vendor_qoq": "vendor QoQ",
        "vendor_yoy": "vendor YoY",
        "rounded_actuals": "calculated from rounded reported values",
    }.get(change.get("provenance"))
    detail = f" · {provenance}" if provenance else ""
    return f"{metric}change versus {direction} · {change['value']} {change['basis'].replace('_', ' ')}{detail}"


def render_pdf(result: dict) -> bytes:
    styles = {
        "title": ParagraphStyle("ReportTitle", fontName="ReportSansBold", fontSize=24, leading=29,
                                textColor=INK, spaceAfter=10, keepWithNext=True),
        "heading": ParagraphStyle("ReportHeading", fontName="ReportSansBold", fontSize=14, leading=19,
                                  textColor=INK, spaceBefore=17, spaceAfter=7, keepWithNext=True),
        "body": ParagraphStyle("ReportBody", fontName="ReportSans", fontSize=10, leading=15,
                               textColor=INK, spaceAfter=7, alignment=TA_LEFT),
        "meta": ParagraphStyle("ReportMeta", fontName="ReportSans", fontSize=9, leading=13,
                               textColor=MUTED, spaceAfter=9),
        "cell": ParagraphStyle("ReportCell", fontName="ReportSans", fontSize=9, leading=13, textColor=INK),
        "column": ParagraphStyle("ReportColumn", fontName="ReportSansBold", fontSize=9, leading=13, textColor=INK),
    }
    citations = report_citations(result)
    numbers = {id_: rank for rank, id_ in enumerate(citations, 1)}

    def references(ids):
        return " ".join(
            f'<link href="#source-{numbers[id_]}" color="#075F6B">[{numbers[id_]}]</link>'
            for id_ in dict.fromkeys(ids) if id_ in numbers
        )

    def paragraph(value, style="body", ids=()):
        return Paragraph(text(value) + (f"  {references(ids)}" if ids else ""), styles[style])

    parts = [
        paragraph(result["title"], "title"),
        paragraph(f"{Period.model_validate(result['period'])}  ·  Vendor fiscal labels", "meta"),
    ]
    unconfirmed = sum(entry["state"] != "ready" or entry.get("data_stability") != "stable"
                      for entry in result.get("readiness", {}).values())
    if unconfirmed:
        parts.append(paragraph(f"{unconfirmed} source scope(s) have incomplete or unconfirmed readiness.", "meta"))
    for section in result["sections"]:
        parts.append(paragraph(section["title"], "heading"))
        if section.get("resolved_periods"):
            parts.append(paragraph(" · ".join(str(Period.model_validate(item)) for item in section["resolved_periods"]),
                                   "meta"))
        if section["rows"]:
            rows = [[paragraph(label, "column") for label in ("Bank", "Metric", "Period", "Reported value", "Source")]]
            for row in section["rows"]:
                fact = BenchmarkFact.model_validate(row)
                rows.append([
                    paragraph(fact.bank, "cell"), paragraph(fact.metric, "cell"), paragraph(fact.period, "cell"),
                    paragraph(display_value(fact), "cell"), Paragraph(references([fact.citation.id]), styles["cell"]),
                ])
            table = LongTable(rows, colWidths=(64, 143, 86, 157, CONTENT_WIDTH - 450), repeatRows=1, hAlign="LEFT")
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), TINT),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, 0), 0.65, RULE),
                ("LINEBELOW", (0, 1), (-1, -1), 0.35, RULE),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]))
            parts.extend([table, Spacer(1, 8)])
        for change in section.get("comparisons") or [section.get("comparison")]:
            if change:
                parts.append(paragraph(comparison_text(change), "meta", change["citation_ids"]))
        note = section.get("note")
        if note:
            parts.append(paragraph(note["text"], ids=[note["citation_id"]]))
        for claim in section.get("claims", []):
            parts.append(paragraph(f"{claim['topic']} · {claim['text']}", ids=claim["evidence_ids"]))
        if not section["rows"] and not section.get("claims"):
            parts.append(paragraph("No cited evidence matched this section.", "meta"))

    if citations:
        footnotes = [paragraph("Sources", "heading")]
        for id_, citation in citations.items():
            number = numbers[id_]
            footnotes.append(Paragraph(
                f'<a name="source-{number}"/>[{number}] {text(citation["locator"])}', styles["meta"],
            ))
        if len(footnotes) <= 13:
            parts.append(KeepTogether(footnotes))
        else:
            parts.extend(footnotes)

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(RULE)
        canvas.line(50, 39, letter[0] - 50, 39)
        canvas.setFillColor(MUTED)
        canvas.setFont("ReportSans", 8)
        canvas.drawString(50, 25, "Aegis Report Agent")
        canvas.drawRightString(letter[0] - 50, 25, str(doc.page))
        canvas.restoreState()

    output = BytesIO()
    doc = SimpleDocTemplate(
        output, pagesize=letter, leftMargin=50, rightMargin=50, topMargin=47, bottomMargin=53,
        title=str(result["title"]), author="Aegis Report Agent",
    )
    doc.build(parts, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
