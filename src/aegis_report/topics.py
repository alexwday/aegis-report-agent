import re

TOPIC_TERMS = {
    "Strategic Initiatives & Transformation": ("strategic priorities", "transformation", "operating model", "integration"),
    "Revenue & Growth": ("revenue growth", "sales growth", "client growth", "fee income"),
    "Capital & Liquidity": ("CET1", "common equity tier 1", "capital ratio", "liquidity coverage", "risk-weighted assets"),
    "Macro & Market Environment": ("interest rates", "economic growth", "inflation", "market volatility"),
    "Net Interest Income & Margins": ("net interest margin", "NIM", "net interest income", "margin", "funding costs", "deposit costs"),
    "Profitability & Returns": ("net income", "return on equity", "return on tangible equity", "earnings per share"),
    "Expenses & Efficiency": ("non-interest expense", "efficiency ratio", "operating leverage", "expense growth"),
    "Wealth & Asset Management": ("assets under management", "net flows", "wealth management", "asset management"),
    "Commercial & Corporate Banking": ("commercial lending", "corporate banking", "business loans", "commercial deposits"),
    "Geographic & International": ("international banking", "geographic segments", "cross-border", "US banking"),
    "Capital Markets & Investment Banking": ("investment banking", "advisory fees", "equity underwriting", "debt capital markets"),
    "Credit Quality & Provisions": ("provision for credit losses", "provisions for credit losses", "PCL", "impaired loans", "allowance", "credit quality"),
    "Consumer & Retail Banking": ("personal banking", "mortgage balances", "consumer lending", "retail deposits"),
    "Technology & Digital Innovation": ("technology investment", "digital adoption", "automation", "cloud migration"),
    "Customer & Client Experience": ("customer satisfaction", "client experience", "customer retention", "service quality"),
    "Trading & Markets": ("trading revenue", "fixed income trading", "market making", "equity trading"),
    "Workforce & Talent": ("headcount", "employee turnover", "talent development", "compensation"),
    "Regulatory & Compliance": ("regulatory requirements", "compliance costs", "supervisory review", "regulatory capital"),
    "Payments & Transaction Services": ("payment volumes", "transaction banking", "cash management", "merchant acquiring"),
    "Risk Management & Cybersecurity": ("operational risk", "risk controls", "cybersecurity", "risk appetite"),
    "Non-Relevant": (),
    "ESG & Sustainability": ("financed emissions", "sustainable finance", "climate risk", "transition plan"),
    "Digital Assets & Emerging Payments": ("digital assets", "stablecoins", "tokenization", "real-time payments"),
}
_BY_LABEL = {label.casefold(): terms for label, terms in TOPIC_TERMS.items()}


def search_terms(topics: tuple[str, ...], custom: tuple[str, ...] = ()) -> tuple[str, ...]:
    expressions = (*custom, *(term for label in topics for term in _BY_LABEL.get(label.casefold(), (label,))))
    return tuple(dict.fromkeys(term.strip().casefold() for term in expressions if term.strip()))


def lexical_hits(text: str, terms: tuple[str, ...]) -> int:
    folded = text.casefold().replace("–", "-").replace("—", "-")
    return sum(bool(re.search(r"(?<!\w)" + re.escape(term) + r"(?:s)?(?!\w)", folded)) for term in terms)
