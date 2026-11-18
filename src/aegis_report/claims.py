import re
from collections import defaultdict
from dataclasses import dataclass

from pydantic import Field, ValidationError

from .gateway import GatewayError, ModelGateway
from .models import Label, StrictModel
from .sources import Citation, Passage

INSTRUCTION_TEXT = re.compile(
    r"(?:ignore|override|disregard).{0,45}(?:instructions|prompt|rules)"
    r"|\b(?:system prompt|developer message|prompt injection|reveal (?:the )?token)\b"
    r"|<\s*/?\s*(?:system|assistant|script)\b",
    re.IGNORECASE,
)


class ProposedClaim(StrictModel):
    topic: Label
    text: str = Field(min_length=1, max_length=320)
    evidence_ids: list[str] = Field(min_length=1, max_length=4)


class ThemeClaim(StrictModel):
    key: str
    topic: str
    text: str
    evidence_ids: list[str]
    citations: list[Citation]
    method: str


@dataclass(frozen=True)
class Candidate:
    topic: str
    text: str
    citation: Citation

    def as_prompt_data(self) -> dict[str, str]:
        return {"id": self.citation.id, "topic": self.topic, "text": self.text, "source": self.citation.source}


def candidates_for(passages: list[Passage]) -> list[Candidate]:
    by_key = {}
    counts = defaultdict(int)
    for passage in passages:
        # Quarantine recognisable instruction-bearing blocks. Claim validation still treats all HTML/text as data.
        if INSTRUCTION_TEXT.search(passage.text):
            continue
        normalized = re.sub(r"^\[[^\]\n]{1,160}\]\s*", "", passage.text)
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", normalized):
            sentence = " ".join(sentence.split())
            if not (16 <= len(sentence) <= 320 and sentence.endswith((".", "!"))):
                continue
            for topic in passage.topics:
                group = (topic.casefold(), passage.citation.source)
                key = (topic, sentence, passage.citation.id)
                if counts[group] < 4 and key not in by_key:
                    by_key[key] = Candidate(topic, sentence, passage.citation)
                    counts[group] += 1
                if len(by_key) >= 24:
                    return list(by_key.values())
    return list(by_key.values())


def draft_themes(instruction: str, passages: list[Passage], gateway: ModelGateway) -> list[ThemeClaim]:
    candidates = candidates_for(passages)
    if not candidates:
        return []
    allowed = {(item.topic.casefold(), item.text, item.citation.id): item for item in candidates}
    accepted = []
    try:
        payload = gateway.draft_claims(instruction, [item.as_prompt_data() for item in candidates])
    except GatewayError:
        payload = None
    claims = payload.get("claims") if isinstance(payload, dict) and set(payload) == {"claims"} else None
    if isinstance(claims, list) and len(claims) <= 6:
        for raw in claims:
            try:
                proposed = ProposedClaim.model_validate(raw)
            except ValidationError:
                continue
            text = " ".join(proposed.text.split())
            matches = [allowed.get((proposed.topic.casefold(), text, id_)) for id_ in proposed.evidence_ids]
            if all(matches):
                accepted.append((matches[0].topic, text, [match.citation for match in matches], "verified_quote"))
    if not accepted:
        seen = set()
        for item in candidates:
            group = (item.topic.casefold(), item.citation.source)
            if group not in seen:
                accepted.append((item.topic, item.text, [item.citation], "fallback_quote"))
                seen.add(group)

    grouped = {}
    for topic, text, citations, method in accepted:
        key = (topic.casefold(), text)
        _, refs, _ = grouped.setdefault(key, (topic, {}, method))
        refs.update((citation.id, citation) for citation in citations)

    slot = defaultdict(int)
    output = []
    for (folded, text), (topic, refs, method) in list(grouped.items())[:6]:
        slot[folded] += 1
        output.append(ThemeClaim(
            key=f"{folded}:{slot[folded]}", topic=topic, text=text,
            evidence_ids=list(refs), citations=list(refs.values()), method=method,
        ))
    return output
