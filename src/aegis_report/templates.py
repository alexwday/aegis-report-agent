from .models import ReportSpec

SYSTEM_TEMPLATES = {
    "quarterly-earnings": ("Quarterly earnings", [
        {"id": "net-income", "title": "Net income", "sources": [{"metric": "Net Income"}],
         "instruction": "Highlight the cited enterprise net income observation."},
    ]),
    "credit-watch": ("Credit and provisions watch", [
        {"id": "credit-quality", "title": "Credit quality highlights", "kind": "highlights",
         "sources": [{"source": "rts", "topic": "Credit Quality & Provisions"}],
         "instruction": "Find cited statements about credit losses and impaired loans.", "output_format": "themes"},
        {"id": "efficiency-trend", "title": "Efficiency ratio trend",
         "sources": [{"metric": "Efficiency Ratio"}], "time": {"compare": "prior_quarter"},
         "instruction": "Show the efficiency ratio and the prior-quarter change."},
    ]),
    "margin-and-capital": ("Margins and capital brief", [
        {"id": "margin-themes", "title": "Margin drivers", "kind": "themes",
         "sources": [{"source": "transcripts", "topics": ["Net Interest Income & Margins"]}],
         "instruction": "Find cited statements about yields, funding and net interest margin.", "output_format": "themes"},
        {"id": "capital-slides", "title": "Capital and liquidity highlights", "kind": "highlights",
         "sources": [{"source": "investor_presentation", "topic": "Capital & Liquidity"}],
         "instruction": "Find cited capital and liquidity disclosures in the investor slides.", "output_format": "themes"},
    ]),
}


def template_index() -> list[dict]:
    return [{"id": key, "title": title, "kind": "system"} for key, (title, _) in SYSTEM_TEMPLATES.items()]


def build_system_template(template_id: str, bank: str) -> ReportSpec:
    title, sections = SYSTEM_TEMPLATES[template_id]
    return ReportSpec.model_validate({"title": title, "sections": [section | {"bank": bank} for section in sections]})
